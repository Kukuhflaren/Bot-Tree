"""Eksperimen: AI sebagai PENILAI (second opinion) atas sinyal bot. Tidak membuat order.

Alur:
  1. Baca token pilihan dari daftar_ai.json (dibuat ai_pemilih.py) beserta arahnya.
  2. Bot menghitung semuanya dari candle 5m asli: skor, syarat masuk, titik grid, TP/SL, rasio TP:SL.
  3. K token dengan skor bot tertinggi dikirim ke AI sebagai ringkasan angka (bukan berita).
  4. AI memberi verdict MASUK / TUNGGU / TOLAK + alasan + risiko, hanya dari angka yang diberikan.
  5. Dicetak berdampingan dengan penilaian bot, dan dicatat di log_penilai.jsonl untuk dievaluasi nanti.

AI hanya memberi pendapat (veto/second opinion). Keputusan dan angka tetap dari bot.
Pakai:  python penilai_ai.py --jumlah 8"""
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


def rencana(a, arah):
    """Titik grid dengan TP, SL, dan rasio TP:SL (aturan yang sama dengan dashboard)."""
    p = a["harga"]
    ref = a["HL"] if arah > 0 else a["HH"]
    sl_h = ref - arah * config.SL_POINTS * p * 1e-4  # 1 poin = 0,01% harga
    hasil = []
    for nama, h in a["grid"]:
        sl_salah_sisi = (arah > 0 and sl_h >= h) or (arah < 0 and sl_h <= h)
        risiko = abs(h - sl_h) / h * 100
        hasil.append({"titik": nama, "harga": r(h), "jarak_persen": r(abs(h - p) / p * 100, 3),
                      "tp": r(h * (1 + arah * config.TP_PERCENT / 100)), "sl": r(sl_h),
                      "risiko_sl_persen": r(risiko, 3),
                      "rr": r(config.TP_PERCENT / risiko, 3) if risiko > 0 else None,
                      "sl_salah_sisi": sl_salah_sisi})
    return hasil


def snapshot(t, a):
    return {
        "simbol": t["nama"], "arah": "BULLISH" if t["arah"] > 0 else "BEARISH", "harga": r(a["harga"]),
        "atr_persen": r(a["atr"] / a["harga"] * 100, 3),
        "ubah_24j_persen": r(t["ubah_24j"], 3), "volume_24j_juta": r(t["vol_juta"], 3), "rasio_volume": r(t["rasio_vol"], 3),
        "skor_bot": a["mentah"], "zona": a["zona"], "lonjakan_ekstrem": a["ekstrem"],
        "komponen_dari_20": {n: v for n, v in a["rincian"]}, "rsi": r(a["rsi"], 3),
        "syarat": dict(zip(["tren", "ema", "macd", "dekat_sr"], a["dasar"] + [a["syarat"][3]])),
        "jarak_ke_sr_persen": r(a["jarak_sr"], 3), "jarak_ke_sr_atr": r(a["jarak_atr"], 3),
        "titik_grid": rencana(a, t["arah"]),
    }


def buat_prompt(snaps):
    return f"""Kamu penilai risiko untuk bot scalping grid futures USDT. Parameter bot: leverage {config.LEVERAGE:.0f}x, TP {config.TP_PERCENT}% dari harga titik masuk, SL {config.SL_POINTS:.0f} poin (1 poin = 0,01% harga) di luar HL/HH, biaya pulang-pergi sekitar {BIAYA_PP}% harga. Tiap token punya sampai 3 titik limit (grid); tiap titik memakai 25% modal.

Di bawah ini ringkasan ANGKA tiap token yang dihitung bot dari candle 5 menit asli. Tugasmu memberi second opinion (bukan memprediksi harga):
- verdict: "MASUK" (setup layak dicoba), "TUNGGU" (belum matang), atau "TOLAK" (risiko lebih besar dari peluang).
- keyakinan: 1 sampai 5.
- alasan: maksimal 20 kata, WAJIB menyebut angka dari data.
- risiko: risiko utama, maksimal 12 kata.
- titik_layak: daftar nama titik grid yang masuk akal (boleh kosong). Titik dengan sl_salah_sisi=true tidak valid.
Pertimbangkan: kesesuaian antar indikator, jarak ke S/R relatif ATR, rasio rr dan apakah TP cukup besar dibanding biaya {BIAYA_PP}% dan ATR, lonjakan ekstrem, likuiditas, dan bila banyak token sejenis atau satu tema, hitung sebagai satu taruhan.

ATURAN KERAS: pakai HANYA data di bawah. Jangan mengarang berita, harga, atau level. Jawab HANYA JSON valid:
{{"ringkasan":"satu kalimat tentang kondisi keseluruhan","hasil":[{{"simbol":"BTC","verdict":"TUNGGU","keyakinan":3,"alasan":"...","risiko":"...","titik_layak":["R1"]}}]}}

DATA:
""" + "\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in snaps)


def jalankan(k):
    ap.cek_jatah()
    token = muat_token()
    ex = dp.exchange_publik()
    print(f"Menghitung {len(token)} token dari candle 5m...")
    hasil = []
    for t in token:
        try:
            c = dp.ambil_candle(ex, t["simbol"], "5m", 300)[:-1]
            a = ik.analisis(c, t["arah"], config.NEAR_SR_PERCENT, config.SCORE_MIN, config.NEAR_MODE, config.NEAR_ATR_MULT)
            hasil.append((t, a))
        except Exception as e:
            print(f"  lewati {t['nama']}: {type(e).__name__}")
    hasil.sort(key=lambda x: (x[1]["layak"], x[1]["mentah"]), reverse=True)
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
        layak = "ya" if a["layak"] else "tdk"
        silang[(layak, "MASUK" if v == "MASUK" else "lain")] += 1
        print(f"{t['nama']:9} {s['arah']:8} {a['mentah']:>7} {layak:9} {v:7} {str(h.get('keyakinan', '-')):>5}  "
              f"{h.get('alasan')} | {h.get('risiko')}")
        rr = [g["rr"] for g in s["titik_grid"] if g["rr"] is not None]
        salah = sum(1 for g in s["titik_grid"] if g["sl_salah_sisi"])
        print(f"{'':9} titik grid: {len(s['titik_grid'])} | rr terbaik: {max(rr) if rr else '-'} | SL salah sisi: {salah} | "
              f"layak menurut AI: {h.get('titik_layak')}")
        log.append({"waktu": datetime.now(timezone.utc).isoformat(), "simbol": t["nama"], "arah": s["arah"],
                    "harga": s["harga"], "skor_bot": a["mentah"], "layak_bot": a["layak"], "verdict": v,
                    "keyakinan": h.get("keyakinan"), "alasan": h.get("alasan")})

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
