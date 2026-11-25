"""Fase D — Paper Trading Engine.

Mensimulasikan grid limit + TP/SL tanpa mengirim order ke Bitget.
Analisis, target, dan pemantauan eksekusi memakai candle 30m publik. State disimpan di state.json.

Alur:
  1. Baca kandidat yang ditampilkan di daftar_40.json dan analisis ulang tanpa AI.
  2. Cek risk.boleh_order_baru(state).
  3. Buka posisi paper (grid limit pending).
  4. Setiap candle 30m baru: cek fill limit, TP bertahap, dan SL.
  5. Tutup posisi → hitung PnL setelah fee → update state.

Pakai:
  python paper.py                  # satu siklus (cek sinyal + update posisi)
  python paper.py --loop           # loop terus (setiap ~60 detik)
  python paper.py --status         # tampilkan ringkasan state saja
  python paper.py --reset          # reset state hanya jika tidak ada posisi terbuka
  python paper.py --reset --ya     # buang posisi terbuka (eksperimen dianggap batal)
"""
from __future__ import annotations

import argparse
import json
import math
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import data_pasar as dp
import indikator as ik
import penilai_ai as pa
import risk
import state as st
import universe as uni

BIAYA_PP = 0.12  # % fee pulang-pergi (perkiraan taker 2 sisi)

# Slippage paper (konservatif):
# - Limit entry: jika candle gap menembus limit, fill di open (bisa lebih baik/buruk tergantung arah)
# - SL: selalu fill di extreme candle (low untuk long, high untuk short) — adverse
# - TP: diasumsikan limit, fill di harga TP (tanpa slippage positif)
SLIPPAGE_SL = True   # True = SL pakai extreme candle (realistis saat gap)
SLIPPAGE_LIMIT_GAP = True  # True = gap-through limit fill di open


def _waktu_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id_posisi(simbol: str) -> str:
    base = simbol.split("/")[0]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"paper-{ts}-{base}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Analisis kandidat dari universe yang ditampilkan
# ---------------------------------------------------------------------------

def _alasan_tolak(a: dict[str, Any], grid: list[dict[str, Any]]) -> list[str]:
    """Nama pintu yang gagal, singkat, untuk log scanner. Bukan keputusan baru."""
    valid = [g for g in grid if g.get("valid")]
    label = {
        "trend_structure": "tren",
        "ema": "ema",
        "macd": "macd",
        "near_sr": "dekat_sr",
        "vwap": "vwap",
        "trend_30m": "tren_30m",
        "extreme_candle": "ekstrem",
        "minimum_score": "skor",
        "grid_available": "grid",
    }
    alasan: list[str] = []
    for nama in pa.kegagalan_gate(a, valid):
        if nama == "valid_risk_reward_grid":
            continue
        teks = label.get(nama, nama)
        if teks not in alasan:
            alasan.append(teks)
    if not valid:
        spesifik: list[str] = []
        for titik in grid:
            for tolak in titik.get("tolak") or []:
                if str(tolak).startswith("risk_atr"):
                    kunci = "risk_atr"
                elif str(tolak).startswith("RR"):
                    kunci = "rr"
                elif tolak == "tanpa TP nyata":
                    kunci = "tanpa_tp"
                else:
                    kunci = "grid"
                if kunci not in spesifik:
                    spesifik.append(kunci)
        if not grid and "grid" not in alasan:
            alasan.append("grid")
        for kunci in spesifik:
            if kunci not in alasan:
                alasan.append(kunci)
    return alasan or ["lain"]


def _cetak_tolakan(tolakan: list[tuple[str, str, list[str], Any]]) -> None:
    if not tolakan:
        return
    hitung: dict[str, int] = {}
    for _, _, alasan, _ in tolakan:
        for nama in alasan:
            hitung[nama] = hitung.get(nama, 0) + 1
    ringkas = ", ".join(f"{nama}={jumlah}" for nama, jumlah in sorted(hitung.items(), key=lambda x: -x[1]))
    print(f"  Tolak: {ringkas}")
    for nama, sisi, alasan, jarak in tolakan[:12]:
        jarak_txt = ""
        if isinstance(jarak, (int, float)):
            jarak_txt = f" jarak_atr={jarak:.1f}x"
        print(f"    {nama:8} {sisi:5} [{', '.join(alasan)}]{jarak_txt}")
    sisa = len(tolakan) - 12
    if sisa > 0:
        print(f"    ... {sisa} simbol lain ditolak")


