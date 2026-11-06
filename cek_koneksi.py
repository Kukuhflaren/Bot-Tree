"""Fase 2: tes koneksi. Hanya MEMBACA data, tidak membuat order."""
import ccxt
import config

print(f"Mode: {config.MODE} | UTA: {config.BITGET_UTA} | DRY_RUN: {config.DRY_RUN} | Modal: {config.MODAL_USDT} USDT")

# 1) Data publik (tanpa key)
pub = ccxt.bitget({"options": {"defaultType": "swap"}})
try:
    t = pub.fetch_ticker("BTC/USDT:USDT", {"uta": config.BITGET_UTA})
    print("Data publik OK. BTC terakhir:", t["last"])
except Exception as e:
    raise SystemExit(f"Gagal ambil data publik: {e}")

# 2) Login API (butuh key)
if not config.BITGET_API_KEY:
    raise SystemExit("API key belum diisi di .env, tes saldo dilewati.")

ex = ccxt.bitget({
    "apiKey": config.BITGET_API_KEY,
    "secret": config.BITGET_SECRET_KEY,
    "password": config.BITGET_PASSPHRASE,
    "options": {"defaultType": "swap"},
})
if config.MODE == "demo":
    ex.set_sandbox_mode(True)
    print("Memakai lingkungan DEMO (wajib Demo API Key).")

try:
    saldo = ex.fetch_balance({"uta": config.BITGET_UTA})
    tot = {a: v for a, v in (saldo.get("total") or {}).items() if v}
    print("Login API OK. Saldo (total, tidak nol):", tot if tot else "kosong / tidak terbaca")
except Exception as e:
    print(f"Login API gagal (cek key, secret, passphrase, izin, mode demo/live): {e}")
