"""Fase 4b: AI sebagai pemilih 20 bullish + 20 bearish.

Alur:
  1. Baca kandidat dari daftar_40.json (dibuat penyaring.py, berisi sekitar 100 token + datanya).
  2. Kirim ringkasan angka ke AI (hemat token: satu baris pendek per token).
  3. AI memilih 20 bullish + 20 bearish dan memberi alasan singkat.
  4. Hasil AI DIPERIKSA: simbol yang tidak ada di daftar dibuang, duplikat dibuang.
  5. Kalau kurang dari 20 atau AI error, sisanya diisi dari rumus penyaring (cadangan).
  6. Simpan ke daftar_ai.json.

Pakai:
    python ai_pemilih.py             -> pakai AI (memakai jatah panggilan harian)
    python ai_pemilih.py --tanpa-ai  -> hanya rumus penyaring (gratis, untuk uji)
Hanya memilih token. Tidak membuat order."""
import json
import sys
import time
from datetime import date, datetime, timezone

import requests

import config
import penyaring

FILE_KANDIDAT = penyaring.FILE_HASIL
FILE_HASIL = "daftar_ai.json"
FILE_PAKAI = "ai_pemakaian.json"
MODEL_BAWAAN = {"claude": "claude-haiku-5-5"}
WAKTU_TUNGGU = 420  # detik menunggu jawaban AI


# ---------- Jatah panggilan harian (menjaga biaya) ----------
def _baca_pakai():
    try:
        with open(FILE_PAKAI, encoding="utf-8") as f:
            d = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        d = {}
    hari_ini = date.today().isoformat()
    if d.get("tanggal") != hari_ini:
        d = {"tanggal": hari_ini, "jumlah": 0, "token": 0}
    d.setdefault("token", 0)
    return d


def cek_jatah():
    d = _baca_pakai()
    if d["jumlah"] >= config.AI_MAX_CALLS_PER_DAY:
        raise RuntimeError(f"Jatah panggilan AI hari ini habis ({d['jumlah']}/{config.AI_MAX_CALLS_PER_DAY})")
    if d["token"] >= config.AI_MAX_TOKENS_PER_HARI:
        raise RuntimeError(f"Jatah token AI hari ini habis ({d['token']}/{config.AI_MAX_TOKENS_PER_HARI})")


def catat_pakai(token=None):
    d = _baca_pakai()
    d["jumlah"] += 1
    d["token"] += token or 0
    with open(FILE_PAKAI, "w", encoding="utf-8") as f:
        json.dump(d, f)


# ---------- Prompt ----------
def buat_prompt(kandidat, n):
    baris = [
        f"{k['simbol'].split('/')[0]}|{k['ubah_24j']:.2f}|{k['rasio_vol']:.2f}|{k['vol_24j_usdt'] / 1e6:.1f}"
        for k in kandidat
    ]
    return f"""Kamu asisten penyaring token untuk bot scalping grid futures. Data di bawah adalah ringkasan 24 jam dari Bitget.
Format tiap baris: SIMBOL|ubah_harga_24j_persen|rasio_volume_vs_rata2_7hari|volume_24j_juta_USDT

TUGAS: dari daftar ini pilih tepat {n} token BULLISH (momentum naik) dan {n} token BEARISH (momentum turun) yang paling menarik untuk scalping grid. Pertimbangkan: kenaikan volume, besar perubahan harga, dan likuiditas (volume besar lebih baik). Satu token hanya boleh muncul di satu sisi.

ATURAN KERAS:
- Gunakan HANYA data di bawah. Jangan mengarang berita, harga, atau level support/resistance.
- Hanya pilih simbol yang ada di daftar.
- Alasan maksimal 12 kata, berdasarkan angka di data.
- Jawab HANYA dengan JSON valid, tanpa teks lain, bentuknya:
{{"bullish":[{{"simbol":"BTC","alasan":"...","keyakinan":1}}],"bearish":[{{"simbol":"ETH","alasan":"...","keyakinan":1}}]}}
- keyakinan adalah angka 1 sampai 5.

DATA:
""" + "\n".join(baris)


# ---------- Panggil AI ----------
def _post(url, **kw):
    """requests.post dengan ulang otomatis kalau server AI sedang sibuk (500/502/503/504).
    Kuota habis (429) TIDAK diulang, karena mengulang tidak membantu."""
    jeda = [10, 30, 60]  # detik menunggu sebelum percobaan ulang ke-1, ke-2, ke-3
    for i in range(len(jeda) + 1):
        r = requests.post(url, **kw)
        if r.status_code in (500, 502, 503, 504) and i < len(jeda):
            print(f"  Server AI sibuk ({r.status_code}), ulang dalam {jeda[i]} detik ({i + 1}/{len(jeda)})...")
            time.sleep(jeda[i])
            continue
        return r


def _ok(r):
    if r.status_code != 200:
        raise RuntimeError(f"AI error {r.status_code}: {r.text[:1500]}")
    return r.json()