def muat_sinyal_layak(maks: int = 5) -> list[dict[str, Any]]:
    """Analisis kandidat bullish/bearish yang tampil di daftar_40.json."""
    try:
        data = uni.muat_data_daftar_40()
    except FileNotFoundError:
        print("  Sinyal: daftar_40.json belum ada. Jalankan penyaring.py terlebih dahulu.")
        return []

    daftar_40 = {
        sisi: {uni.base_simbol(item["simbol"]) for item in data[sisi]}
        for sisi in ("bullish", "bearish")
    }
    ex = dp.exchange_publik()
    hasil = []
    tolakan: list[tuple[str, str, list[str], Any]] = []
    gagal_simbol = 0
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for k in data[kunci]:
            simbol = k["simbol"]
            if not uni.ada_di_daftar_40(simbol, arah, daftar_40):
                continue
            try:
                c = dp.ambil_candle(ex, simbol, config.CANDLE_TIMEFRAME, 300)[:-1]
                a = ik.analisis(
                    c, arah,
                    config.NEAR_SR_PERCENT, config.SCORE_MIN,
                    config.NEAR_MODE, config.NEAR_ATR_MULT,
                    c30=c,
                )
                grid = pa.rencana(a, arah)
                valid = [g for g in grid if g["valid"]]
                if a["layak"] and valid:
                    snap = pa.snapshot(
                        {"simbol": simbol, "nama": simbol.split("/")[0], "arah": arah,
                         "ubah_24j": k.get("ubah_24j", 0), "vol_juta": k.get("vol_24j_usdt", 0) / 1e6,
                         "rasio_vol": k.get("rasio_vol", 1)},
                        a,
                    )
                    hasil.append(snap)
                else:
                    tolakan.append((
                        simbol.split("/")[0],
                        "LONG" if arah > 0 else "SHORT",
                        _alasan_tolak(a, grid),
                        a.get("jarak_atr"),
                    ))
            except Exception as e:
                print(f"  Sinyal: gagal menganalisis {simbol}: {type(e).__name__}: {e}")
                gagal_simbol += 1
                continue
            if len(hasil) >= maks:
                break
        if len(hasil) >= maks:
            break
    if gagal_simbol:
        print(f"  Sinyal: {gagal_simbol} simbol gagal dianalisis.")
    print(f"  Sinyal: {len(hasil)} layak dari daftar_40.json")
    _cetak_tolakan(tolakan)
    return hasil


# ---------------------------------------------------------------------------
# Buka posisi paper
# ---------------------------------------------------------------------------

def buka_posisi(state: dict[str, Any], sinyal: dict[str, Any]) -> dict[str, Any] | None:
    """Buka satu posisi paper dari sinyal yang sudah layak.
    Mengembalikan dict posisi atau None jika ditolak.
    """
    boleh, alasan = risk.boleh_order_baru(state)
    if not boleh:
        st.tambah_log(state, f"Tolak buka: {alasan}", "warn")
        return None

    if state.get("open_positions"):
        st.tambah_log(state, "Sudah ada posisi terbuka, lewati", "info")
        return None

    simbol = sinyal.get("simbol")
    if not simbol:
        return None
    # Normalisasi ke format Bitget
    if "/" not in simbol:
        simbol = f"{simbol}/USDT:USDT"
    arah = 1 if str(sinyal.get("arah", "")).upper().startswith("BULL") else -1

    size = risk.ringkasan_size()
    titik_valid = [t for t in (sinyal.get("titik_grid") or []) if t.get("valid")]
    if not titik_valid:
        st.tambah_log(state, f"{simbol}: tidak ada titik grid valid", "warn")
        return None

    # Semua titik grid share SL yang sama; TP memakai tangga S/R lawan.
    sl = titik_valid[0].get("sl")
    tps = [t["tp"] for t in titik_valid if t.get("tp") is not None]
    if not tps or sl is None:
        st.tambah_log(state, f"{simbol}: SL/TP tidak lengkap", "warn")
        return None
    ladder_dari_sinyal = any(t.get("tp_levels") for t in titik_valid)
    tp_levels = sorted(
        {level for t in titik_valid for level in (t.get("tp_levels") or [t["tp"]]) if level is not None},
        reverse=arah < 0,
    )
    tp = tp_levels[-1]

    pos = {
        "id": _id_posisi(simbol),
        "simbol": simbol,
        "arah": arah,
        "waktu_buka": _waktu_iso(),
        "margin": size["margin_usdt"],
        "leverage": size["leverage"],
        "notional": size["notional_usdt"],
        "titik_grid": [
            {
                "nama": t["titik"],
                "harga": t["harga"],
                "tp": t.get("tp"),
                "tp_levels": t.get("tp_levels") or ([t["tp"]] if t.get("tp") is not None else []),
                "status": "pending",  # pending | filled | cancelled
            }
            for t in titik_valid
        ],
        "tp_ladder": [{"harga": level, "status": "pending"} for level in tp_levels],
        "tp_fraction_per_level": sinyal.get("tp_fraction_per_level", 0.25 if ladder_dari_sinyal else 1.0),
        "sl": sl,
        "tp": tp,
        "candle_timeframe": sinyal.get("candle_timeframe", config.CANDLE_TIMEFRAME),
        "entry_avg": None,
        "ukuran_terisi": 0.0,       # notional yang sudah terisi
        "ukuran_masuk_total": 0.0,
        "ukuran_ditutup": 0.0,
        "realisasi": {"pnl_kotor": 0.0, "fee": 0.0, "pnl_bersih": 0.0, "notional": 0.0},
        "candle_terakhir_diproses": sinyal.get("candle_timestamp"),
        "status": "open",
        "skor_bot": sinyal.get("skor_bot"),
        "rr_terbaik": sinyal.get("rr_terbaik"),
    }

    state["open_positions"].append(pos)
    st.tambah_log(
        state,
        f"BUKA {simbol} {'LONG' if arah > 0 else 'SHORT'} | "
        f"margin={size['margin_usdt']:.2f} notional={size['notional_usdt']:.2f} | "
        f"grid={len(titik_valid)} titik | SL={sl} TP levels={tp_levels} "
        f"({pos['tp_fraction_per_level']:.0%} posisi/level)",
        "info",
    )
    return pos


