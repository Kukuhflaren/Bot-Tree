"""Cek kelayakan kerangka dengan data NYATA Bitget (hanya membaca, tidak membuat order).

Menjawab dua pertanyaan praktis untuk tiap token:
  1. Apakah ukuran order per setup (RISK_PER_SETUP_PCT x modal x leverage) memenuhi MINIMUM order bursa?
  2. Berapa ATR kelipatan jarak SL (SL_POINTS / SL_BUFFER_ATR)? Kalau lebih besar dari RISK_ATR_MAX,
     tidak akan ada titik grid yang valid.

Pakai:
    python cek_kelayakan.py                 (memakai watchlist.json)
    python cek_kelayakan.py BTC ETH SOL     (token pilihan sendiri)"""
import sys

import config
import data_pasar as dp
import indikator as ik
import risk
import universe as uni


def min_notional(m, harga):
    """Perkiraan nilai order minimum (USDT) dari data pasar ccxt. None kalau bursa tidak memberi datanya."""
    lim = (m or {}).get("limits") or {}
    min_cost = (lim.get("cost") or {}).get("min")
    min_amt = (lim.get("amount") or {}).get("min")
    ukuran = (m or {}).get("contractSize") or 1
    kandidat = []
    if min_cost:
        kandidat.append(float(min_cost))
    if min_amt:
        kandidat.append(float(min_amt) * harga * float(ukuran))
    return max(kandidat) if kandidat else None


def main():
    nama = [a.upper() for a in sys.argv[1:] if not a.startswith("--")] or uni.muat_watchlist() or ["BTC"]
    ex = dp.exchange_publik()
    try:
        ex.load_markets()
    except Exception as e:
        print(f"Catatan: data pasar (batas order minimum) gagal dimuat: {type(e).__name__}")

    margin, notional = risk.margin_per_setup(), risk.notional_per_setup()
    print(f"Modal {config.MODAL_USDT} USDT | alokasi {config.RISK_PER_SETUP_PCT}% -> margin per setup {margin:.3f} USDT "
          f"-> notional {notional:.3f} USDT @ {config.LEVERAGE:.0f}x")
    sl_teks = (f"{config.SL_BUFFER_ATR} x ATR" if config.SL_BUFFER_ATR > 0
               else f"{config.SL_POINTS:.0f} poin (1 poin = 0,01% harga)")
    print(f"SL di luar HL/HH: {sl_teks} | RISK_ATR boleh {config.RISK_ATR_MIN} - {config.RISK_ATR_MAX} | TP mode {config.TP_MODE}\n")

    ok_order, ok_sl, total, margin_perlu_maks = 0, 0, 0, 0.0
    for n in nama:
        sim = f"{n}/USDT:USDT"
        try:
            c = dp.ambil_candle(ex, sim, "5m", 300)[:-1]
        except Exception as e:
            print(f"{n:8} gagal ambil candle: {type(e).__name__}")
            continue
        total += 1
        p, atr = c[-1]["c"], ik.atr(c)
        buffer = config.SL_BUFFER_ATR * atr if config.SL_BUFFER_ATR > 0 else config.SL_POINTS * p * 1e-4
        buffer_atr = buffer / atr if atr > 0 else float("inf")
        mn = min_notional((getattr(ex, "markets", None) or {}).get(sim), p)
        if mn is None:
            order_txt, order_ok = "order minimum tidak diketahui", None
        else:
            perlu = mn / config.LEVERAGE
            margin_perlu_maks = max(margin_perlu_maks, perlu)
            order_ok = notional >= mn
            order_txt = f"order min ~{mn:.2f} USDT (margin {perlu:.2f}) -> {'CUKUP' if order_ok else 'TIDAK CUKUP'}"
            ok_order += 1 if order_ok else 0
        sl_ok = buffer_atr <= config.RISK_ATR_MAX
        ok_sl += 1 if sl_ok else 0
        print(f"{n:8} harga {p:<10.6g} ATR5m {atr / p * 100:.3f}% | buffer SL {buffer / p * 100:.3f}% = {buffer_atr:.1f} ATR "
              f"({'ok' if sl_ok else 'MELEBIHI RISK_ATR_MAX'}) | {order_txt}")

    print(f"\nRINGKASAN ({total} token)")
    print(f"  Ukuran setup memenuhi order minimum : {ok_order} dari {total}")
    print(f"  Buffer SL <= RISK_ATR_MAX           : {ok_sl} dari {total}")
    if margin_perlu_maks > margin:
        pct = margin_perlu_maks / config.MODAL_USDT * 100
        print(f"  Agar semua lolos minimum order, margin per setup minimal ~{margin_perlu_maks:.2f} USDT "
              f"= {pct:.0f}% dari modal (sekarang {config.RISK_PER_SETUP_PCT}%).")
    if ok_sl < total:
        print("  Sebagian token punya buffer SL lebih lebar dari RISK_ATR_MAX: titik grid mereka akan selalu ditolak.")
        print("  Opsi: SL_BUFFER_ATR (mis. 0.5) atau perkecil SL_POINTS, atau naikkan RISK_ATR_MAX.")


if __name__ == "__main__":
    main()
