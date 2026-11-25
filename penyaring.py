"""Penyaring tanpa AI + universe (blacklist + watchlist prefer/only).

WATCHLIST_MODE=prefer:
  Token di watchlist diutamakan masuk top N per sisi; token lain tetap bisa mengisi sisa slot.
WATCHLIST_MODE=only:
  Hanya token watchlist.
WATCHLIST_MODE=off:
  Tidak ada prioritas watchlist.

Skor mengurutkan kandidat pullback ke support/resistance, bukan pengejar gerakan 24 jam
terbesar. Kontrak isRwa (saham, ETF, komoditas sesi) dibuang kecuali ada di watchlist.
"""
import json
import math
import urllib.request
from datetime import datetime, timezone

import ccxt

import config
import universe as uni

FILE_HASIL = "daftar_40.json"
STABLECOIN = {"USDC", "USDE", "FDUSD", "TUSD", "DAI", "USDD"}
URL_KONTRAK = "https://api.bitget.com/api/v2/mix/market/contracts?productType=usdt-futures"


def buat_exchange():
    ex = ccxt.bitget({"enableRateLimit": True, "timeout": 20000, "options": {"defaultType": "swap"}})
    ex.has["fetchCurrencies"] = False
    return ex


def ambil_semua_ticker(ex):
    galat = []
    for params in ({}, {"productType": "USDT-FUTURES"}, {"uta": config.BITGET_UTA}):
        try:
            return ex.fetch_tickers(None, params)
        except Exception as e:
            galat.append(f"{type(e).__name__}: {e}")
    raise RuntimeError(" | ".join(galat))


def ubah_persen(t):
    if t.get("percentage") is not None:
        return t["percentage"]
    if t.get("open") and t.get("last"):
        return (t["last"] - t["open"]) / t["open"] * 100
    return None


def basis_rwa_dari_kontrak(rows) -> set[str]:
    """Base coin yang Bitget tandai isRwa=YES."""
    hasil = set()
    if not isinstance(rows, list):
        return hasil
    for row in rows:
        if not isinstance(row, dict) or str(row.get("isRwa", "")).upper() != "YES":
            continue
        base = str(row.get("baseCoin") or "").strip().upper()
        if base:
            hasil.add(base)
    return hasil


def ambil_basis_rwa() -> set[str]:
    """Kontrak saham/ETF/komoditas sesi. Kosong jika fitur mati atau daftar gagal dibaca."""
    if not config.EXCLUDE_RWA:
        return set()
    try:
        with urllib.request.urlopen(URL_KONTRAK, timeout=20) as resp:
            payload = json.load(resp)
        rows = payload.get("data") if isinstance(payload, dict) else None
        basis = basis_rwa_dari_kontrak(rows)
    except Exception as exc:
        print(
            f"Catatan: daftar kontrak RWA tidak terbaca ({type(exc).__name__}: {exc}). "
            "Saringan saham/ETF dilewati putaran ini."
        )
        return set()
    if not basis:
        print("Catatan: respons kontrak tidak berisi isRwa=YES. Saringan saham/ETF dilewati.")
    return basis


def saring_likuid(tickers, watchlist, rwa=None):
    hasil = []
    dibuang = {"blacklist": 0, "watchlist": 0, "volume": 0, "data": 0, "rwa": 0}
    rwa = {str(s).upper() for s in (rwa or set())}
    wl = {str(s).upper() for s in watchlist}
    for simbol, t in tickers.items():
        if not simbol.endswith(":USDT"):
            continue
        base = simbol.split("/")[0]
        if base in STABLECOIN:
            continue
        if base.upper() in rwa and base.upper() not in wl:
            dibuang["rwa"] += 1
            continue
        ok, alasan = uni.lolos_universe(base, watchlist)
        if not ok:
            if alasan == "blacklist":
                dibuang["blacklist"] += 1
            else:
                dibuang["watchlist"] += 1
            continue
        vol, ubah = t.get("quoteVolume"), ubah_persen(t)
        if vol is None or ubah is None or not t.get("last"):
            dibuang["data"] += 1
            continue
        if vol < config.PENYARING_VOL_MIN_USDT:
            dibuang["volume"] += 1
            continue
        hasil.append({"simbol": simbol, "harga": t["last"], "ubah_24j": ubah, "vol_24j_usdt": vol})
    hasil.sort(key=lambda k: k["vol_24j_usdt"], reverse=True)
    return hasil[: config.PENYARING_TOP_VOLUME], dibuang


