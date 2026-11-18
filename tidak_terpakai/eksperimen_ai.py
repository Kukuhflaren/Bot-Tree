"""Eksperimen: Gemini + pencarian Google (berita nyata) vs hitungan bot.

Alur:
  1. Gemini mencari berita/data terbaru lewat Google Search, memilih N token bullish + N bearish,
     menilai skor seperti bot (RSI, EMA, MACD, SAR, candle, masing-masing 0-20), memperkirakan
     S/R, HH/HL, RSI, volume 24 jam, likuiditas, kelas aset, dan catatan risiko.
  2. Bot menghitung angka yang SAMA dari data Bitget (indikator.py) untuk token yang sama.
  3. Dicetak perbandingan AI vs bot, plus rincian token yang terpakai.

Angka bot adalah acuan (dihitung dari candle asli). Angka AI hanyalah perkiraan, jangan dipakai untuk order.

Pakai:  python eksperimen_ai.py --jumlah 5                (N per sisi, mulai dari kecil dulu)
        python eksperimen_ai.py --jumlah 5 --tanpa-cari   (tanpa pencarian Google, AI memakai pengetahuannya)
Hanya membaca data. Tidak membuat order."""
import json
import sys
from datetime import datetime, timezone
from time import time

import ai_pemilih as ap
import config
import data_pasar as dp
import indikator as ik
import penyaring as pn

WAKTU_TUNGGU = 600  # detik; pencarian web membuat jawaban lebih lama
FILE_HASIL = "eksperimen_ai.json"
KOMPONEN = ["RSI", "EMA", "MACD", "SAR", "Candle"]


def buat_prompt(n, cari=True):
    tanggal = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    instruksi = ("Gunakan Google Search untuk mencari berita dan data pasar TERBARU (24 jam terakhir)." if cari else
                 "Kamu TIDAK punya akses internet. Gunakan pengetahuanmu sendiri; isi berita dengan null kecuali kamu yakin.")
    return f"""Sekarang {tanggal}. Kamu analis untuk bot scalping grid futures USDT di Bitget (kripto, token saham/ETF, komoditas, indeks).
{instruksi}

TUGAS:
1. Pilih {n} token BULLISH dan {n} token BEARISH yang paling menarik untuk scalping grid hari ini: volume tinggi, likuiditas tinggi, perubahan harga 24 jam jelas, dan ada katalis berita. Satu token hanya di satu sisi.
2. Nilai tiap token seperti bot teknikal, 0-20 per komponen, searah dengan sisi pilihanmu:
   rsi (RSI14 timeframe 5m mendukung arah), ema (EMA9 vs EMA21 dan harga vs EMA9 searah), macd (histogram searah dan menguat), sar (SAR searah), candle (candle terakhir searah dan kuat).
   skor = jumlah kelima komponen (0-100).
3. Perkirakan angka berikut dalam harga USDT: harga, s1, s2 (support terdekat), r1, r2 (resistance terdekat), hh, hl (puncak dan lembah terakhir), rsi (angka RSI14 5m), volume_24j_juta (juta USDT).
4. likuiditas: "tinggi", "sedang", atau "rendah". kelas: "kripto", "saham", "etf", "komoditas", "indeks", atau "lainnya".
5. berita: satu kalimat maksimal 15 kata dari hasil pencarian (atau null). risiko: catatan risiko maksimal 10 kata, misalnya ETF berleverage, token baru melonjak, jam pasar tutup (atau null).

ATURAN KERAS:
- Jika tidak menemukan datanya, isi null. JANGAN mengarang angka atau berita.
- simbol hanya kode dasar (BTC, ETH, SOXL, CL), tanpa /USDT.
- Jawab HANYA JSON valid, tanpa teks lain, bentuknya:
{{"bullish":[{{"simbol":"BTC","skor":70,"komponen":{{"rsi":15,"ema":10,"macd":10,"sar":20,"candle":15}},"harga":0,"s1":0,"s2":0,"r1":0,"r2":0,"hh":0,"hl":0,"rsi":0,"volume_24j_juta":0,"likuiditas":"tinggi","kelas":"kripto","berita":null,"risiko":null}}],"bearish":[]}}"""


def panggil_gemini_cari(prompt, cari=True):
    if config.AI_PROVIDER != "gemini":
        raise SystemExit("Eksperimen ini hanya untuk AI_PROVIDER=gemini di .env")
    kunci = config.AI_KEYS.get("gemini", "")
    model = config.AI_MODEL_CARI if (cari and config.AI_MODEL_CARI) else config.AI_MODEL
    if not kunci or not model:
        raise SystemExit("Isi GEMINI_API_KEY dan AI_MODEL di .env")
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": 12000}}
    if cari:
        body["tools"] = [{"google_search": {}}]
    r = ap._post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": kunci, "content-type": "application/json"},
        json=body,
        timeout=WAKTU_TUNGGU,
    )
    data = ap._ok(r)
    cand = data["candidates"][0]
    teks = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    if not teks:
        raise RuntimeError(f"Gemini tidak mengembalikan teks (finishReason={cand.get('finishReason')})")
    return teks, data.get("usageMetadata", {}), cand.get("groundingMetadata", {})


