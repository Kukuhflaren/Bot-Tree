"""Eksperimen: AI sebagai PENILAI (second opinion) atas sinyal bot. Tidak membuat order.

Alur:
  1. Baca token pilihan dari daftar_ai.json (dibuat ai_pemilih.py) beserta arahnya.
  2. Bot menghitung semuanya dari candle 5m asli: skor, syarat masuk, titik grid, TP/SL, rasio TP:SL.
  3. K token dengan skor bot tertinggi dikirim ke AI sebagai ringkasan angka (bukan berita).
  4. AI memberi verdict MASUK / TUNGGU / TOLAK + alasan + risiko, hanya dari angka yang diberikan.
  5. Dicetak berdampingan dengan penilaian bot, dan dicatat di log_penilai.jsonl untuk dievaluasi nanti.

Perubahan penting:
  - TP bersama di HH (bullish) / HL (bearish), bukan persen fixed dari entry
  - SL tetap fixed poin di luar HL/HH
  - Titik dengan sl_salah_sisi atau RR < RR_MIN ditandai tidak valid
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
    token = []
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for k in d[kunci]:
            token.append({"simbol": k["simbol"], "nama": k["simbol"].split("/")[0], "arah": arah,
                          "ubah_24j": k["ubah_24j"], "vol_juta": k["vol_24j_usdt"] / 1e6,
                          "rasio_vol": k["rasio_vol"]})
    return token


def rencana(a, arah, rr_min=None):
    """Titik grid dengan TP bersama di HH/HL dan SL fixed poin di luar HL/HH.

    Bullish: TP = HH, SL = HL - (SL_POINTS * harga * 1e-4)
    Bearish: TP = HL, SL = HH + (SL_POINTS * harga * 1e-4)

    Titik ditolak (valid=False) jika:
      - SL berada di sisi yang salah relatif entry (sl_salah_sisi)
      - risk <= 0 atau reward <= 0 (geometri rusak)
      - RR < rr_min (default config.RR_MIN = 1.0)
    """
    if rr_min is None:
        rr_min = config.RR_MIN
    p = a["harga"]
    # TP bersama: semua grid ditutup saat harga menyentuh HH (long) atau HL (short)
    tp = a["HH"] if arah > 0 else a["HL"]
    # SL fixed poin di luar struktur HL/HH
    ref = a["HL"] if arah > 0 else a["HH"]
    sl_h = ref - arah * config.SL_POINTS * p * 1e-4  # 1 poin = 0,01% harga

    hasil = []
    for nama, h in a["grid"]:
        if arah > 0:
            sl_salah_sisi = sl_h >= h
            risk = h - sl_h
            reward = tp - h
        else:
            sl_salah_sisi = sl_h <= h
            risk = sl_h - h
            reward = h - tp

        risiko_persen = (risk / h * 100) if h > 0 else 0.0
        reward_persen = (reward / h * 100) if h > 0 else 0.0

        if risk <= 0 or reward <= 0:
            rr = None
            valid = False
        else:
            rr = reward / risk
            valid = (not sl_salah_sisi) and (rr >= rr_min)

        hasil.append({
            "titik": nama,
            "harga": r(h),
            "jarak_persen": r(abs(h - p) / p * 100, 3),
            "tp": r(tp),
            "sl": r(sl_h),
            "risiko_sl_persen": r(risiko_persen, 3),
            "reward_persen": r(reward_persen, 3),
            "rr": r(rr, 3) if rr is not None else None,
            "sl_salah_sisi": sl_salah_sisi,
            "valid": valid,
        })
    return hasil


def snapshot(t, a):
    grid = rencana(a, t["arah"])
    valid_grid = [g for g in grid if g["valid"]]
    # Nama syarat harus selaras dengan urutan di indikator.analisis()
    nama_syarat = ["tren", "ema", "macd", "dekat_sr", "vwap", "tren_30m"]
    syarat_dict = {}
    for i, nama in enumerate(nama_syarat):
        if i < len(a["syarat"]):
            syarat_dict[nama] = a["syarat"][i]

    return {
        "simbol": t["nama"],
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
        "tp_bersama": r(a["HH"] if t["arah"] > 0 else a["HL"]),
        "titik_grid": grid,
        "titik_valid": len(valid_grid),
        "rr_terbaik": r(max((g["rr"] for g in valid_grid if g["rr"] is not None), default=None), 3),
        # Bot hanya layak jika indikator layak DAN minimal 1 titik grid lolos RR_MIN
        "layak_bot_final": bool(a["layak"] and len(valid_grid) >= 1),
    }


def buat_prompt(snaps):
    return f"""Kamu penilai risiko untuk bot scalping grid futures USDT.
Parameter bot:
- leverage {config.LEVERAGE:.0f}x
- TP BERSAMA di HH (bullish) atau HL (bearish) — semua grid ditutup sekaligus saat harga menyentuh level itu
- SL fixed {config.SL_POINTS:.0f} poin (1 poin = 0,01% harga) di luar HL/HH
- RR minimum per titik grid = {config.RR_MIN}
- biaya pulang-pergi sekitar {BIAYA_PP}% harga
- tiap titik limit memakai sebagian modal

