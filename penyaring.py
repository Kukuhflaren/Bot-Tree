"""Fase 4a: Penyaring tanpa AI.

Alur (5 langkah):
  1. Ambil data 24 jam SEMUA kontrak futures USDT dari Bitget (1 panggilan).
  2. Buang token yang kurang likuid (volume kecil) dan stablecoin, ambil N volume terbesar.
  3. Untuk N token itu, bandingkan volume 24 jam dengan rata-rata 7 hari sebelumnya (rasio volume).
  4. Beri skor = |perubahan harga 24 jam| x rasio volume (dibatasi maks 3x).
  5. Naik -> daftar BULLISH, turun -> daftar BEARISH. Simpan ke daftar_40.json.

Hanya MEMBACA data publik. Tidak membuat order."""
import json
from datetime import datetime, timezone

import math

import ccxt

import config

FILE_HASIL = "daftar_40.json"
STABLECOIN = {"USDC", "USDE", "FDUSD", "TUSD", "DAI", "USDD"}


def buat_exchange():
    ex = ccxt.bitget({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "swap"}})
    ex.has["fetchCurrencies"] = False  # tidak diperlukan, dan endpoint-nya pernah bermasalah
    return ex


# ---------- Langkah 1 ----------
def ambil_semua_ticker(ex):
    """Mencoba beberapa cara pemanggilan; kalau semua gagal, tampilkan semua galatnya."""
    galat = []
    for params in ({}, {"productType": "USDT-FUTURES"}, {"uta": config.BITGET_UTA}):
        try:
            return ex.fetch_tickers(None, params)
        except Exception as e:
            galat.append(f"{type(e).__name__}: {e}")
    raise RuntimeError(" | ".join(galat))


def ubah_persen(t):
    """Perubahan harga 24 jam (persen). Kalau tidak tersedia langsung, hitung dari harga buka."""
    if t.get("percentage") is not None:
        return t["percentage"]
    if t.get("open") and t.get("last"):
        return (t["last"] - t["open"]) / t["open"] * 100
    return None


# ---------- Langkah 2 ----------
def saring_likuid(tickers):
    hasil = []
    for simbol, t in tickers.items():
        if not simbol.endswith(":USDT"):  # hanya perpetual berkolateral USDT
            continue
        if simbol.split("/")[0] in STABLECOIN:
            continue
        vol, ubah = t.get("quoteVolume"), ubah_persen(t)
        if vol is None or ubah is None or not t.get("last"):
            continue  # data tidak lengkap -> lewati
        if vol < config.PENYARING_VOL_MIN_USDT:
            continue
        hasil.append({"simbol": simbol, "harga": t["last"], "ubah_24j": ubah, "vol_24j_usdt": vol})
    hasil.sort(key=lambda k: k["vol_24j_usdt"], reverse=True)  # volume terbesar di depan
    return hasil[: config.PENYARING_TOP_VOLUME]


# ---------- Langkah 3 ----------
def tambah_rasio_volume(ex, kandidat):
    gagal = 0
    for k in kandidat:
        try:
            harian = ex.fetch_ohlcv(k["simbol"], "1d", None, 9)
            tutup = harian[:-1][-7:]  # buang hari yang masih berjalan, ambil 7 hari terakhir
            # volume candle dalam koin; dikali harga tutup = perkiraan volume dalam USDT
            per_hari = [r[5] * r[4] for r in tutup]
            rata = sum(per_hari) / len(per_hari) if per_hari else 0
            k["rasio_vol"] = k["vol_24j_usdt"] / rata if rata > 0 else 1.0
        except Exception:
            gagal += 1
            k["rasio_vol"] = 1.0  # data tidak ada -> anggap volume normal
    return kandidat, gagal


# ---------- Langkah 4 dan 5 ----------
def hitung_skor(k):
    ubah = abs(k["ubah_24j"])
    if config.UBAH_MAKS_SKOR > 0:  # 0 = tidak dibatasi
        ubah = min(ubah, config.UBAH_MAKS_SKOR)
    # likuiditas: 1.0 di 1 juta USDT, 2.0 di 10 juta, 3.0 di 100 juta
    likuid = math.log10(max(k["vol_24j_usdt"], 1e6) / 1e6) + 1
    return ubah * min(k["rasio_vol"], 3.0) * likuid

def susun_daftar(kandidat, jumlah):
    for k in kandidat:
        k["skor"] = hitung_skor(k)
    naik = [k for k in kandidat if k["ubah_24j"] > 0]
    turun = [k for k in kandidat if k["ubah_24j"] < 0]
    urut = lambda daftar: sorted(daftar, key=lambda k: k["skor"], reverse=True)[:jumlah]
    return urut(naik), urut(turun)


def cetak(judul, daftar):
    print(f"\n{judul} ({len(daftar)})")
    print(f"  {'No':>2} {'Simbol':16} {'Ubah24j':>9} {'Vol24j(Juta)':>13} {'RasioVol':>9} {'Skor':>7}")
    for i, k in enumerate(daftar, 1):
        tanda = " !" if abs(k["ubah_24j"]) >= 30 else ""  # tanda "!" = perubahan ekstrem, hati-hati
        print(f"  {i:>2} {k['simbol']:16} {k['ubah_24j']:>8.2f}% {k['vol_24j_usdt'] / 1e6:>13.1f} "
              f"{k['rasio_vol']:>8.2f}x {k['skor']:>7.2f}{tanda}")


def jalankan(ex=None):
    ex = ex or buat_exchange()
    tickers = ambil_semua_ticker(ex)
    kandidat = saring_likuid(tickers)
    print(f"Total ticker: {len(tickers)} | lolos likuiditas (maks {config.PENYARING_TOP_VOLUME}): {len(kandidat)}")
    kandidat, gagal = tambah_rasio_volume(ex, kandidat)
    if gagal:
        print(f"Catatan: {gagal} token gagal diambil volume hariannya (rasio dianggap 1.0).")
    bull, bear = susun_daftar(kandidat, config.JUMLAH_PER_SISI)
    hasil = {"waktu": datetime.now(timezone.utc).isoformat(), "bullish": bull, "bearish": bear, "kandidat": kandidat}
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=2, ensure_ascii=False)
    return hasil


if __name__ == "__main__":
    h = jalankan()
    cetak("BULLISH", h["bullish"])
    cetak("BEARISH", h["bearish"])
    kurang = config.JUMLAH_PER_SISI * 2 - len(h["bullish"]) - len(h["bearish"])
    if kurang > 0:
        print(f"\nCatatan: daftar kurang {kurang} dari target {config.JUMLAH_PER_SISI * 2}. "
              "Wajar kalau pasar sedang sangat condong satu arah.")
    print(f"\nTersimpan di {FILE_HASIL}")