def angka(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def pct(ai, bot):
    ai = angka(ai)
    return None if ai is None or not bot else (ai - bot) / bot * 100


def rata(daftar):
    d = [abs(x) for x in daftar if x is not None]
    return sum(d) / len(d) if d else None


def f(x, fmt="{:.2f}"):
    return "-" if x is None else fmt.format(x)


def bandingkan(item, arah, tickers, ex):
    nama = str(item.get("simbol", "")).split("/")[0].upper()
    simbol = f"{nama}/USDT:USDT"
    baris = {"simbol": nama, "arah": arah, "ai": item, "ada": simbol in tickers, "bot": None, "galat": None}
    if not baris["ada"]:
        return baris
    try:
        c = dp.ambil_candle(ex, simbol, "5m", 300)[:-1]
        a = ik.analisis(c, arah, config.NEAR_SR_PERCENT, config.SCORE_MIN, config.NEAR_MODE, config.NEAR_ATR_MULT)
        t = tickers[simbol]
        a["vol_juta"] = (t.get("quoteVolume") or 0) / 1e6
        baris["bot"] = a
    except Exception as e:
        baris["galat"] = f"{type(e).__name__}: {e}"
    return baris


def cetak_token(u, gm, detik):
    print(f"\nWaktu: {detik:.0f} detik")
    print(f"Token -> prompt: {u.get('promptTokenCount')} | jawaban: {u.get('candidatesTokenCount')} | "
          f"hasil pencarian: {u.get('toolUsePromptTokenCount')} | berpikir: {u.get('thoughtsTokenCount')} | "
          f"TOTAL: {u.get('totalTokenCount')}")
    kueri = gm.get("webSearchQueries", [])
    sumber = [c.get("web", {}).get("title") for c in gm.get("groundingChunks", []) if c.get("web")]
    print(f"Pencarian web: {len(kueri)} kueri, {len(sumber)} sumber")
    for q in kueri[:8]:
        print(f"  kueri: {q}")
    for s in dict.fromkeys(sumber[:8]):
        print(f"  sumber: {s}")


def jalankan(n, cari=True):
    ap.cek_jatah()
    model_dipakai = config.AI_MODEL_CARI if (cari and config.AI_MODEL_CARI) else config.AI_MODEL
    print(f"Model: {model_dipakai} | pencarian Google: {'ya' if cari else 'tidak'}")
    ex = pn.buat_exchange()
    mulai = time()
    teks, usage, gm = panggil_gemini_cari(buat_prompt(n, cari), cari)
    detik = time() - mulai
    ap.catat_pakai(angka(usage.get("totalTokenCount")))
    cetak_token(usage, gm, detik)
    jawaban = ap.ambil_json(teks)

    tickers = pn.ambil_semua_ticker(ex)
    hasil = []
    for kunci, arah in (("bullish", 1), ("bearish", -1)):
        for item in (jawaban.get(kunci) or [])[:n]:
            hasil.append(bandingkan(item, arah, tickers, ex))

    # --- Tabel 1: skor AI vs bot ---
    print(f"\n{'No':>2} {'Simbol':8} {'Arah':8} {'SkorAI':>6} {'SkorBot':>7} {'Selisih':>7}  {'Kelas':9} {'Likuid':7} Berita / Risiko")
    sel_skor, sel_komp = [], {k: [] for k in KOMPONEN}
    for i, b in enumerate(hasil, 1):
        ai, bot = b["ai"], b["bot"]
        skor_ai = angka(ai.get("skor"))
        skor_bot = bot["mentah"] if bot else None
        sel = (skor_ai - skor_bot) if skor_ai is not None and skor_bot is not None else None
        if sel is not None:
            sel_skor.append(sel)
        if bot:
            kom = ai.get("komponen") or {}
            for nama, nilai in bot["rincian"]:
                v = angka(kom.get(nama.lower()))
                if v is not None:
                    sel_komp[nama].append(v - nilai)
        catatan = " | ".join(x for x in (ai.get("berita"), ai.get("risiko")) if x)
        arah_t = "BULLISH" if b["arah"] > 0 else "BEARISH"
        status = "" if b["ada"] else "  [TIDAK ADA di Bitget]"
        print(f"{i:>2} {b['simbol']:8} {arah_t:8} {f(skor_ai, '{:.0f}'):>6} {f(skor_bot, '{:.0f}'):>7} "
              f"{f(sel, '{:+.0f}'):>7}  {str(ai.get('kelas')):9} {str(ai.get('likuiditas')):7} {catatan}{status}")

    # --- Tabel 2: level dan indikator (selisih AI terhadap bot, dalam persen) ---
    print(f"\n{'Simbol':8} {'Harga%':>7} {'RSI AI':>7} {'RSI bot':>8} {'S1%':>7} {'R1%':>7} {'HL%':>7} {'HH%':>7} {'Vol AI':>8} {'Vol bot':>8}  (selisih % = AI terhadap bot)")
    err = {"harga": [], "rsi": [], "s1": [], "r1": [], "hl": [], "hh": [], "vol": []}
    for b in hasil:
        ai, bot = b["ai"], b["bot"]
        if not bot:
            continue
        e = {"harga": pct(ai.get("harga"), bot["harga"]), "rsi": pct(ai.get("rsi"), bot["rsi"]),
             "s1": pct(ai.get("s1"), bot["S1"]), "r1": pct(ai.get("r1"), bot["R1"]),
             "hl": pct(ai.get("hl"), bot["HL"]), "hh": pct(ai.get("hh"), bot["HH"]),
             "vol": pct(ai.get("volume_24j_juta"), bot["vol_juta"])}
        for k, v in e.items():
            err[k].append(v)
        print(f"{b['simbol']:8} {f(e['harga'], '{:+.2f}'):>7} {f(angka(ai.get('rsi')), '{:.0f}'):>7} {bot['rsi']:>8.1f} "
              f"{f(e['s1'], '{:+.2f}'):>7} {f(e['r1'], '{:+.2f}'):>7} {f(e['hl'], '{:+.2f}'):>7} {f(e['hh'], '{:+.2f}'):>7} "
              f"{f(angka(ai.get('volume_24j_juta')), '{:.1f}'):>8} {bot['vol_juta']:>8.1f}")

    # --- Ringkasan ---
    ada = [b for b in hasil if b["ada"]]
    print(f"\nRINGKASAN ({len(hasil)} token dari AI)")
    print(f"  Ada di Bitget: {len(ada)} dari {len(hasil)}")
    print(f"  Rata-rata selisih skor |AI - bot|: {f(rata(sel_skor), '{:.1f}')} poin")
    print("  Rata-rata selisih per komponen (poin dari 20): " +
          ", ".join(f"{k} {f(rata(v), '{:.1f}')}" for k, v in sel_komp.items()))
    print("  Rata-rata galat AI terhadap bot (%): " +
          ", ".join(f"{k} {f(rata(v), '{:.2f}')}" for k, v in err.items()))
    setuju = [b for b in ada if b["bot"] and b["bot"]["mentah"] >= config.SCORE_MIN]
    print(f"  Skor bot untuk arah pilihan AI >= {config.SCORE_MIN:.0f}: {len(setuju)} dari {len(ada)}")
    print(f"  Layak masuk menurut bot (versi {config.NEAR_MODE}): "
          f"{sum(1 for b in ada if b['bot'] and b['bot']['layak_' + ('atr' if config.NEAR_MODE == 'atr' else 'persen')])}")
    try:
        with open(pn.FILE_HASIL, encoding="utf-8") as fh:
            dasar = json.load(fh)
        rumus = {k["simbol"].split("/")[0] for k in dasar["bullish"] + dasar["bearish"]}
        ai_set = {b["simbol"] for b in hasil}
        print(f"  Irisan dengan daftar rumus penyaring: {len(ai_set & rumus)} dari {len(ai_set)}")
    except Exception:
        pass
    total = angka(usage.get("totalTokenCount"))
    if total and hasil:
        print(f"  Token per token yang dinilai: sekitar {total / len(hasil):.0f}")
    pakai = ap._baca_pakai()
    print(f"  Pemakaian hari ini: {pakai['token']}/{config.AI_MAX_TOKENS_PER_HARI} token, "
          f"{pakai['jumlah']}/{config.AI_MAX_CALLS_PER_DAY} panggilan")

    with open(FILE_HASIL, "w", encoding="utf-8") as fh:
        json.dump({"waktu": datetime.now(timezone.utc).isoformat(), "usage": usage, "jawaban": jawaban},
                  fh, indent=2, ensure_ascii=False)
    print(f"\nTersimpan di {FILE_HASIL}")


if __name__ == "__main__":
    jumlah = 5
    if "--jumlah" in sys.argv:
        jumlah = int(sys.argv[sys.argv.index("--jumlah") + 1])
    jalankan(jumlah, "--tanpa-cari" not in sys.argv)