def panggil_ai(prompt):
    prov = config.AI_PROVIDER
    kunci = config.AI_KEYS.get(prov, "")
    if not kunci:
        raise RuntimeError(f"API key untuk '{prov}' belum diisi di .env")
    model = config.AI_MODEL or MODEL_BAWAAN.get(prov, "")
    if not model:
        raise RuntimeError("AI_MODEL belum diisi di .env")

    if prov == "claude":
        r = _post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": kunci, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 4000, "messages": [{"role": "user", "content": prompt}]},
            timeout=WAKTU_TUNGGU,
        )
        data = _ok(r)
        u = data.get("usage", {})
        return data["content"][0]["text"], (u.get("input_tokens", 0) + u.get("output_tokens", 0)) or None

    if prov == "gemini":
        r = _post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": kunci, "content-type": "application/json"},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8000}},
            timeout=WAKTU_TUNGGU,
        )
        data = _ok(r)
        cand = data["candidates"][0]
        teks = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
        if not teks:
            raise RuntimeError(f"Gemini tidak mengembalikan teks (finishReason={cand.get('finishReason')})")
        return teks, data.get("usageMetadata", {}).get("totalTokenCount")

    if prov in ("gpt", "grok"):  # keduanya memakai format yang sama (kompatibel OpenAI)
        alamat = "https://api.openai.com/v1/chat/completions" if prov == "gpt" else "https://api.x.ai/v1/chat/completions"
        r = _post(
            alamat,
            headers={"Authorization": f"Bearer {kunci}", "content-type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            timeout=WAKTU_TUNGGU,
        )
        data = _ok(r)
        return data["choices"][0]["message"]["content"], data.get("usage", {}).get("total_tokens")

    raise RuntimeError(f"AI_PROVIDER '{prov}' tidak dikenal (pilih: gemini, claude, grok, gpt)")


# ---------- Periksa jawaban AI ----------
def ambil_json(teks):
    awal, akhir = teks.find("{"), teks.rfind("}")
    if awal < 0 or akhir < 0:
        raise ValueError("Jawaban AI bukan JSON.")
    return json.loads(teks[awal: akhir + 1])


def validasi(jawaban, kandidat, n):
    """Buang simbol yang tidak ada di daftar kandidat dan duplikat. Mengembalikan (bull, bear, dipakai)."""
    peta = {k["simbol"].split("/")[0].upper(): k for k in kandidat}
    dipakai = set()

    def ambil(daftar_ai):
        hasil = []
        for item in daftar_ai or []:
            nama = str(item.get("simbol", "")).split("/")[0].upper()
            if nama in peta and nama not in dipakai and len(hasil) < n:
                dipakai.add(nama)
                k = dict(peta[nama])
                k["alasan"] = str(item.get("alasan", ""))[:120]
                k["keyakinan"] = item.get("keyakinan")
                k["sumber"] = "ai"
                hasil.append(k)
        return hasil

    bull = ambil(jawaban.get("bullish"))
    bear = ambil(jawaban.get("bearish"))
    return bull, bear, dipakai


def isi_kekurangan(bull, bear, kandidat, n, dipakai):
    """Kalau ada sisi yang kurang dari n, isi dari rumus penyaring."""
    naik, turun = penyaring.susun_daftar(kandidat, len(kandidat))
    for daftar, cadangan in ((bull, naik), (bear, turun)):
        for k in cadangan:
            if len(daftar) >= n:
                break
            nama = k["simbol"].split("/")[0].upper()
            if nama not in dipakai:
                dipakai.add(nama)
                k = dict(k)
                k["alasan"], k["keyakinan"], k["sumber"] = "rumus penyaring", None, "rumus"
                daftar.append(k)


def muat_kandidat():
    try:
        with open(FILE_KANDIDAT, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit("daftar_40.json belum ada. Jalankan dulu: python penyaring.py")
    if not data.get("kandidat"):
        raise SystemExit("daftar_40.json belum berisi 'kandidat'. Pakai penyaring.py versi terbaru lalu jalankan ulang.")
    return data["kandidat"]


def jalankan(pakai_ai=True):
    kandidat = muat_kandidat()
    n = config.JUMLAH_PER_SISI
    sumber, galat, token = "rumus", None, None
    bull, bear, dipakai = [], [], set()
    if pakai_ai:
        try:
            cek_jatah()
            teks, token = panggil_ai(buat_prompt(kandidat, n))
            catat_pakai(token)
            bull, bear, dipakai = validasi(ambil_json(teks), kandidat, n)
            sumber = "ai"
        except Exception as e:
            galat = f"{type(e).__name__}: {e}"
            bull, bear, dipakai = [], [], set()
    isi_kekurangan(bull, bear, kandidat, n, dipakai)
    hasil = {"waktu": datetime.now(timezone.utc).isoformat(), "sumber": sumber, "galat": galat, "token": token,
             "bullish": bull, "bearish": bear}
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=2, ensure_ascii=False)
    return hasil


def cetak(judul, daftar):
    print(f"\n{judul} ({len(daftar)})")
    print(f"  {'No':>2} {'Simbol':16} {'Ubah24j':>9} {'Vol(Juta)':>10} {'Sumber':7} Alasan")
    for i, k in enumerate(daftar, 1):
        print(f"  {i:>2} {k['simbol']:16} {k['ubah_24j']:>8.2f}% {k['vol_24j_usdt'] / 1e6:>10.1f} "
              f"{k['sumber']:7} {k.get('alasan', '')}")


if __name__ == "__main__":
    h = jalankan(pakai_ai="--tanpa-ai" not in sys.argv)
    print(f"Sumber daftar: {h['sumber'].upper()}")
    if h.get("token"):
        pakai = _baca_pakai()
        print(f"Token panggilan ini: {h['token']} | hari ini: {pakai['token']}/{config.AI_MAX_TOKENS_PER_HARI} token, "
              f"{pakai['jumlah']}/{config.AI_MAX_CALLS_PER_DAY} panggilan")
    if h["galat"]:
        print(f"AI gagal, memakai rumus penyaring. Penyebab: {h['galat']}")
    cetak("BULLISH", h["bullish"])
    cetak("BEARISH", h["bearish"])
    dari_ai = sum(1 for k in h["bullish"] + h["bearish"] if k["sumber"] == "ai")
    print(f"\nDari AI: {dari_ai} | dari rumus: {len(h['bullish']) + len(h['bearish']) - dari_ai}")
    print(f"Tersimpan di {FILE_HASIL}")
