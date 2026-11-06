"""Fase 3: tes. Ambil candle 5m beberapa token lalu hitung skor sinyal. Tidak membuat order."""
import config
import data_pasar as dp
import indikator as ik

SIMBOL = ["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT"]
ex = dp.exchange_publik()
detail = None

for s in SIMBOL:
    try:
        c = dp.ambil_candle(ex, s, "5m", 300)[:-1]  # buang candle yang masih berjalan
    except Exception as e:
        print(f"{s}: gagal ambil candle: {e}")
        continue
    for arah, nama in ((1, "BULLISH"), (-1, "BEARISH")):
        a = ik.analisis(c, arah, config.NEAR_SR_PERCENT, config.SCORE_MIN)
        tanda = "".join("v" if ok else "x" for ok in a["syarat"])
        print(f"{s:15} {nama:8} skor {a['skor']:3} {a['zona']:15} layak: {'YA ' if a['layak'] else 'tdk'} "
              f"syarat[tren,EMA,MACD,S/R]={tanda} jarakS/R={a['jarak_sr']:.2f}%")
        if detail is None:
            detail = (s, nama, a)

if detail:
    s, nama, a = detail
    print(f"\nRincian {s} {nama}: harga {a['harga']}, RSI {a['rsi']:.1f}")
    for k, v in a["rincian"]:
        print(f"  {k:7} {v}/20")
    print(f"  S1 {a['S1']:.4f} | S2 {a['S2']:.4f} | R1 {a['R1']:.4f} | R2 {a['R2']:.4f} | HL {a['HL']:.4f} | HH {a['HH']:.4f}")
