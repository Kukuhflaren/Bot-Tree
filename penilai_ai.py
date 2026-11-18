"""Eksperimen: AI sebagai PENILAI (second opinion) atas sinyal bot. Tidak membuat order.

Alur:
  1. Ambil pilihan daftar_ai.json yang masih ada pada sisi sama di daftar_40.json.
  2. Bot menghitung semuanya dari candle 30m asli: skor, syarat masuk, titik grid, TP/SL, rasio TP:SL.
  3. K token dengan skor bot tertinggi dikirim ke AI sebagai ringkasan angka (bukan berita).
  4. AI memberi verdict MASUK / TUNGGU / TOLAK + alasan + risiko, hanya dari angka yang diberikan.
  5. Dicetak berdampingan dengan penilaian bot, dan dicatat di log_penilai.jsonl untuk dievaluasi nanti.

Perubahan penting:
  - TP bertahap di S/R lawan; 25% posisi yang terisi direalisasikan per level
  - SL tetap fixed poin di luar HL/HH
  - Titik valid hanya jika: tidak sl_salah_sisi, RR >= RR_MIN, risk_atr dalam [RISK_ATR_MIN, RISK_ATR_MAX]
  - VWAP + konfirmasi tren 30m ikut dalam syarat bot

AI hanya memberi pendapat (veto/second opinion). Keputusan dan angka tetap dari bot.
Pakai:  python penilai_ai.py --jumlah 8
"""
import json
import sys
from datetime import datetime, timezone

import ai_pemilih as ap
import config
import data_pasar as dp
import indikator as ik
import universe as uni

FILE_HASIL = "penilai_ai.json"
FILE_LOG = "log_penilai.jsonl"
BIAYA_PP = 0.12  # perkiraan biaya pulang-pergi (persen harga), fee taker 2 sisi


def r(x, n=5):
    """Bulatkan ke n angka signifikan (menghemat token)."""
    return None if x is None else float(f"{x:.{n}g}")


