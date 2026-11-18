"""Tes CoinMarketCap Keyless Public API (tanpa API key). Hanya membaca data, tidak membuat order.
Tujuan: melihat bentuk respons asli (nama field) sebelum kita memutuskan memakainya.
Hasil lengkap disimpan di cmc_contoh.json."""
import json
import time

import requests

BASE = "https://pro-api.coinmarketcap.com/public-api"
ENDPOINT = [
    ("Fear and Greed", "/v3/fear-and-greed/latest", {}),
    ("Global metrics", "/v1/global-metrics/quotes/latest", {"convert": "USD"}),
    ("Altcoin season index", "/v1/altcoin-season-index/latest", {}),
    ("Listings (5 teratas)", "/v3/cryptocurrency/listings/latest", {"start": 1, "limit": 5, "convert": "USD"}),
]


def ambil(path, params, coba=4):
    """GET dengan jeda bertahap kalau kena batas laju (429)."""
    for i in range(coba):
        r = requests.get(BASE + path, params=params, headers={"Accept": "application/json"}, timeout=20)
        if r.status_code == 429 and i < coba - 1:
            jeda = 2 ** i
            print(f"  429 (terlalu sering), tunggu {jeda} detik...")
            time.sleep(jeda)
            continue
        return r


hasil = {}
for nama, path, params in ENDPOINT:
    print(f"\n=== {nama}  ({path})")
    try:
        r = ambil(path, params)
    except Exception as e:
        print(f"  gagal: {type(e).__name__}: {e}")
        continue
    print(f"  status: {r.status_code}")
    try:
        data = r.json()
    except ValueError:
        print("  bukan JSON:", r.text[:300])
        continue
    hasil[nama] = data
    teks = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    print("  " + teks[:700] + (" ..." if len(teks) > 700 else ""))
    time.sleep(1)

with open("cmc_contoh.json", "w", encoding="utf-8") as f:
    json.dump(hasil, f, indent=2, ensure_ascii=False)
print("\nTersimpan di cmc_contoh.json")
