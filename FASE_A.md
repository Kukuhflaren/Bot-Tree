# Fase A — Fondasi risk & universe

Status: diimplementasikan di `config.py`, `risk.py`, `universe.py`, `watchlist.json`, `penyaring.py`, `cek_fase_a.py`.

## Ceklis

| Item | Status |
|------|--------|
| TOKEN_BLACKLIST (leveraged + equity-jam + komoditas umum) | Ya |
| RISK_ATR_MIN / RISK_ATR_MAX | Ya |
| Watchlist inti + WATCHLIST_MODE=only | Ya |
| MAX_OPEN_TOKENS=1 | Ya |
| RISK_PER_SETUP_PCT=5 (margin per setup) | Ya |
| Modul `boleh_order_baru` (kill, daily loss, consecutive, open) | Ya |
| Skrip verifikasi `cek_fase_a.py` | Ya |

## Perintah

```bash
# 1. Samakan .env dengan env.example (tambah baris baru)
# 2. Verifikasi lokal tanpa order
python cek_fase_a.py

# 3. Penyaring hanya watchlist crypto inti
python penyaring.py
```

## Size (contoh modal 10 USDT, 5%, lev 5x)

- Margin per setup = 0.5 USDT
- Notional ≈ 2.5 USDT
- Maks 1 token terbuka

## Berikutnya: Fase B

Kunci tertulis entry / SL / TP (S/R lawan) + konfirmasi 30m di spesifikasi dan kode indikator.