# ---------------------------------------------------------------------------
# Update posisi terbuka (fill + exit) — partial fill aware
# ---------------------------------------------------------------------------
#
# Edge cases yang ditangani:
# 1. Partial fill: hanya notional proporsional yang aktif; sisa limit tetap pending.
# 2. Fill + SL/TP dalam candle yang sama: fill dulu, lalu cek exit (realistis untuk bar).
# 3. Beberapa level terisi sekaligus (gap): semua yang tersentuh diisi, entry_avg dihitung ulang.
# 4. Saat exit: sisa pending otomatis di-cancel, PnL hanya dihitung dari ukuran_terisi.
# 5. Belum ada fill sama sekali: TP/SL belum aktif (tidak bisa keluar sebelum entry).
# 6. Entry average = rata-rata sederhana (tiap level diasumsikan porsi notional sama).
#

def _n_filled(pos: dict[str, Any]) -> int:
    return sum(
        1 for t in pos["titik_grid"]
        if t["status"] == "filled" or float(t.get("filled_notional") or 0) > 0
    )


def _n_pending(pos: dict[str, Any]) -> int:
    return sum(1 for t in pos["titik_grid"] if t["status"] in ("pending", "partial"))


def _harga_fill_limit(limit: float, arah: int, candle: dict) -> float:
    """Harga fill aktual untuk limit order.

    Normal: fill di harga limit.
    Gap-through (open sudah melewati limit): fill di open (SLIPPAGE_LIMIT_GAP).
      Long limit 100, open 98 → fill 98 (lebih baik)
      Short limit 100, open 102 → fill 102 (lebih baik)
    Slippage adverse pada limit entry jarang; gap biasanya menguntungkan pembuat limit.
    """
    if not SLIPPAGE_LIMIT_GAP:
        return limit
    o = candle["o"]
    if arah > 0 and o < limit:   # gap down menembus buy limit
        return o
    if arah < 0 and o > limit:   # gap up menembus sell limit
        return o
    return limit


def _harga_exit_sl(sl: float, arah: int, candle: dict) -> float:
    """Harga exit SL dengan slippage adverse.

    Long  : fill di min(sl, low)  — bisa lebih buruk dari SL
    Short : fill di max(sl, high)
    """
    if not SLIPPAGE_SL:
        return sl
    if arah > 0:
        return min(sl, candle["l"])
    return max(sl, candle["h"])


def _harga_exit_tp(tp: float, arah: int, candle: dict) -> float:
    """TP diasumsikan limit → fill di harga TP (tidak ambil slippage positif)."""
    return tp