def muat_token():
    try:
        with open(ap.FILE_HASIL, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        raise SystemExit("daftar_ai.json belum ada. Jalankan dulu: python ai_pemilih.py")
    daftar_40_json = uni.muat_daftar_40()
    try:
        with open(uni.FILE_DAFTAR_40, encoding="utf-8") as f:
            data_40 = json.load(f)
    except FileNotFoundError:
        raise SystemExit("daftar_40.json belum ada. Jalankan dulu: python penyaring.py")
    pilihan = {}
    for sisi in ("bullish", "bearish"):
        pilihan[sisi] = {
            uni.base_simbol(k.get("simbol", ""))
            for k in d.get(sisi, [])
            if isinstance(k, dict) and isinstance(k.get("simbol"), str)
        }
    token = []
    ditolak = 0
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for k in data_40[kunci]:
            simbol = k["simbol"]
            if not uni.ada_di_daftar_40(simbol, arah, daftar_40_json) or uni.base_simbol(simbol) not in pilihan[kunci]:
                continue
            token.append({"simbol": simbol, "nama": simbol.split("/")[0], "arah": arah,
                          "ubah_24j": k["ubah_24j"], "vol_juta": k["vol_24j_usdt"] / 1e6,
                          "rasio_vol": k["rasio_vol"]})
    for sisi, arah in (("bullish", 1), ("bearish", -1)):
        ditolak += sum(
            1 for k in d.get(sisi, [])
            if not isinstance(k, dict) or not isinstance(k.get("simbol"), str)
            or not uni.ada_di_daftar_40(k["simbol"], arah, daftar_40_json)
        )
    if ditolak:
        print(f"Universe: {ditolak} kandidat daftar_ai ditolak karena tidak ada di daftar_40 sisi yang sama.")
    return token


# [FASE B] TP sesuai TP_MODE; SL bisa berbasis poin atau ATR
def tp_untuk(a, arah, h):
    """Harga TP untuk titik masuk h. None = tidak ada level nyata (titik ditolak)."""
    if config.TP_MODE == "persen":
        return h * (1 + arah * config.TP_PERCENT / 100)
    if config.TP_MODE == "struktur":
        return a["HH"] if arah > 0 else a["HL"]
    lawan = a["level_atas"] if arah > 0 else a["level_bawah"]  # S/R lawan terdekat (level nyata)
    sesuai = [level for level in lawan if level > h] if arah > 0 else [level for level in lawan if level < h]
    sesuai.sort(reverse=arah < 0)
    return sesuai[0] if sesuai else None


def tp_levels_untuk(a, arah, h):
    """Target bertahap; tiap level berikutnya dapat merealisasikan 25% notional."""
    if config.TP_MODE == "persen":
        target = tp_untuk(a, arah, h)
        return [target] if target is not None else []
    if config.TP_MODE == "struktur":
        target = tp_untuk(a, arah, h)
        return [target] if target is not None else []
    lawan = a["level_atas"] if arah > 0 else a["level_bawah"]
    sesuai = [level for level in lawan if level > h] if arah > 0 else [level for level in lawan if level < h]
    return sorted(set(sesuai), reverse=arah < 0)


def buffer_sl(a):
    """Jarak SL di luar HL/HH dalam satuan harga."""
    if config.SL_BUFFER_ATR > 0:
        return config.SL_BUFFER_ATR * (a.get("atr") or 0.0)
    return config.SL_POINTS * a["harga"] * 1e-4  # 1 poin = 0,01% harga


def rencana(a, arah, rr_min=None, risk_atr_min=None, risk_atr_max=None):
    """Titik grid dengan TP (sesuai TP_MODE) dan SL di luar HL/HH.

    Bullish: SL = HL - buffer     Bearish: SL = HH + buffer
    Titik ditolak (valid=False) jika:
      - tidak ada TP nyata (mode sr_lawan tanpa level lawan)
      - SL berada di sisi yang salah relatif entry
      - risk atau reward <= 0
      - RR < rr_min
      - risk_atr di luar [risk_atr_min, risk_atr_max]
    Kolom "tolak" berisi alasan penolakan."""
    if rr_min is None:
        rr_min = config.RR_MIN
    if risk_atr_min is None:
        risk_atr_min = config.RISK_ATR_MIN
    if risk_atr_max is None:
        risk_atr_max = config.RISK_ATR_MAX

    p = a["harga"]
    atr = a.get("atr") or 0.0
    ref = a["HL"] if arah > 0 else a["HH"]
    sl_h = ref - arah * buffer_sl(a)

    hasil = []
    for nama, h in a["grid"]:
        tp_levels = tp_levels_untuk(a, arah, h)
        tp_h = tp_levels[0] if tp_levels else None
        tolak = []
        if arah > 0:
            sl_salah_sisi = sl_h >= h
            risk = h - sl_h
            reward = (tp_h - h) if tp_h is not None else None
        else:
            sl_salah_sisi = sl_h <= h
            risk = sl_h - h
            reward = (h - tp_h) if tp_h is not None else None

        risiko_persen = (risk / h * 100) if h > 0 else 0.0
        reward_persen = (reward / h * 100) if (reward is not None and h > 0) else None
        risk_atr = (risk / atr) if atr > 0 else None

        rr = None
        if tp_h is None:
            tolak.append("tanpa TP nyata")
        if sl_salah_sisi:
            tolak.append("SL salah sisi")
        if risk <= 0 or (reward is not None and reward <= 0):
            tolak.append("geometri rusak")
        elif reward is not None and not sl_salah_sisi:
            rr = reward / risk
            if rr < rr_min:
                tolak.append(f"RR {rr:.2f} < {rr_min}")
            if risk_atr is not None and risk_atr < risk_atr_min:
                tolak.append(f"risk_atr {risk_atr:.2f} < {risk_atr_min}")
            if risk_atr is not None and risk_atr > risk_atr_max:
                tolak.append(f"risk_atr {risk_atr:.2f} > {risk_atr_max}")

        hasil.append({
            "titik": nama,
            "harga": r(h),
            "jarak_persen": r(abs(h - p) / p * 100, 3),
            "tp": r(tp_h) if tp_h is not None else None,
            "tp_levels": [r(level) for level in tp_levels],
            "sl": r(sl_h),
            "risiko_sl_persen": r(risiko_persen, 3),
            "reward_persen": r(reward_persen, 3) if reward_persen is not None else None,
            "rr": r(rr, 3) if rr is not None else None,
            "risk_atr": r(risk_atr, 3) if risk_atr is not None else None,
            "sl_salah_sisi": sl_salah_sisi,
            "valid": not tolak,
            "tolak": tolak,
        })
    return hasil


GATE_NAMES = (
    "trend_structure", "ema", "macd", "near_sr", "vwap", "trend_30m",
    "extreme_candle", "minimum_score", "grid_available", "valid_risk_reward_grid",
)


def kegagalan_gate(a, valid_grid):
    """Kembalikan semua gate yang gagal; hitungan antar-gate dapat saling tumpang tindih."""
    syarat = a.get("syarat", [])
    lolos = {
        nama: bool(syarat[i]) if i < len(syarat) else False
        for i, nama in enumerate(GATE_NAMES[:6])
    }
    lolos.update({
        "extreme_candle": not bool(a.get("ekstrem")),
        "minimum_score": a.get("mentah", 0) >= config.SCORE_MIN,
        "grid_available": bool(a.get("grid")),
        "valid_risk_reward_grid": bool(valid_grid),
    })
    return [nama for nama in GATE_NAMES if not lolos[nama]]


def snapshot(t, a):
    grid = rencana(a, t["arah"])
    valid_grid = [g for g in grid if g["valid"]]
    # Nama syarat harus selaras dengan urutan di indikator.analisis()
    nama_syarat = ["tren", "ema", "macd", "dekat_sr", "vwap", "tren_30m"]
    syarat_dict = {}
    for i, nama in enumerate(nama_syarat):
        if i < len(a["syarat"]):
            syarat_dict[nama] = a["syarat"][i]

    risk_atrs = [g["risk_atr"] for g in valid_grid if g.get("risk_atr") is not None]
    return {
        "simbol": t["nama"],
        "candle_timeframe": "30m",
        "candle_timestamp": a.get("candle_timestamp"),
        "arah": "BULLISH" if t["arah"] > 0 else "BEARISH",
        "harga": r(a["harga"]),
        "atr_persen": r(a["atr"] / a["harga"] * 100, 3),
        "ubah_24j_persen": r(t["ubah_24j"], 3),
        "volume_24j_juta": r(t["vol_juta"], 3),
        "rasio_volume": r(t["rasio_vol"], 3),
        "skor_bot": a["mentah"],
        "zona": a["zona"],
        "lonjakan_ekstrem": a["ekstrem"],
        "komponen_dari_20": {n: v for n, v in a["rincian"]},
        "rsi": r(a["rsi"], 3),
        "vwap": r(a.get("vwap")),
        "di_atas_vwap": a.get("di_atas_vwap"),
        "vwap_ok": a.get("vwap_ok"),
        "tren_30m": {
            "ok": a.get("tren_30m", {}).get("ok"),
            "arah_30m": a.get("tren_30m", {}).get("arah_30m"),
            "candle_sesuai": a.get("tren_30m", {}).get("candle_sesuai"),
        },
        "syarat": syarat_dict,
        "jarak_ke_sr_persen": r(a["jarak_sr"], 3),
        "jarak_ke_sr_atr": r(a["jarak_atr"], 3),
        "tp_mode": config.TP_MODE,
        "tp_fraction_per_level": 0.25,
        "titik_grid": grid,
        "titik_valid": len(valid_grid),
        "rr_terbaik": r(max((g["rr"] for g in valid_grid if g["rr"] is not None), default=None), 3),
        "risk_atr_min_valid": r(min(risk_atrs), 3) if risk_atrs else None,
        # Bot hanya layak jika indikator layak DAN minimal 1 titik grid lolos semua filter
        "layak_bot_final": bool(a["layak"] and len(valid_grid) >= 1),
    }


def _teks_sl():
    if config.SL_BUFFER_ATR > 0:
        return f"{config.SL_BUFFER_ATR} x ATR"
    return f"{config.SL_POINTS:.0f} poin (1 poin = 0,01% harga)"


def buat_prompt(snaps):
    return f"""Kamu penilai risiko untuk bot scalping grid futures USDT.
Parameter bot:
- leverage {config.LEVERAGE:.0f}x
- TP mode "{config.TP_MODE}" (sr_lawan = target bertahap pada S/R lawan; struktur = di HH/HL; persen = {config.TP_PERCENT}% dari entry)
- tiap level TP merealisasikan 25% dari posisi yang terisi saat target pertama tercapai; sisa tetap terbuka sampai target berikutnya atau SL
- SL di luar HL/HH dengan jarak {_teks_sl()}
- RR minimum per titik grid = {config.RR_MIN}
- risk (jarak entry→SL) harus antara {config.RISK_ATR_MIN}× dan {config.RISK_ATR_MAX}× ATR (menolak SL terlalu sempit/lebar)
- biaya pulang-pergi sekitar {BIAYA_PP}% harga
- tiap titik limit memakai sebagian modal

Di bawah ini ringkasan ANGKA tiap token yang dihitung bot dari candle 30 menit asli.
Tugasmu memberi second opinion (bukan memprediksi harga):
- verdict: "MASUK" (setup layak dicoba), "TUNGGU" (belum matang), atau "TOLAK" (risiko lebih besar dari peluang).
- keyakinan: 1 sampai 5.
- alasan: maksimal 20 kata, WAJIB menyebut angka dari data.
- risiko: risiko utama, maksimal 12 kata.
- titik_layak: daftar nama titik grid yang valid=true saja (boleh kosong).

Pertimbangkan:
- hanya titik dengan valid=true yang boleh dipilih
- RR tinggi saja TIDAK cukup jika risk_atr terlalu kecil (mudah kena noise)
- VWAP dan tren_30m harus mendukung arah
- jarak ke S/R relatif ATR
- lonjakan ekstrem
- likuiditas

ATURAN KERAS: pakai HANYA data di bawah. Jangan mengarang berita, harga, atau level. Jawab HANYA JSON valid:
{{"ringkasan":"satu kalimat tentang kondisi keseluruhan","hasil":[{{"simbol":"BTC","verdict":"TUNGGU","keyakinan":3,"alasan":"...","risiko":"...","titik_layak":["R1"]}}]}}

DATA:
""" + "\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in snaps)


def jalankan(k, pakai_ai=None):
    pakai_ai = config.AI_ENABLED if pakai_ai is None else pakai_ai
    if pakai_ai:
        ap.cek_jatah()
    token = muat_token()
    if not token:
        raise SystemExit("Tidak ada kandidat daftar_ai yang masih menjadi anggota daftar_40.")
    ex = dp.exchange_publik()
    print(f"Menghitung {len(token)} token dari candle 30m...")
    print(
        f"Aturan: TP {config.TP_MODE} | SL {_teks_sl()} | "
        f"RR min {config.RR_MIN} | risk ATR [{config.RISK_ATR_MIN}, {config.RISK_ATR_MAX}]\n"
    )
    hasil = []
    galat_data = 0
    for t in token:
        try:
            c = dp.ambil_candle(ex, t["simbol"], "30m", 300)[:-1]
            a = ik.analisis(c, t["arah"], config.NEAR_SR_PERCENT, config.SCORE_MIN, config.NEAR_MODE, config.NEAR_ATR_MULT, c30=c)
            hasil.append((t, a))
        except Exception as e:
            print(f"  lewati {t['nama']}: {type(e).__name__}: {e}")
            galat_data += 1
    gate_counts = {nama: 0 for nama in GATE_NAMES}
    for t, a in hasil:
        valid_grid = [g for g in rencana(a, t["arah"]) if g["valid"]]
        for nama in kegagalan_gate(a, valid_grid):
            gate_counts[nama] += 1
    print("Penolakan per gate (dapat tumpang tindih):")
    for nama, jumlah in gate_counts.items():
        print(f"  {nama}: {jumlah}")
    print(f"  data_or_runtime_error: {galat_data}")
    if not hasil:
        raise SystemExit("Tidak ada kandidat berhasil dianalisis; AI tidak dipanggil.")
    # Urutkan: yang punya titik valid + layak di depan
    def kunci_urut(item):
        t, a = item
        grid = rencana(a, t["arah"])
        n_valid = sum(1 for g in grid if g["valid"])
        return (a["layak"] and n_valid >= 1, n_valid, a["mentah"])

    hasil.sort(key=kunci_urut, reverse=True)
    terpilih = hasil[:k]
    snaps = [snapshot(t, a) for t, a in terpilih]

    if pakai_ai:
        try:
            teks, jumlah_token = ap.panggil_ai(buat_prompt(snaps))
        except Exception as e:
            raise SystemExit(f"\nAI gagal: {type(e).__name__}: {str(e)[:200]}")
        ap.catat_pakai(jumlah_token)
        jawaban = ap.ambil_json(teks)
    else:
        jumlah_token = 0
        jawaban = {"ringkasan": "AI dinonaktifkan; hasil hanya berisi analisis bot.", "hasil": []}
    peta = {str(h.get("simbol", "")).upper(): h for h in jawaban.get("hasil", [])}

    print(f"\nRingkasan {'AI' if pakai_ai else 'bot'}: {jawaban.get('ringkasan')}")
    print(
        f"\n{'Simbol':9} {'Arah':8} {'SkorBot':>7} {'BotLayak':9} "
        f"{'AI' if pakai_ai else 'AI off':7} {'Yakin':>5}  Alasan | Risiko"
    )
    silang = {("ya", "MASUK"): 0, ("ya", "lain"): 0, ("tdk", "MASUK"): 0, ("tdk", "lain"): 0}
    log = []
    for (t, a), s in zip(terpilih, snaps):
        h = peta.get(t["nama"].upper(), {})
        v = h.get("verdict", "-")
        layak = "ya" if s["layak_bot_final"] else "tdk"
        silang[(layak, "MASUK" if v == "MASUK" else "lain")] += 1
        print(f"{t['nama']:9} {s['arah']:8} {a['mentah']:>7} {layak:9} {v:7} {str(h.get('keyakinan', '-')):>5}  "
              f"{h.get('alasan')} | {h.get('risiko')}")
        n_salah = sum(1 for g in s["titik_grid"] if g["sl_salah_sisi"])
        n_valid = s["titik_valid"]
        print(f"{'':9} grid: {len(s['titik_grid'])} total, {n_valid} valid | "
              f"rr terbaik: {s['rr_terbaik'] if s['rr_terbaik'] is not None else '-'} | "
              f"risk_atr min valid: {s.get('risk_atr_min_valid')} | "
              f"SL salah sisi: {n_salah} | "
              f"VWAP ok: {s.get('vwap_ok')} | tren30m: {s.get('tren_30m', {}).get('ok')} | "
              f"layak AI: {h.get('titik_layak')}")
        if pakai_ai:
            log.append({
                "waktu": datetime.now(timezone.utc).isoformat(),
                "simbol": t["nama"],
                "arah": s["arah"],
                "harga": s["harga"],
                "skor_bot": a["mentah"],
                "layak_bot": s["layak_bot_final"],
                "titik_valid": n_valid,
                "rr_terbaik": s["rr_terbaik"],
                "risk_atr_min_valid": s.get("risk_atr_min_valid"),
                "verdict": v,
                "keyakinan": h.get("keyakinan"),
                "alasan": h.get("alasan"),
            })

    if pakai_ai:
        print("\nPERBANDINGAN BOT vs AI")
        print(f"  Bot layak,  AI MASUK        : {silang[('ya', 'MASUK')]}")
        print(f"  Bot layak,  AI TUNGGU/TOLAK : {silang[('ya', 'lain')]}")
        print(f"  Bot tidak,  AI MASUK        : {silang[('tdk', 'MASUK')]}")
        print(f"  Bot tidak,  AI TUNGGU/TOLAK : {silang[('tdk', 'lain')]}")
    else:
        print("\nPerbandingan AI dilewati karena AI dinonaktifkan.")
    if jumlah_token:
        print(f"Token panggilan ini: {jumlah_token}")
    if pakai_ai:
        pakai = ap._baca_pakai()
        print(f"Pemakaian hari ini: {pakai['token']} token, {pakai['jumlah']} panggilan")
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump({
            "snapshot": snaps, "jawaban": jawaban, "token": jumlah_token,
            "ai_enabled": pakai_ai,
        }, f, indent=2, ensure_ascii=False)
    if pakai_ai:
        with open(FILE_LOG, "a", encoding="utf-8") as f:
            for baris in log:
                f.write(json.dumps(baris, ensure_ascii=False) + "\n")
        print(f"Tersimpan di {FILE_HASIL} dan ditambahkan ke {FILE_LOG}")
    else:
        print(f"Tersimpan di {FILE_HASIL}; AI tidak dipanggil dan log AI tidak diubah.")


if __name__ == "__main__":
    jumlah = 8
    if "--jumlah" in sys.argv:
        jumlah = int(sys.argv[sys.argv.index("--jumlah") + 1])
    pakai_ai = config.AI_ENABLED
    if "--pakai-ai" in sys.argv:
        pakai_ai = True
    if "--tanpa-ai" in sys.argv:
        pakai_ai = False
    jalankan(jumlah, pakai_ai=pakai_ai)
