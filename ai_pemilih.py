"""Fase 4b: AI sebagai pemilih dari daftar 20 bullish + 20 bearish.

Alur:
  1. Baca hanya daftar bullish dan bearish yang ditampilkan penyaring.py.
  2. Kirim ringkasan angka ke AI (hemat token: satu baris pendek per token).
  3. AI memilih 20 bullish + 20 bearish.
  4. Hasil AI DIPERIKSA: simbol yang tidak ada di daftar dibuang, duplikat dibuang.
  5. Kalau kurang dari 20 atau AI error, sisanya diisi dari rumus penyaring (cadangan).
  6. Simpan ke daftar_ai.json.

Pakai:
    python ai_pemilih.py             -> ikut USE_AI (default off)
    python ai_pemilih.py --pakai-ai  -> aktifkan AI untuk pemanggilan ini
    python ai_pemilih.py --tanpa-ai  -> paksa tanpa AI
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
def buat_prompt(bullish, bearish, n):
    def baris(daftar):
        return [
            f"{k['simbol'].split('/')[0]}|{k['ubah_24j']:.2f}|{k['rasio_vol']:.2f}|"
            f"{k['vol_24j_usdt'] / 1e6:.1f}"
            for k in daftar
        ]

    return f"""Kamu asisten penyaring token untuk bot scalping grid futures. Data di bawah adalah ringkasan 24 jam dari Bitget.
Format tiap baris: SIMBOL|ubah_harga_24j_persen|rasio_volume_vs_rata2_7hari|volume_24j_juta_USDT

TUGAS: pilih tepat {n} token BULLISH dari DAFTAR BULLISH dan {n} token BEARISH dari DAFTAR BEARISH. Pertimbangkan kenaikan volume, besar perubahan harga, dan likuiditas. Satu token hanya boleh muncul di satu sisi.

ATURAN KERAS:
- Gunakan HANYA data di bawah. Jangan mengarang berita, harga, atau level support/resistance.
- Jangan memindahkan token dari satu sisi ke sisi lainnya.
- Jawab HANYA dengan JSON valid, tanpa teks lain, bentuknya:
{{"bullish":[{{"simbol":"BTC"}}],"bearish":[{{"simbol":"ETH"}}]}}

