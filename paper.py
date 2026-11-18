"""Fase D — Paper Trading Engine.

Mensimulasikan grid limit + TP/SL tanpa mengirim order ke Bitget.
Hanya memakai data candle publik. State disimpan di state.json.

Alur:
  1. Baca sinyal layak (dari penilai_ai.json atau daftar_ai.json + analisis ulang).
  2. Cek risk.boleh_order_baru(state).
  3. Buka posisi paper (grid limit pending).
  4. Setiap candle baru: cek fill limit, TP, SL, lonjakan ekstrem.
  5. Tutup posisi → hitung PnL setelah fee → update state.

Pakai:
  python paper.py                  # satu siklus (cek sinyal + update posisi)
  python paper.py --loop           # loop terus (setiap ~60 detik)
  python paper.py --status         # tampilkan ringkasan state saja
  python paper.py --reset          # reset state (hati-hati)
"""
from __future__ import annotations

import argparse
import json
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

BIAYA_PP = 0.12  # % fee pulang-pergi (perkiraan taker 2 sisi)
FILE_SINYAL = "penilai_ai.json"
FILE_DAFTAR = "daftar_ai.json"

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
# Baca sinyal dari hasil penilai / daftar AI
# ---------------------------------------------------------------------------

def muat_sinyal_layak(maks: int = 5) -> list[dict[str, Any]]:
    """Ambil token yang layak_bot_final=True dari penilai_ai.json.
    Jika file belum ada, coba bangun ulang dari daftar_ai.json (tanpa AI).
    """
    # Prioritas 1: hasil penilai_ai
    try:
        with open(FILE_SINYAL, encoding="utf-8") as f:
            data = json.load(f)
        snaps = data.get("snapshot") or []
        layak = [s for s in snaps if s.get("layak_bot_final")]
        if layak:
            return layak[:maks]
    except FileNotFoundError:
        pass

    # Prioritas 2: bangun dari daftar_ai + analisis ulang
    try:
        with open(FILE_DAFTAR, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return []

    ex = dp.exchange_publik()
    hasil = []
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for k in d.get(kunci, []):
            simbol = k["simbol"]
            try:
                c = dp.ambil_candle(ex, simbol, "5m", 300)[:-1]
                c30 = dp.ambil_candle(ex, simbol, "30m", 200)[:-1]
                a = ik.analisis(
                    c, arah,
                    config.NEAR_SR_PERCENT, config.SCORE_MIN,
                    config.NEAR_MODE, config.NEAR_ATR_MULT,
                    c30=c30,
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
            except Exception:
                continue
            if len(hasil) >= maks:
                break
        if len(hasil) >= maks:
            break
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

    # Ambil SL & TP dari titik pertama yang valid (semua titik share SL yang sama)
    sl = titik_valid[0].get("sl")
    # TP bisa berbeda per titik; untuk paper kita pakai TP terbaik (paling jauh)
    tps = [t["tp"] for t in titik_valid if t.get("tp") is not None]
    if not tps or sl is None:
        st.tambah_log(state, f"{simbol}: SL/TP tidak lengkap", "warn")
        return None
    tp = max(tps) if arah > 0 else min(tps)

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
                "status": "pending",  # pending | filled | cancelled
            }
            for t in titik_valid
        ],
        "sl": sl,
        "tp": tp,
        "entry_avg": None,
        "ukuran_terisi": 0.0,       # notional yang sudah terisi
        "status": "open",
        "skor_bot": sinyal.get("skor_bot"),
        "rr_terbaik": sinyal.get("rr_terbaik"),
    }

    state["open_positions"].append(pos)
    st.tambah_log(
        state,
        f"BUKA {simbol} {'LONG' if arah > 0 else 'SHORT'} | "
        f"margin={size['margin_usdt']:.2f} notional={size['notional_usdt']:.2f} | "
        f"grid={len(titik_valid)} titik | SL={sl} TP={tp}",
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
    return sum(1 for t in pos["titik_grid"] if t["status"] == "filled")


def _n_pending(pos: dict[str, Any]) -> int:
    return sum(1 for t in pos["titik_grid"] if t["status"] == "pending")


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
    """Cek titik limit mana yang terisi pada candle ini.

    Long  : low <= harga limit  → filled
    Short : high >= harga limit → filled

    Bisa mengisi beberapa level sekaligus jika candle merentang jauh (gap).
    Harga fill disimpan di t['harga_fill'] (bisa beda dari limit saat gap).
    """
    filled = []
    arah = pos["arah"]
    low, high = candle["l"], candle["h"]

    for t in pos["titik_grid"]:
        if t["status"] != "pending":
            continue
        harga = t["harga"]
        if arah > 0 and low <= harga:
            t["status"] = "filled"
            t["harga_fill"] = _harga_fill_limit(harga, arah, candle)
            t["waktu_fill"] = _waktu_iso()
            filled.append(t)
        elif arah < 0 and high >= harga:
            t["status"] = "filled"
            t["harga_fill"] = _harga_fill_limit(harga, arah, candle)
            t["waktu_fill"] = _waktu_iso()
            filled.append(t)
    return filled


def _hitung_entry_avg(pos: dict[str, Any]) -> float | None:
    """Rata-rata entry dari titik yang sudah filled (porsi sama per level).

    Pakai harga_fill jika ada (setelah gap slippage), selain itu harga limit.
    """
    filled = [t for t in pos["titik_grid"] if t["status"] == "filled"]
    if not filled:
        return None
    return sum(t.get("harga_fill", t["harga"]) for t in filled) / len(filled)


def _tp_efektif(pos: dict[str, Any]) -> float | None:
    """TP yang dipakai untuk exit.

    - Jika ada titik filled yang punya TP sendiri → pakai TP terdekat ke entry
      (lebih konservatif daripada TP terjauh).
    - Fallback ke pos['tp'] (shared) jika tidak ada.
    """
    filled = [t for t in pos["titik_grid"] if t["status"] == "filled" and t.get("tp") is not None]
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
    tp = _tp_efektif(pos)
    if tp is None or sl is None:
        return None

    if arah > 0:
        if low <= sl:
            return "sl"
        if high >= tp:
            return "tp"
    else:
        if high >= sl:
            return "sl"
        if low <= tp:
            return "tp"
    return None


def _cancel_sisa_pending(pos: dict[str, Any]) -> int:
    """Batalkan semua limit yang masih pending. Return jumlah yang di-cancel."""
    n = 0
    for t in pos["titik_grid"]:
        if t["status"] == "pending":
            t["status"] = "cancelled"
            n += 1
    return n


def _hitung_pnl(pos: dict[str, Any], harga_keluar: float) -> dict[str, float]:
    """Hitung PnL setelah fee — hanya dari ukuran yang sudah terisi."""
    entry = pos["entry_avg"]
    notional = pos.get("ukuran_terisi") or 0.0
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


def tutup_posisi(state: dict[str, Any], pos: dict[str, Any], alasan: str, harga_keluar: float) -> None:
    """Tutup posisi, cancel sisa pending, hitung PnL hanya dari yang terisi, pindah ke riwayat."""
    n_cancel = _cancel_sisa_pending(pos)
    hasil = _hitung_pnl(pos, harga_keluar)

    # Catat slippage vs level teoritis
    level_teori = pos["sl"] if alasan == "sl" else (_tp_efektif(pos) or pos["tp"])
    slip = None
    if level_teori and pos.get("entry_avg"):
        # slippage dalam persen harga (positif = lebih buruk bagi trader)
        if pos["arah"] > 0:
            # long SL: keluar lebih rendah = buruk; long TP: keluar lebih tinggi = baik
            if alasan == "sl":
                slip = (level_teori - harga_keluar) / level_teori * 100
            else:
                slip = (harga_keluar - level_teori) / level_teori * 100
        else:
            if alasan == "sl":
                slip = (harga_keluar - level_teori) / level_teori * 100
            else:
                slip = (level_teori - harga_keluar) / level_teori * 100
    hasil["slippage_pct"] = round(slip, 4) if slip is not None else 0.0
    hasil["level_teori"] = level_teori

    pos["status"] = "closed"
    pos["waktu_tutup"] = _waktu_iso()
    pos["alasan_tutup"] = alasan
    pos["hasil"] = hasil
    pos["pending_dibatalkan"] = n_cancel

    # Update state agregat
    state["modal_saat_ini"] = round(state["modal_saat_ini"] + hasil["pnl_bersih"], 4)
    state["daily_pnl_usdt"] = round(state["daily_pnl_usdt"] + hasil["pnl_bersih"], 4)
    state["total_trades"] = state.get("total_trades", 0) + 1

    if hasil["pnl_bersih"] >= 0:
        state["total_wins"] = state.get("total_wins", 0) + 1
        state["consecutive_losses"] = 0
    else:
        state["total_losses"] = state.get("total_losses", 0) + 1
        state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1

    # Pindahkan ke riwayat
    state["open_positions"] = [p for p in state["open_positions"] if p["id"] != pos["id"]]
    state.setdefault("riwayat", []).append(pos)
    state["riwayat"] = state["riwayat"][-100:]

    partial_txt = ""
    total_level = len(pos["titik_grid"])
    if hasil["n_filled"] < total_level:
        partial_txt = f" | partial {hasil['n_filled']}/{total_level} level"

    slip = hasil.get("slippage_pct") or 0
    slip_txt = f" | slip={slip:+.3f}%" if abs(slip) > 0.001 else ""

    st.tambah_log(
        state,
        f"TUTUP {pos['simbol']} {alasan.upper()} | "
        f"entry={pos['entry_avg']:.6g} keluar={harga_keluar:.6g} | "
        f"PnL={hasil['pnl_bersih']:+.4f} USDT ({hasil['pnl_persen']:+.3f}%) | "
        f"fee={hasil['fee']:.4f}{partial_txt}{slip_txt}"
        + (f" | cancel {n_cancel} pending" if n_cancel else ""),
        "info" if hasil["pnl_bersih"] >= 0 else "warn",
    )


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
        n_filled = _n_filled(pos)
        # Alokasi notional proporsional terhadap jumlah level yang terisi
        pos["ukuran_terisi"] = pos["notional"] * (n_filled / total) if total else 0.0
        pos["entry_avg"] = _hitung_entry_avg(pos)
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
    if alasan:
        if alasan == "sl":
            # Slippage adverse: long fill di low, short di high
            harga_keluar = _harga_exit_sl(pos["sl"], pos["arah"], candle)
        else:
            tp = _tp_efektif(pos) or pos["tp"]
            harga_keluar = _harga_exit_tp(tp, pos["arah"], candle)
        tutup_posisi(state, pos, alasan, harga_keluar)
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
            candles = dp.ambil_candle(ex, pos["simbol"], "5m", 5)
            if len(candles) < 2:
                continue
            # Pakai candle yang sudah tutup (index -2)
            candle = candles[-2]
            update_posisi(state, pos, candle)
        except Exception as e:
            st.tambah_log(state, f"Error update {pos['simbol']}: {type(e).__name__}: {e}", "error")

    # --- Coba buka posisi baru ---
    if buka_baru and not state.get("open_positions"):
        sinyal_list = muat_sinyal_layak(maks=3)
        if not sinyal_list:
            st.tambah_log(state, "Tidak ada sinyal layak saat ini", "info")
        else:
            # Ambil yang skor tertinggi
            terbaik = max(sinyal_list, key=lambda s: s.get("skor_bot") or 0)
            buka_posisi(state, terbaik)

    st.simpan(state)


def tampil_status(state: dict[str, Any]) -> None:
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
            print(
                f"  {p['simbol']} {arah}{partial} | entry={p.get('entry_avg') or '-'} | "
                f"filled={filled}/{total} pending={pending} | "
                f"notional={p.get('ukuran_terisi', 0):.2f}/{p['notional']:.2f} | "
                f"SL={p['sl']} TP={tp_eff or p['tp']}"
            )
            # Detail level
            for t in p["titik_grid"]:
                print(f"      {t['nama']:4} @ {t['harga']} → {t['status']}")
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
    parser.add_argument("--no-buka", action="store_true", help="Hanya update posisi, jangan buka baru")
    parser.add_argument("--interval", type=int, default=60, help="Detik antar siklus (default 60)")
    args = parser.parse_args()

    if args.reset:
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
