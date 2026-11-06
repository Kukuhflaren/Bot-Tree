"""Fase 3: ambil candle dari Bitget (data publik, tanpa key)."""
import ccxt
import config


def exchange_publik():
    ex = ccxt.bitget({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "swap"},
    })
    # Daftar koin (spot/public/coins) tidak kita perlukan dan endpoint-nya bisa bermasalah,
    # jadi dilewati saat memuat data pasar.
    ex.has["fetchCurrencies"] = False
    return ex


def ambil_candle(ex, simbol, tf="5m", limit=300):
    """Mengembalikan list candle (dict: t, o, h, l, c, v). Data pasar publik tidak
    bergantung tipe akun, jadi dicoba tanpa parameter UTA dulu, lalu dengan UTA."""
    galat = []
    for params in ({}, {"uta": config.BITGET_UTA}):
        try:
            baris = ex.fetch_ohlcv(simbol, tf, None, limit, params)
            return [dict(t=r[0], o=r[1], h=r[2], l=r[3], c=r[4], v=r[5]) for r in baris]
        except Exception as e:
            galat.append(f"{type(e).__name__}: {e}")
    raise RuntimeError(" | ".join(galat))