def _cek_fill(pos: dict[str, Any], candle: dict) -> list[dict]:
    """Apply trade-through confirmation and a shared candle-volume fill cap."""
    filled = []
    arah = pos["arah"]
    low, high = candle["l"], candle["h"]
    threshold = max(0.0, config.PAPER_FILL_THROUGH_BPS) / 10_000
    participation = config.PAPER_FILL_PARTICIPATION_PCT / 100
    if not 0 < participation <= 1:
        raise ValueError("PAPER_FILL_PARTICIPATION_PCT must be in (0, 100]")
    volume = float(candle.get("v") or 0)
    if not math.isfinite(volume) or volume < 0:
        raise ValueError("Candle volume must be finite and non-negative")
    capacity = volume * float(candle["c"]) * participation

    for t in pos["titik_grid"]:
        if t["status"] not in ("pending", "partial"):
            continue
        harga = t["harga"]
        crossed = (
            arah > 0
            and low <= harga * (1 - threshold)
            and float(candle["c"]) <= harga
        ) or (
            arah < 0
            and high >= harga * (1 + threshold)
            and float(candle["c"]) >= harga
        )
        if not crossed or capacity <= 0:
            continue
        per_level = pos["notional"] / max(len(pos["titik_grid"]), 1)
        already_filled = float(t.get("filled_notional") or 0)
        if t["status"] == "filled" and "filled_notional" not in t:
            already_filled = per_level
        remaining = max(0.0, per_level - already_filled)
        fill_notional = min(remaining, capacity)
        if fill_notional <= 0:
            continue
        t["filled_notional"] = already_filled + fill_notional
        t["_fill_notional_delta"] = fill_notional
        t["status"] = "filled" if t["filled_notional"] >= per_level - 1e-9 else "partial"
        t["harga_fill"] = _harga_fill_limit(harga, arah, candle)
        t["waktu_fill"] = _waktu_iso()
        filled.append(t)
        capacity -= fill_notional
    return filled


def _hitung_entry_avg(pos: dict[str, Any]) -> float | None:
    """Weighted average entry across full, partial, and cancelled partial fills."""
    filled = [
        t for t in pos["titik_grid"]
        if t["status"] in ("filled", "partial", "cancelled")
        and (float(t.get("filled_notional") or 0) > 0 or t["status"] == "filled")
    ]
    if not filled:
        return None
    values = []
    for level in filled:
        notional = float(level.get("filled_notional") or 0)
        if notional <= 0:
            notional = pos["notional"] / max(len(pos["titik_grid"]), 1)
        values.append((float(level.get("harga_fill", level["harga"])), notional))
    total = sum(notional for _, notional in values)
    return sum(price * notional for price, notional in values) / total if total else None


def _tp_efektif(pos: dict[str, Any]) -> float | None:
    """Target TP berikutnya atau, untuk posisi lama, TP efektif sebelumnya.

    Posisi baru menggunakan ladder target S/R. Posisi lama yang tersimpan tetap
    memakai TP per titik untuk menjaga perilakunya.
    """
    if "tp_ladder" in pos:
        pending = [level["harga"] for level in pos["tp_ladder"] if level["status"] == "pending"]
        return pending[0] if pending else None

    filled = [
        t for t in pos["titik_grid"]
        if t["status"] in ("filled", "partial", "cancelled")
        and (float(t.get("filled_notional") or 0) > 0 or t["status"] == "filled")
        and t.get("tp") is not None
    ]
    if not filled:
        return pos.get("tp")
    arah = pos["arah"]
    entry = pos.get("entry_avg") or filled[0]["harga"]
    # Pilih TP dengan reward terkecil di antara yang filled (konservatif)
    if arah > 0:
        return min(t["tp"] for t in filled)
    return max(t["tp"] for t in filled)


def _cek_exit(pos: dict[str, Any], candle: dict) -> str | None:
    """Cek apakah TP atau SL tersentuh. Return 'tp' | 'sl' | None.

    Hanya aktif setelah minimal 1 level terisi (entry_avg ada).
    Prioritas: SL dicek dulu (lebih aman jika candle menyentuh keduanya).
    """
    if pos.get("entry_avg") is None:
        return None

    arah = pos["arah"]
    low, high = candle["l"], candle["h"]
    sl = pos["sl"]
    if sl is None:
        return None

    if arah > 0:
        if low <= sl:
            return "sl"
        if any(
            level["status"] == "pending" and _trade_through_target(level["harga"], arah, candle)
            for level in pos.get("tp_ladder", [])
        ):
            return "tp"
    else:
        if high >= sl:
            return "sl"
        if any(
            level["status"] == "pending" and _trade_through_target(level["harga"], arah, candle)
            for level in pos.get("tp_ladder", [])
        ):
            return "tp"
    if "tp_ladder" not in pos:
        tp = _tp_efektif(pos)
        if tp is None:
            return None
        if _trade_through_target(tp, arah, candle):
            return "tp"
    return None


