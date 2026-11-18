"""Mengambil judul berita terbaru dari Google News RSS (gratis, tanpa API key).
Hasil disimpan di cache (berita_cache.json) supaya tidak mengambil ulang terlalu sering.
Hanya membaca data. Tidak membuat order."""
import json
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus

import requests

FILE_CACHE = "berita_cache.json"
UMUR_CACHE_JAM = 3

# Kata kunci khusus untuk simbol yang namanya ambigu atau bukan kripto
KUERI_KHUSUS = {
    "CL": "crude oil WTI price", "BZ": "Brent crude oil price", "XAU": "gold price",
    "XAG": "silver price", "XAUT": "Tether Gold XAUT", "PAXG": "PAX Gold PAXG",
    "NATGAS": "natural gas price", "COPPER": "copper price", "XPT": "platinum price",
    "SPX": "S&P 500", "SP500": "S&P 500", "SPY": "SPY ETF S&P 500", "QQQ": "QQQ Nasdaq 100 ETF",
    "NDX": "Nasdaq 100", "SOXL": "SOXL semiconductor ETF", "SOXS": "SOXS semiconductor ETF",
    "SQQQ": "SQQQ Nasdaq inverse ETF", "OPENAI": "OpenAI", "ANTHROPIC": "Anthropic",
}


def kueri_untuk(nama):
    return KUERI_KHUSUS.get(nama.upper(), f"{nama} crypto OR stock")


def _muat_cache():
    try:
        with open(FILE_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _simpan_cache(cache):
    with open(FILE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _ambil_rss(nama, maks):
    url = ("https://news.google.com/rss/search?q=" + quote_plus(kueri_untuk(nama) + " when:1d")
           + "&hl=en-US&gl=US&ceid=US:en")
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"RSS error {r.status_code}")
    hasil = []
    for item in ET.fromstring(r.content).iter("item"):
        tgl = item.findtext("pubDate")
        try:
            tgl = parsedate_to_datetime(tgl).isoformat()
        except Exception:
            pass
        hasil.append({"judul": (item.findtext("title") or "").strip(), "sumber": item.findtext("source"),
                      "tanggal": tgl, "link": item.findtext("link")})
        if len(hasil) >= maks:
            break
    return hasil


def ambil_berita(nama, maks=3, paksa=False):
    """Mengembalikan (daftar_berita, dari_cache)."""
    cache, kunci = _muat_cache(), nama.upper()
    c = cache.get(kunci)
    if c and not paksa and time.time() - c["waktu"] < UMUR_CACHE_JAM * 3600 and len(c["berita"]) >= min(maks, len(c["berita"])):
        return c["berita"][:maks], True
    berita = _ambil_rss(nama, maks)
    cache[kunci] = {"waktu": time.time(), "berita": berita}
    _simpan_cache(cache)
    return berita, False


def ambil_banyak(daftar_nama, maks=3, jeda=1.5):
    """Mengembalikan {nama: {"berita": [...], "galat": None atau pesan}}. Jeda hanya untuk pengambilan baru."""
    hasil = {}
    for nama in daftar_nama:
        try:
            berita, dari_cache = ambil_berita(nama, maks)
            hasil[nama] = {"berita": berita, "galat": None}
            if not dari_cache:
                time.sleep(jeda)
        except Exception as e:
            hasil[nama] = {"berita": [], "galat": f"{type(e).__name__}: {e}"}
    return hasil


if __name__ == "__main__":
    import sys
    nama = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    for b in ambil_berita(nama, 5, paksa=True)[0]:
        print(f"- {b['judul']} | {b['sumber']} | {b['tanggal']}\n  {b['link']}")
