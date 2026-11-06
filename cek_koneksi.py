"""Langkah 2: tes koneksi. Hanya MEMBACA data, tidak membuat order."""
import ccxt
import config

print(f"Mode: {config.MODE}")
ex = ccxt.bitget({
    "apiKey": config.BITGET_API_KEY,
    "secret": config.BITGET_SECRET_KEY,
    "password": config.BITGET_PASSPHRASE,
    "options": {"defaultType": "swap"},
})

try:
    t = ex.fetch_ticker("BTC/USDT:USDT", {"uta": config.BITGET_UTA})
    print("Data publik OK. BTC terakhir:", t["last"])
except Exception as e:
    raise SystemExit(f"Gagal ambil data publik: {e}")

if not config.BITGET_API_KEY:
    print("API key belum diisi di .env, lewati tes saldo.")
else:
    try:
        saldo = ex.fetch_balance({"uta": config.BITGET_UTA})
        print("Login API OK. USDT tersedia:", saldo.get("USDT", {}).get("free"))
    except Exception as e:
        print(f"Login API gagal (cek key, secret, passphrase, izin, IP): {e}")