def _trade_through_target(target: float, arah: int, candle: dict) -> bool:
    threshold = max(0.0, config.PAPER_FILL_THROUGH_BPS) / 10_000
    if arah > 0:
        return candle["h"] >= target * (1 + threshold) and candle["c"] >= target
    return candle["l"] <= target * (1 - threshold) and candle["c"] <= target


def _cancel_sisa_pending(pos: dict[str, Any]) -> int:
    """Batalkan semua limit yang masih pending. Return jumlah yang di-cancel."""
    n = 0
    for t in pos["titik_grid"]:
        if t["status"] in ("pending", "partial"):
            t["status"] = "cancelled"
            n += 1
    for level in pos.get("tp_ladder", []):
        if level["status"] == "pending":
            level["status"] = "cancelled"
    return n


def _hitung_pnl(
    pos: dict[str, Any], harga_keluar: float, notional_override: float | None = None,
) -> dict[str, float]:
    """Hitung PnL setelah fee — hanya dari ukuran yang sudah terisi."""
    entry = pos["entry_avg"]
    notional = pos.get("ukuran_terisi") or 0.0
    if notional_override is not None:
        notional = notional_override
    arah = pos["arah"]

    if not entry or notional <= 0:
        return {
            "pnl_persen": 0.0,
            "pnl_kotor": 0.0,
            "fee": 0.0,
            "pnl_bersih": 0.0,
            "harga_keluar": harga_keluar,
            "notional_terisi": 0.0,
            "n_filled": 0,
        }

    if arah > 0:
        pnl_persen = (harga_keluar - entry) / entry * 100
    else:
        pnl_persen = (entry - harga_keluar) / entry * 100

    pnl_kotor = notional * (pnl_persen / 100)
    fee = notional * (BIAYA_PP / 100)
    pnl_bersih = pnl_kotor - fee

    return {
        "pnl_persen": round(pnl_persen, 4),
        "pnl_kotor": round(pnl_kotor, 4),
        "fee": round(fee, 4),
        "pnl_bersih": round(pnl_bersih, 4),
        "harga_keluar": harga_keluar,
        "notional_terisi": round(notional, 4),
        "n_filled": _n_filled(pos),
    }


def _akumulasi_hasil(pos: dict[str, Any], hasil_baru: dict[str, float], harga_keluar: float) -> dict[str, float]:
    realisasi = pos.setdefault(
        "realisasi", {"pnl_kotor": 0.0, "fee": 0.0, "pnl_bersih": 0.0, "notional": 0.0, "nilai_keluar": 0.0},
    )
    for nama in ("pnl_kotor", "fee", "pnl_bersih"):
        realisasi[nama] = realisasi.get(nama, 0.0) + hasil_baru[nama]
    realisasi["notional"] = realisasi.get("notional", 0.0) + hasil_baru["notional_terisi"]
    realisasi["nilai_keluar"] = realisasi.get("nilai_keluar", 0.0) + hasil_baru["notional_terisi"] * harga_keluar
    pos["ukuran_ditutup"] = pos.get("ukuran_ditutup", 0.0) + hasil_baru["notional_terisi"]
    notional_total = realisasi["notional"]
    return {
        "pnl_persen": round(realisasi["pnl_kotor"] / notional_total * 100, 4) if notional_total else 0.0,
        "pnl_kotor": round(realisasi["pnl_kotor"], 4),
        "fee": round(realisasi["fee"], 4),
        "pnl_bersih": round(realisasi["pnl_bersih"], 4),
        "harga_keluar": round(realisasi["nilai_keluar"] / notional_total, 8) if notional_total else harga_keluar,
        "notional_terisi": round(notional_total, 4),
        "n_filled": _n_filled(pos),
    }


def _catat_pnl(state: dict[str, Any], pnl_bersih: float) -> None:
    state["modal_saat_ini"] = round(state["modal_saat_ini"] + pnl_bersih, 4)
    state["daily_pnl_usdt"] = round(state["daily_pnl_usdt"] + pnl_bersih, 4)


