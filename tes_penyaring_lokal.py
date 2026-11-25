"""Uji offline skor pullback dan saringan RWA. Tidak memanggil bursa."""
import penyaring


def test_skor_pullback_menurunkan_gerakan_jauh():
    dasar = {"rasio_vol": 1.5, "vol_24j_usdt": 50_000_000}
    tenang = penyaring.hitung_skor({**dasar, "ubah_24j": -4})
    liar = penyaring.hitung_skor({**dasar, "ubah_24j": -30})
    assert tenang > liar, (tenang, liar)
    print("[OK] skor pullback menurunkan gerakan 24j yang sudah jauh")


def test_rwa_dibuang_kecuali_watchlist():
    rows = [
        {"symbol": "BTCUSDT", "baseCoin": "BTC", "isRwa": "NO"},
        {"symbol": "NVDAUSDT", "baseCoin": "NVDA", "isRwa": "YES"},
        {"symbol": "TQQQUSDT", "baseCoin": "TQQQ", "isRwa": "YES"},
    ]
    rwa = penyaring.basis_rwa_dari_kontrak(rows)
    assert rwa == {"NVDA", "TQQQ"}
    tickers = {
        "BTC/USDT:USDT": {"quoteVolume": 20_000_000, "percentage": -2, "last": 1},
        "NVDA/USDT:USDT": {"quoteVolume": 20_000_000, "percentage": -6, "last": 1},
        "TQQQ/USDT:USDT": {"quoteVolume": 20_000_000, "percentage": -8, "last": 1},
        "USDC/USDT:USDT": {"quoteVolume": 90_000_000, "percentage": 0, "last": 1},
    }
    lama_min = penyaring.config.PENYARING_VOL_MIN_USDT
    lama_top = penyaring.config.PENYARING_TOP_VOLUME
    penyaring.config.PENYARING_VOL_MIN_USDT = 1
    penyaring.config.PENYARING_TOP_VOLUME = 10
    try:
        hasil, dibuang = penyaring.saring_likuid(tickers, ["NVDA"], rwa)
    finally:
        penyaring.config.PENYARING_VOL_MIN_USDT = lama_min
        penyaring.config.PENYARING_TOP_VOLUME = lama_top
    simbol = {k["simbol"] for k in hasil}
    assert "BTC/USDT:USDT" in simbol
    assert "NVDA/USDT:USDT" in simbol
    assert "TQQQ/USDT:USDT" not in simbol
    assert "USDC/USDT:USDT" not in simbol
    assert dibuang["rwa"] == 1
    print("[OK] RWA dibuang kecuali yang ada di watchlist")


if __name__ == "__main__":
    test_skor_pullback_menurunkan_gerakan_jauh()
    test_rwa_dibuang_kecuali_watchlist()
    print("All local screener tests passed")