Di bawah ini ringkasan ANGKA tiap token yang dihitung bot dari candle 5 menit asli.
Tugasmu memberi second opinion (bukan memprediksi harga):
- verdict: "MASUK" (setup layak dicoba), "TUNGGU" (belum matang), atau "TOLAK" (risiko lebih besar dari peluang).
- keyakinan: 1 sampai 5.
- alasan: maksimal 20 kata, WAJIB menyebut angka dari data.
- risiko: risiko utama, maksimal 12 kata.
- titik_layak: daftar nama titik grid yang valid=true saja (boleh kosong).

Pertimbangkan:
- hanya titik dengan valid=true yang boleh dipilih
- RR harus >= {config.RR_MIN}
- VWAP dan tren_30m harus mendukung arah
- jarak ke S/R relatif ATR
- lonjakan ekstrem
- likuiditas

ATURAN KERAS: pakai HANYA data di bawah. Jangan mengarang berita, harga, atau level. Jawab HANYA JSON valid:
{{"ringkasan":"satu kalimat tentang kondisi keseluruhan","hasil":[{{"simbol":"BTC","verdict":"TUNGGU","keyakinan":3,"alasan":"...","risiko":"...","titik_layak":["R1"]}}]}}

DATA:
""" + "\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in snaps)


def jalankan(k):
    ap.cek_jatah()
    token = muat_token()
    ex = dp.exchange_publik()
    print(f"Menghitung {len(token)} token dari candle 5m...")
    print(f"Aturan: TP di HH/HL | SL {config.SL_POINTS:.0f} poin di luar struktur | RR min {config.RR_MIN}\n")
    hasil = []
    for t in token:
        try:
            c = dp.ambil_candle(ex, t["simbol"], "5m", 300)[:-1]
            a = ik.analisis(c, t["arah"], config.NEAR_SR_PERCENT, config.SCORE_MIN, config.NEAR_MODE, config.NEAR_ATR_MULT)
            hasil.append((t, a))
        except Exception as e:
            print(f"  lewati {t['nama']}: {type(e).__name__}: {e}")
    # Urutkan: yang punya titik valid + layak di depan
    def kunci_urut(item):
        t, a = item
        grid = rencana(a, t["arah"])
        n_valid = sum(1 for g in grid if g["valid"])
        return (a["layak"] and n_valid >= 1, n_valid, a["mentah"])

    hasil.sort(key=kunci_urut, reverse=True)
    terpilih = hasil[:k]
    snaps = [snapshot(t, a) for t, a in terpilih]

    try:
        teks, jumlah_token = ap.panggil_ai(buat_prompt(snaps))
    except Exception as e:
        raise SystemExit(f"\nAI gagal: {type(e).__name__}: {str(e)[:200]}")
    ap.catat_pakai(jumlah_token)
    jawaban = ap.ambil_json(teks)
    peta = {str(h.get("simbol", "")).upper(): h for h in jawaban.get("hasil", [])}

    print(f"\nRingkasan AI: {jawaban.get('ringkasan')}")
    print(f"\n{'Simbol':9} {'Arah':8} {'SkorBot':>7} {'BotLayak':9} {'AI':7} {'Yakin':>5}  Alasan | Risiko")
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
              f"SL salah sisi: {n_salah} | "
              f"VWAP ok: {s.get('vwap_ok')} | tren30m: {s.get('tren_30m', {}).get('ok')} | "
              f"layak AI: {h.get('titik_layak')}")
        log.append({
            "waktu": datetime.now(timezone.utc).isoformat(),
            "simbol": t["nama"],
            "arah": s["arah"],
            "harga": s["harga"],
            "skor_bot": a["mentah"],
            "layak_bot": s["layak_bot_final"],
            "titik_valid": n_valid,
            "rr_terbaik": s["rr_terbaik"],
            "verdict": v,
            "keyakinan": h.get("keyakinan"),
            "alasan": h.get("alasan"),
        })

    print("\nPERBANDINGAN BOT vs AI")
    print(f"  Bot layak,  AI MASUK        : {silang[('ya', 'MASUK')]}")
    print(f"  Bot layak,  AI TUNGGU/TOLAK : {silang[('ya', 'lain')]}")
    print(f"  Bot tidak,  AI MASUK        : {silang[('tdk', 'MASUK')]}")
    print(f"  Bot tidak,  AI TUNGGU/TOLAK : {silang[('tdk', 'lain')]}")
    if jumlah_token:
        print(f"Token panggilan ini: {jumlah_token}")
    pakai = ap._baca_pakai()
    print(f"Pemakaian hari ini: {pakai['token']} token, {pakai['jumlah']} panggilan")
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump({"snapshot": snaps, "jawaban": jawaban, "token": jumlah_token}, f, indent=2, ensure_ascii=False)
    with open(FILE_LOG, "a", encoding="utf-8") as f:
        for baris in log:
            f.write(json.dumps(baris, ensure_ascii=False) + "\n")
    print(f"Tersimpan di {FILE_HASIL} dan ditambahkan ke {FILE_LOG}")


if __name__ == "__main__":
    jumlah = 8
    if "--jumlah" in sys.argv:
        jumlah = int(sys.argv[sys.argv.index("--jumlah") + 1])
    jalankan(jumlah)