def tambah_rasio_volume(ex, kandidat):
    gagal = 0
    for k in kandidat:
        try:
            harian = ex.fetch_ohlcv(k["simbol"], "1d", None, 9)
            tutup = harian[:-1][-7:]
            per_hari = [r[5] * r[4] for r in tutup]
            rata = sum(per_hari) / len(per_hari) if per_hari else 0
            k["rasio_vol"] = k["vol_24j_usdt"] / rata if rata > 0 else 1.0
        except Exception:
            gagal += 1
            k["rasio_vol"] = 1.0
    return kandidat, gagal


def hitung_skor(k):
    """Likuiditas dulu. Gerakan 24j yang sudah jauh dari UBAH_IDEAL_SKOR diturunkan.

    Daftar ini hanya kandidat untuk syarat 'dekat S/R'. Mengejar perubahan 24 jam
    terbesar mengisi daftar dengan token yang justru gagal di pintu itu.
    """
    ubah = abs(float(k.get("ubah_24j") or 0))
    ideal = config.UBAH_IDEAL_SKOR
    if ideal <= 0 or ubah <= ideal:
        faktor = 1.0
    else:
        faktor = ideal / ubah
    if config.UBAH_MAKS_SKOR > 0 and ubah > config.UBAH_MAKS_SKOR:
        faktor *= 0.25
    likuid = math.log10(max(float(k.get("vol_24j_usdt") or 0), 1e6) / 1e6) + 1
    rasio = min(float(k.get("rasio_vol") or 1.0), 3.0)
    return faktor * rasio * likuid * 100


def susun_daftar(kandidat, jumlah, watchlist):
    for k in kandidat:
        k["skor"] = hitung_skor(k)
        base = k["simbol"].split("/")[0].upper()
        k["prioritas_watchlist"] = base in {s.upper() for s in watchlist}
    naik = [k for k in kandidat if k["ubah_24j"] > 0]
    turun = [k for k in kandidat if k["ubah_24j"] < 0]
    return (
        uni.prioritaskan_watchlist(naik, watchlist, jumlah),
        uni.prioritaskan_watchlist(turun, watchlist, jumlah),
    )


def cetak(judul, daftar):
    print(f"\n{judul} ({len(daftar)})")
    print(f"  {'No':>2} {'Simbol':16} {'Harga':>14} {'Ubah24j':>9} {'Vol24j(Juta)':>13} {'RasioVol':>9} {'Skor':>7}  W")
    for i, k in enumerate(daftar, 1):
        tanda = " !" if abs(k["ubah_24j"]) >= 30 else ""
        w = "*" if k.get("prioritas_watchlist") else " "
        print(f"  {i:>2} {k['simbol']:16} {k['harga']:>14.6g} {k['ubah_24j']:>8.2f}% {k['vol_24j_usdt'] / 1e6:>13.1f} "
              f"{k['rasio_vol']:>8.2f}x {k['skor']:>7.2f}{tanda}  {w}")


def jalankan(ex=None):
    ex = ex or buat_exchange()
    wl = uni.muat_watchlist()
    tickers = ambil_semua_ticker(ex)
    rwa = ambil_basis_rwa()
    kandidat, dibuang = saring_likuid(tickers, wl, rwa)
    print(
        f"Total ticker: {len(tickers)} | lolos saring: {len(kandidat)} "
        f"| mode watchlist: {config.WATCHLIST_MODE} ({len(wl)} simbol)"
    )
    print(
        f"Dibuang — blacklist: {dibuang['blacklist']} | luar watchlist(only): {dibuang['watchlist']} "
        f"| saham/ETF/RWA: {dibuang['rwa']} | volume rendah: {dibuang['volume']} | data kosong: {dibuang['data']}"
    )
    kandidat, gagal = tambah_rasio_volume(ex, kandidat)
    if gagal:
        print(f"Catatan: {gagal} token gagal volume harian (rasio=1.0).")
    bull, bear = susun_daftar(kandidat, config.JUMLAH_PER_SISI, wl)
    hasil = {
        "waktu": datetime.now(timezone.utc).isoformat(),
        "watchlist_mode": config.WATCHLIST_MODE,
        "watchlist": wl,
        "bullish": bull,
        "bearish": bear,
        "kandidat": kandidat,
    }
    with open(FILE_HASIL, "w", encoding="utf-8") as f:
        json.dump(hasil, f, indent=2, ensure_ascii=False)
    return hasil


if __name__ == "__main__":
    h = jalankan()
    cetak("BULLISH", h["bullish"])
    cetak("BEARISH", h["bearish"])
    kurang = config.JUMLAH_PER_SISI * 2 - len(h["bullish"]) - len(h["bearish"])
    if kurang > 0:
        print(f"\nCatatan: daftar kurang {kurang} dari target {config.JUMLAH_PER_SISI * 2}.")
    print(f"\nTersimpan di {FILE_HASIL}")
    print("Kolom W=* artinya token ada di watchlist (diprioritaskan).")