def _finalisasi_posisi(
    state: dict[str, Any], pos: dict[str, Any], alasan: str, hasil: dict[str, float],
    harga_keluar: float, level_teori: float | None,
) -> None:
    n_cancel = _cancel_sisa_pending(pos)
    slip = None
    if level_teori and pos.get("entry_avg"):
        if pos["arah"] > 0:
            slip = ((level_teori - harga_keluar) if alasan == "sl" else (harga_keluar - level_teori)) / level_teori * 100
        else:
            slip = ((harga_keluar - level_teori) if alasan == "sl" else (level_teori - harga_keluar)) / level_teori * 100
    hasil["slippage_pct"] = round(slip, 4) if slip is not None else 0.0
    hasil["level_teori"] = level_teori
    hasil["notional_sisa"] = round(pos.get("ukuran_terisi", 0.0), 4)

    pos["status"] = "closed"
    pos["waktu_tutup"] = _waktu_iso()
    pos["alasan_tutup"] = alasan
    pos["hasil"] = hasil
    pos["pending_dibatalkan"] = n_cancel

    state["total_trades"] = state.get("total_trades", 0) + 1
    if hasil["pnl_bersih"] >= 0:
        state["total_wins"] = state.get("total_wins", 0) + 1
        state["consecutive_losses"] = 0
    else:
        state["total_losses"] = state.get("total_losses", 0) + 1
        state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

    state["open_positions"] = [p for p in state["open_positions"] if p["id"] != pos["id"]]
    state.setdefault("riwayat", []).append(pos)
    state["riwayat"] = state["riwayat"][-100:]

    slip_txt = f" | slip={hasil['slippage_pct']:+.3f}%" if abs(hasil["slippage_pct"]) > 0.001 else ""
    st.tambah_log(
        state,
        f"TUTUP {pos['simbol']} {alasan.upper()} | "
        f"entry={pos['entry_avg']:.6g} keluar={harga_keluar:.6g} | "
        f"PnL kumulatif={hasil['pnl_bersih']:+.4f} USDT ({hasil['pnl_persen']:+.3f}%) | "
        f"fee={hasil['fee']:.4f}{slip_txt}"
        + (f" | cancel {n_cancel} pending" if n_cancel else ""),
        "info" if hasil["pnl_bersih"] >= 0 else "warn",
    )


def tutup_posisi(state: dict[str, Any], pos: dict[str, Any], alasan: str, harga_keluar: float) -> None:
    """Tutup posisi, cancel sisa pending, hitung PnL hanya dari yang terisi, pindah ke riwayat."""
    hasil_baru = _hitung_pnl(pos, harga_keluar)
    _catat_pnl(state, hasil_baru["pnl_bersih"])
    hasil = _akumulasi_hasil(pos, hasil_baru, harga_keluar)
    pos["ukuran_terisi"] = 0.0
    level_teori = pos["sl"] if alasan == "sl" else (_tp_efektif(pos) or pos["tp"])
    _finalisasi_posisi(state, pos, alasan, hasil, harga_keluar, level_teori)


def _realisasi_tp(
    state: dict[str, Any], pos: dict[str, Any], level: dict[str, Any],
) -> None:
    harga = level["harga"]
    level["status"] = "hit"
    if pos.get("tp_notional_basis") is None:
        pos["tp_notional_basis"] = pos.get("ukuran_terisi", 0.0)
    jumlah = min(
        pos.get("ukuran_terisi", 0.0),
        pos["tp_notional_basis"] * pos.get("tp_fraction_per_level", 0.25),
    )
    if jumlah <= 0:
        return

    hasil_baru = _hitung_pnl(pos, harga, jumlah)
    _catat_pnl(state, hasil_baru["pnl_bersih"])
    hasil = _akumulasi_hasil(pos, hasil_baru, harga)
    pos["ukuran_terisi"] = max(0.0, pos.get("ukuran_terisi", 0.0) - jumlah)
    pos.setdefault("tp_events", []).append({
        "harga": harga,
        "notional": round(jumlah, 4),
        "pnl_bersih": hasil_baru["pnl_bersih"],
    })
    st.tambah_log(
        state,
        f"TP {pos['simbol']} @ {harga:.8g} | ditutup={jumlah:.4f} "
        f"({pos.get('tp_fraction_per_level', 0.25):.0%} posisi) | "
        f"PnL={hasil_baru['pnl_bersih']:+.4f} USDT",
        "info" if hasil_baru["pnl_bersih"] >= 0 else "warn",
    )
    if pos["ukuran_terisi"] <= 1e-10:
        pos["ukuran_terisi"] = 0.0
        _finalisasi_posisi(state, pos, "tp", hasil, harga, harga)


