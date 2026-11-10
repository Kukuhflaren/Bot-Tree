"""Melihat SEMUA kontrak futures USDT di Bitget (tanpa filter volume) untuk mencari
komoditas, indeks, dan saham. Hanya membaca data publik."""
import penyaring as pn

PERSIS = {"CL", "NG", "XAU", "XAG", "SPX", "NDX", "DJI", "DXY", "VIX", "RUT", "HG", "GC", "SI", "BZ", "QQQ", "SPY"}
SEBAGIAN = ["GOLD", "SILVER", "OIL", "BRENT", "WTI", "COPPER", "US500", "SP500", "NAS100", "DOW", "PAXG", "XAUT"]

ex = pn.buat_exchange()
tickers = pn.ambil_semua_ticker(ex)

baris = []
for simbol, d in tickers.items():
    if simbol.endswith(":USDT"):
        baris.append((simbol.split("/")[0], d.get("quoteVolume") or 0, pn.ubah_persen(d)))
baris.sort(key=lambda b: b[1], reverse=True)
print(f"Total kontrak USDT: {len(baris)}")

print("\nKemungkinan komoditas / indeks (cocok dengan daftar kata kunci):")
cocok = [b for b in baris if b[0] in PERSIS or any(k in b[0] for k in SEBAGIAN)]
for nama, vol, ubah in cocok:
    u = f"{ubah:.2f}%" if ubah is not None else "-"
    print(f"  {nama:12} vol24j {vol / 1e6:9.2f} Juta   ubah {u}")
if not cocok:
    print("  (tidak ada yang cocok dengan kata kunci)")

print("\nSemua simbol dengan volume 24 jam >= 1 Juta USDT (urut volume terbesar):")
besar = [b[0] for b in baris if b[1] >= 1e6]
print(", ".join(besar))
print(f"\n({len(besar)} simbol)")