DATA:
DAFTAR BULLISH:
""" + "\n".join(baris(bullish)) + "\nDAFTAR BEARISH:\n" + "\n".join(baris(bearish))


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


def validasi(jawaban, bullish_kandidat, bearish_kandidat, n):
    """Validasi jawaban terhadap daftar yang tampil pada sisi masing-masing."""
    peta_bull = {k["simbol"].split("/")[0].upper(): k for k in bullish_kandidat}
    peta_bear = {k["simbol"].split("/")[0].upper(): k for k in bearish_kandidat}
    dipakai = set()

    def ambil(daftar_ai, peta):
        hasil = []
        for item in daftar_ai or []:
            nama = str(item.get("simbol", "")).split("/")[0].upper()
            if nama in peta and nama not in dipakai and len(hasil) < n:
                dipakai.add(nama)
                k = dict(peta[nama])
                k.pop("alasan", None)
                k.pop("keyakinan", None)
                k["sumber"] = "ai"
                hasil.append(k)
        return hasil

    bull = ambil(jawaban.get("bullish"), peta_bull)
    bear = ambil(jawaban.get("bearish"), peta_bear)
    return bull, bear, dipakai


def isi_kekurangan(bull, bear, bullish_kandidat, bearish_kandidat, n, dipakai):
    """Isi kekurangan hanya dari daftar sisi yang sedang diproses."""
    for daftar, kandidat_sisi in ((bull, bullish_kandidat), (bear, bearish_kandidat)):
        for k in kandidat_sisi:
            if len(daftar) >= n:
                break
            nama = k["simbol"].split("/")[0].upper()
            if nama not in dipakai:
                dipakai.add(nama)
                k = dict(k)
                k.pop("alasan", None)
                k.pop("keyakinan", None)
                k["sumber"] = "rumus"
                daftar.append(k)


def muat_kandidat():
    try:
        with open(FILE_KANDIDAT, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise SystemExit("daftar_40.json belum ada. Jalankan dulu: python penyaring.py")
    try:
        bullish = data["bullish"]
        bearish = data["bearish"]
    except KeyError as exc:
        raise SystemExit("daftar_40.json belum berisi daftar bullish/bearish. Jalankan penyaring.py terlebih dahulu.") from exc
    if not bullish and not bearish:
        raise SystemExit("Daftar bullish dan bearish di daftar_40.json kosong.")
    watchlist = data.get("watchlist", [])
    if not isinstance(watchlist, list):
        raise SystemExit("watchlist di daftar_40.json harus berupa daftar.")
    metadata = {
        "watchlist_mode": data.get("watchlist_mode", config.WATCHLIST_MODE),
        "watchlist": [str(simbol).strip().upper() for simbol in watchlist if str(simbol).strip()],
    }
    return bullish, bearish, metadata


def jalankan(pakai_ai=None):
    pakai_ai = config.AI_ENABLED if pakai_ai is None else pakai_ai
    bullish_kandidat, bearish_kandidat, metadata = muat_kandidat()
    watchlist = set(metadata["watchlist"])

    def tandai_watchlist(daftar):
        for item in daftar:
            item.pop("alasan", None)
            item.pop("keyakinan", None)
            item["prioritas_watchlist"] = item["simbol"].split("/")[0].upper() in watchlist

    n = config.JUMLAH_PER_SISI
    sumber, galat, token = "rumus", None, None
    bull, bear, dipakai = [], [], set()
    if pakai_ai:
        try:
            cek_jatah()
            teks, token = panggil_ai(buat_prompt(bullish_kandidat, bearish_kandidat, n))
            catat_pakai(token)
            bull, bear, dipakai = validasi(ambil_json(teks), bullish_kandidat, bearish_kandidat, n)
            sumber = "ai"
        except Exception as e:
            galat = f"{type(e).__name__}: {e}"
            bull, bear, dipakai = [], [], set()
    isi_kekurangan(bull, bear, bullish_kandidat, bearish_kandidat, n, dipakai)
    tandai_watchlist(bull)
    tandai_watchlist(bear)
    hasil = {
        "waktu": datetime.now(timezone.utc).isoformat(),
        "sumber": sumber,
        "galat": galat,
        "token": token,
        "watchlist_mode": metadata["watchlist_mode"],
        "watchlist": metadata["watchlist"],
        "bullish": bull,
        "bearish": bear,
    }
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=2, ensure_ascii=False)
    return hasil


def cetak(judul, daftar):
    print(f"\n{judul} ({len(daftar)})")
    print(f"  {'No':>2} {'Simbol':16} {'Ubah24j':>9} {'Vol24j(Juta)':>13} {'RasioVol':>9} {'Skor':>7}  W")
    for i, k in enumerate(daftar, 1):
        tanda = " !" if abs(k["ubah_24j"]) >= 30 else ""
        w = "*" if k.get("prioritas_watchlist") else " "
        print(f"  {i:>2} {k['simbol']:16} {k['ubah_24j']:>8.2f}% {k['vol_24j_usdt'] / 1e6:>13.1f} "
              f"{k['rasio_vol']:>8.2f}x {k['skor']:>7.2f}{tanda}  {w}")


if __name__ == "__main__":
    pakai_ai = config.AI_ENABLED
    if "--pakai-ai" in sys.argv:
        pakai_ai = True
    if "--tanpa-ai" in sys.argv:
        pakai_ai = False
    h = jalankan(pakai_ai=pakai_ai)
    print(f"Sumber daftar: {h['sumber'].upper()}")
    if h.get("token"):
        pakai = _baca_pakai()
        print(f"Token panggilan ini: {h['token']} | hari ini: {pakai['token']}/{config.AI_MAX_TOKENS_PER_HARI} token, "
              f"{pakai['jumlah']}/{config.AI_MAX_CALLS_PER_DAY} panggilan")
    if h["galat"]:
        print(f"AI gagal, memakai rumus penyaring. Penyebab: {h['galat']}")
    cetak("BULLISH", h["bullish"])
    cetak("BEARISH", h["bearish"])
    print(f"\nWatchlist ({h['watchlist_mode']}): {', '.join(h['watchlist']) or '-'}")
    dari_ai = sum(1 for k in h["bullish"] + h["bearish"] if k["sumber"] == "ai")
    print(f"\nDari AI: {dari_ai} | dari rumus: {len(h['bullish']) + len(h['bearish']) - dari_ai}")
    print(f"Tersimpan di {FILE_HASIL}")
    print("Kolom W=* artinya token ada di watchlist (diprioritaskan).")