def update_posisi(state: dict[str, Any], pos: dict[str, Any], candle: dict) -> None:
    """Satu siklus update untuk satu posisi terbuka (partial-fill aware).

    Urutan:
      1. Cek fill limit baru (bisa partial / multi-level)
      2. Update entry_avg + ukuran_terisi
      3. Cek exit (SL diprioritaskan). Jika exit → cancel sisa pending + tutup.
    """
    # 1. Cek fill
    baru_filled = _cek_fill(pos, candle)
    if baru_filled:
        total = len(pos["titik_grid"])
        fill_deltas = [
            (t, float(t.pop("_fill_notional_delta", 0)))
            for t in baru_filled
        ]
        ukuran_baru = sum(delta for _, delta in fill_deltas)
        ukuran_lama = pos.get("ukuran_terisi", 0.0)
        harga_lama = pos.get("entry_avg")
        nilai_baru = sum(
            float(t.get("harga_fill", t["harga"])) * delta
            for t, delta in fill_deltas
        )
        harga_baru = nilai_baru / ukuran_baru if ukuran_baru else 0.0
        pos["ukuran_masuk_total"] = pos.get("ukuran_masuk_total", ukuran_lama) + ukuran_baru
        pos["ukuran_terisi"] = ukuran_lama + ukuran_baru
        pos["entry_avg"] = (
            (harga_lama * ukuran_lama + harga_baru * ukuran_baru) / pos["ukuran_terisi"]
            if harga_lama is not None and ukuran_lama > 0 else harga_baru
        )
        n_filled = _n_filled(pos)
        nama = ",".join(t["nama"] for t in baru_filled)
        st.tambah_log(
            state,
            f"FILL {pos['simbol']} [{nama}] → entry_avg={pos['entry_avg']:.6g} | "
            f"terisi={pos['ukuran_terisi']:.2f}/{pos['notional']:.2f} "
            f"({n_filled}/{total} level)",
            "info",
        )

    # 2. Cek exit (hanya jika sudah ada minimal 1 fill)
    alasan = _cek_exit(pos, candle)
    if alasan == "sl":
        # Prioritaskan SL jika candle menyentuh SL dan TP sekaligus.
        harga_keluar = _harga_exit_sl(pos["sl"], pos["arah"], candle)
        tutup_posisi(state, pos, "sl", harga_keluar)
        return
    if alasan == "tp":
        ladder = pos.get("tp_ladder")
        if ladder is None:
            tp = _tp_efektif(pos) or pos["tp"]
            tutup_posisi(state, pos, "tp", _harga_exit_tp(tp, pos["arah"], candle))
            return
        for level in ladder:
            if level["status"] != "pending":
                continue
            tersentuh = (
                _trade_through_target(level["harga"], pos["arah"], candle)
            )
            if not tersentuh:
                continue
            _realisasi_tp(state, pos, level)
            if pos.get("status") == "closed":
                return
        return


# ---------------------------------------------------------------------------
# Siklus utama
# ---------------------------------------------------------------------------

def satu_siklus(state: dict[str, Any], buka_baru: bool = True) -> None:
    """Satu putaran: update posisi terbuka + (opsional) coba buka posisi baru."""
    ex = dp.exchange_publik()

    # --- Update posisi yang sudah terbuka ---
    for pos in list(state.get("open_positions") or []):
        try:
            candles = dp.ambil_candle(ex, pos["simbol"], pos.get("candle_timeframe", config.CANDLE_TIMEFRAME), 5)
            if len(candles) < 2:
                continue
            candle_tutup = candles[:-1]
            terakhir = pos.get("candle_terakhir_diproses")
            baru = (
                [candle_tutup[-1]] if terakhir is None and candle_tutup
                else [c for c in candle_tutup if c["t"] > terakhir]
            )
            for candle in baru:
                update_posisi(state, pos, candle)
                pos["candle_terakhir_diproses"] = candle["t"]
                if pos.get("status") == "closed":
                    break
        except Exception as e:
            st.tambah_log(state, f"Error update {pos['simbol']}: {type(e).__name__}: {e}", "error")

    # --- Coba buka posisi baru ---
    if buka_baru and not state.get("open_positions"):
        sinyal_list = muat_sinyal_layak(maks=3)
        if not sinyal_list:
            st.tambah_log(state, "Tidak ada sinyal layak (syarat masuk / grid tidak terpenuhi)", "info")
            print("  Tidak ada posisi dibuka: belum ada setup yang lolos syarat bot.")
            print("  Penyebab umum: tren_30m/MACD/dekat_SR gagal, atau SL risk_atr di luar batas.")
            print("  Cek: python tes_indikator.py  dan  python cek_kelayakan.py")
        else:
            terbaik = max(sinyal_list, key=lambda s: s.get("skor_bot") or 0)
            buka_posisi(state, terbaik)
    elif state.get("open_positions"):
        print(f"  Lewati buka baru: sudah ada {len(state['open_positions'])} posisi terbuka.")

    st.simpan(state)


