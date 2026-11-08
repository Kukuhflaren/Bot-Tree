"""Fase 3: tes. Ambil candle 5m beberapa token, hitung skor, bandingkan dua versi syarat 'dekat S/R',
dan tampilkan titik grid (harus tidak kembar). Tidak membuat order."""
import config
import data_pasar as dp
import indikator as ik

SIMBOL = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]
ex = dp.exchange_publik()
terbaik = {}
n_persen = n_atr = 0

print(f"Versi PERSEN: jarak <= {config.NEAR_SR_PERCENT}% | Versi ATR: jarak <= {config.NEAR_ATR_MULT} x ATR\n")
for s in SIMBOL:
    try:
        c = dp.ambil_candle(ex, s, "5m", 300)[:-1]  # buang candle yang masih berjalan
    except Exception as e:
        print(f"{s}: gagal ambil candle: {e}")
        continue
    for arah, nama in ((1, "BULLISH"), (-1, "BEARISH")):
        a = ik.analisis(c, arah, config.NEAR_SR_PERCENT, config.SCORE_MIN, config.NEAR_MODE, config.NEAR_ATR_MULT)
        dasar = "".join("v" if ok else "x" for ok in a["dasar"])
        n_persen += a["layak_persen"]
        n_atr += a["layak_atr"]
        print(f"{s:14} {nama:7} skor {a['skor']:3} {a['zona']:15} dasar[tren,EMA,MACD]={dasar} | "
              f"PERSEN {a['jarak_sr']:.2f}% {'YA ' if a['layak_persen'] else 'tdk'} | "
              f"ATR {a['jarak_atr']:.1f}x {'YA ' if a['layak_atr'] else 'tdk'}")
        if s not in terbaik or a["mentah"] > terbaik[s][1]["mentah"]:
            terbaik[s] = (nama, a)

print(f"\nJumlah layak masuk: versi PERSEN = {n_persen}, versi ATR = {n_atr} (dari {2 * len(SIMBOL)} kombinasi)")

print("\nTitik grid (sisi dengan skor lebih tinggi per token):")
for s, (nama, a) in terbaik.items():
    p = a["harga"]
    titik = " | ".join(f"{n} {h:.4f} ({abs(h - p) / p * 100:.2f}%)" for n, h in a["grid"])
    print(f"  {s:14} {nama:7} harga {p} -> {titik if titik else 'tidak ada titik valid'}")

print("\nDiagnosa tren (2 puncak dan 2 lembah terakhir, jendela 5 candle; 1=naik, -1=turun, 0=campur):")
for s, (nama, a) in terbaik.items():
    ti = a["tren_info"]
    print(f"  {s:14} tren={ti['tren']:2} puncak {[round(x, 4) for x in ti['puncak']]} lembah {[round(x, 4) for x in ti['lembah']]}")