def tampil_status(state: dict[str, Any]) -> None:
    try:
        _cetak_status(state)
    except Exception as exc:
        print(f"  Status paper tidak tercetak utuh: {type(exc).__name__}")


def _cetak_status(state: dict[str, Any]) -> None:
    print("=== STATUS PAPER ===")
    print(st.ringkasan(state))
    print()
    opens = state.get("open_positions") or []
    if not opens:
        print("Tidak ada posisi terbuka.")
    else:
        for p in opens:
            arah = "LONG" if p["arah"] > 0 else "SHORT"
            filled = sum(1 for t in p["titik_grid"] if t["status"] == "filled")
            pending = sum(1 for t in p["titik_grid"] if t["status"] == "pending")
            total = len(p["titik_grid"])
            partial = " (partial)" if 0 < filled < total else ""
            tp_eff = _tp_efektif(p)
            tp_label = f"TP berikut={tp_eff}" if tp_eff is not None else "TP ladder habis; sisa ke SL"
            print(
                f"  {p['simbol']} {arah}{partial} | entry={p.get('entry_avg') or '-'} | "
                f"filled={filled}/{total} pending={pending} | "
                f"notional={p.get('ukuran_terisi', 0):.2f}/{p['notional']:.2f} | "
                f"SL={p['sl']} {tp_label}"
            )
            # Detail level
            for t in p["titik_grid"]:
                print(f"      {t['nama']:4} @ {t['harga']} -> {t['status']}")
            for level in p.get("tp_ladder", []):
                print(f"      TP  @ {level['harga']} -> {level['status']}")
    print()
    riwayat = state.get("riwayat") or []
    if riwayat:
        print("5 trade terakhir:")
        for r in riwayat[-5:]:
            h = r.get("hasil") or {}
            n_f = h.get("n_filled", "?")
            total = len(r.get("titik_grid") or [])
            partial = f" {n_f}/{total}" if total else ""
            print(
                f"  {r['simbol']} {r.get('alasan_tutup','?'):4}{partial} | "
                f"PnL={h.get('pnl_bersih', 0):+.4f} | {r.get('waktu_tutup','')[:19]}"
            )


def main():
    parser = argparse.ArgumentParser(description="Paper Trading Engine Bot-Tree")
    parser.add_argument("--loop", action="store_true", help="Jalankan terus setiap ~60 detik")
    parser.add_argument("--status", action="store_true", help="Tampilkan status saja")
    parser.add_argument("--reset", action="store_true", help="Reset state.json ke awal")
    parser.add_argument("--ya", action="store_true", help="Izinkan reset meski masih ada posisi terbuka")
    parser.add_argument("--no-buka", action="store_true", help="Hanya update posisi, jangan buka baru")
    parser.add_argument("--interval", type=int, default=60, help="Detik antar siklus (default 60)")
    args = parser.parse_args()

    if args.reset:
        lama = st.muat()
        terbuka = lama.get("open_positions") or []
        if terbuka and not args.ya:
            print(f"Reset ditolak: {len(terbuka)} posisi paper masih terbuka.")
            print("Tunggu SL/TP. Reset paksa membuang eksperimen dan tidak menambah trade tertutup.")
            print("Pakai: python paper.py --reset --ya")
            raise SystemExit(1)
        s = st.state_kosong()
        st.simpan(s)
        print("State di-reset.")
        print(st.ringkasan(s))
        return

    state = st.muat()

    if args.status:
        tampil_status(state)
        return

    print(f"Paper engine | {st.ringkasan(state)}")
    print(f"Modal config: {config.MODAL_USDT} USDT | Leverage {config.LEVERAGE}x | "
          f"Margin/setup {risk.margin_per_setup():.2f} USDT")
    print()

    if args.loop:
        print(f"Loop aktif (interval {args.interval}s). Ctrl+C untuk berhenti.\n")
        try:
            while True:
                print(f"--- {_waktu_iso()} ---")
                satu_siklus(state, buka_baru=not args.no_buka)
                tampil_status(state)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\nDihentikan.")
            st.simpan(state)
    else:
        satu_siklus(state, buka_baru=not args.no_buka)
        tampil_status(state)


if __name__ == "__main__":
    main()
