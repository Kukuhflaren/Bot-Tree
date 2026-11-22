"""Cek kelayakan kerangka dengan data NYATA Bitget (hanya membaca, tidak membuat order).

Menjawab dua pertanyaan praktis untuk tiap token:
  1. Apakah ukuran order per setup (RISK_PER_SETUP_PCT x modal x leverage) memenuhi MINIMUM order bursa?
  2. Berapa ATR kelipatan jarak SL (SL_POINTS / SL_BUFFER_ATR)? Kalau lebih besar dari RISK_ATR_MAX,
     tidak akan ada titik grid yang valid.
Di akhir dicetak bagian "YANG PERLU DIPERBAIKI" lengkap dengan angka yang disarankan.

Pakai:
    python cek_kelayakan.py                 (semua token daftar_40; watchlist lebih dulu)
    python cek_kelayakan.py BTC ETH SOL     (token pilihan sendiri)"""
import math
import sys

import config
import data_pasar as dp
import indikator as ik
import risk
import universe as uni

JUMLAH_LEVEL = 3   # rencana jumlah level grid per setup (2-3); ubah sesuai rencanamu
CADANGAN = 1.2     # cadangan 20%: nilai order minimum (USDT) ikut bergerak mengikuti harga token


def susun_token(data: dict, watchlist: list[str]) -> list[str]:
    """Gabungkan kedua sisi daftar_40 tanpa duplikat, dengan watchlist lebih dulu."""
    semua = []
    terlihat = set()
    for sisi in ("bullish", "bearish"):
        for item in data[sisi]:
            nama = uni.base_simbol(item["simbol"])
            if nama not in terlihat:
                semua.append(nama)
                terlihat.add(nama)

    prioritas = []
    sudah_diprioritaskan = set()
    for nama in watchlist:
        nama = nama.strip().upper()
        if nama in terlihat and nama not in sudah_diprioritaskan:
            prioritas.append(nama)
            sudah_diprioritaskan.add(nama)
    return prioritas + [nama for nama in semua if nama not in sudah_diprioritaskan]


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
    argumen = [a.upper() for a in sys.argv[1:] if not a.startswith("--")]
    watchlist = uni.muat_watchlist()
    if argumen:
        nama = argumen
        print(f"Memeriksa token pilihan: {', '.join(nama)}")
    else:
        daftar = uni.muat_data_daftar_40()
        nama = susun_token(daftar, watchlist)
        terpilih_wl = [n for n in nama if n in set(watchlist)]
        print(f"Memeriksa {len(nama)} token unik dari daftar_40.json "
              f"({len(terpilih_wl)} token watchlist di urutan teratas).")
        if terpilih_wl:
            print("* = token watchlist")
        if not nama:
            raise SystemExit("daftar_40.json tidak berisi token bullish atau bearish.")
    ex = dp.exchange_publik()
    try:
        ex.load_markets()
    except Exception as e:
        print(f"Catatan: data pasar (batas order minimum) gagal dimuat: {type(e).__name__}")

    margin, notional = risk.margin_per_setup(), risk.notional_per_setup()
    sumber = "MODAL_LIVE_USDT" if config.MODE == "live" else "MODAL_DEMO_USDT"
    print(f"Mode {config.MODE}: modal dibaca dari {sumber} = {config.MODAL_USDT} USDT")
    print(f"Alokasi {config.RISK_PER_SETUP_PCT}% -> margin per setup {margin:.3f} USDT "
          f"-> notional {notional:.3f} USDT @ {config.LEVERAGE:.0f}x")
    tp_teks = "Support/Resistance" if getattr(config, "TP_METHOD", "sr") == "sr" else f"{config.TP_ATR_PERCENT:.0f}% ATR"
    if getattr(config, "SL_METHOD", "atr") == "sr":
        sl_teks = "HH/HL Support/Resistance"
    else:
        sl_teks = f"{config.SL_ATR_PERCENT:.0f}% ATR"
    print(f"TP: {tp_teks} | SL: {sl_teks} | RISK_ATR boleh {config.RISK_ATR_MIN} - {config.RISK_ATR_MAX}\n")

    baris = []
    for n in nama:
        sim = f"{n}/USDT:USDT"
        try:
            c = dp.ambil_candle(ex, sim, "5m", 300)[:-1]
        except Exception as e:
            print(f"{n:8} gagal ambil candle: {type(e).__name__}")
            continue
        p, atr = c[-1]["c"], ik.atr(c)
        if getattr(config, "SL_METHOD", "atr") == "sr":
            buffer = 0.0
        else:
            buffer = atr * getattr(config, "SL_ATR_PERCENT", 50.0) / 100.0
        buffer_atr = buffer / atr if atr > 0 else float("inf")
        mn = min_notional((getattr(ex, "markets", None) or {}).get(sim), p)
        perlu = mn / config.LEVERAGE if mn else None
        order_ok = None if mn is None else notional >= mn
        sl_ok = buffer_atr <= config.RISK_ATR_MAX
        baris.append({"nama": n, "harga": p, "atr": atr, "buffer_atr": buffer_atr, "mn": mn,
                      "perlu": perlu, "order_ok": order_ok, "sl_ok": sl_ok})
        if mn is None:
            order_txt = "order minimum tidak diketahui"
        else:
            order_txt = f"order min ~{mn:.2f} USDT (margin {perlu:.2f}) -> {'CUKUP' if order_ok else 'TIDAK CUKUP'}"
        tanda = "*" if n in watchlist else " "
        print(f"{tanda}{n:7} harga {p:<10.6g} ATR5m {atr / p * 100:.3f}% | buffer SL {buffer / p * 100:.3f}% = {buffer_atr:.1f} ATR "
              f"({'ok' if sl_ok else 'MELEBIHI RISK_ATR_MAX'}) | {order_txt}")
        if mn is not None:
            m1 = mn / config.LEVERAGE
            print(f"{'':8} margin minimum: 1 level {m1:.2f} USDT ({m1 / config.MODAL_USDT * 100:.0f}% modal) | "
                  f"2 level {2 * m1:.2f} ({2 * m1 / config.MODAL_USDT * 100:.0f}%) | "
                  f"3 level {3 * m1:.2f} ({3 * m1 / config.MODAL_USDT * 100:.0f}%)")

    total = len(baris)
    gagal_order = [r for r in baris if r["order_ok"] is False]
    gagal_sl = [r for r in baris if not r["sl_ok"]]
    dikenal = [r for r in baris if r["perlu"]]
    print(f"\nRINGKASAN ({total} token)")
    print(f"  Ukuran setup memenuhi order minimum : {sum(1 for r in baris if r['order_ok'])} dari {total}")
    print(f"  Buffer SL <= RISK_ATR_MAX           : {sum(1 for r in baris if r['sl_ok'])} dari {total}")

    print("\nYANG PERLU DIPERBAIKI")
    if not gagal_order and not gagal_sl:
        print("  Tidak ada. Ukuran setup dan jarak SL cocok untuk semua token di atas.")

    if gagal_order and dikenal:
        modal = config.MODAL_USDT
        perlu_maks = max(r["perlu"] for r in dikenal)
        pct1 = math.ceil(perlu_maks * CADANGAN / modal * 1000) / 10
        pctN = math.ceil(perlu_maks * JUMLAH_LEVEL * CADANGAN / modal * 1000) / 10
        modal1 = perlu_maks * CADANGAN / (config.RISK_PER_SETUP_PCT / 100)
        print("  1. UKURAN ORDER di bawah minimum bursa")
        print(f"     Token yang gagal: {', '.join(r['nama'] for r in gagal_order)}")
        print(f"     Sekarang: margin {margin:.2f} USDT -> notional {notional:.2f} USDT. "
              f"Butuh minimal {perlu_maks:.2f} USDT margin per level (token terberat).")
        print("     Pilih salah satu:")
        print(f"     a. Naikkan RISK_PER_SETUP_PCT di .env menjadi minimal {pct1}% (1 level) atau {pctN}% ({JUMLAH_LEVEL} level).")
        print("        Sudah termasuk cadangan 20% karena nilai order minimum ikut harga token.")
        if pctN > 50:
            print(f"        Peringatan: {pctN}% lebih dari separuh modal, terlalu besar. Pertimbangkan opsi b atau d.")
        print(f"     b. Atau naikkan modal menjadi minimal ~{modal1:.0f} USDT (1 level) atau ~{modal1 * JUMLAH_LEVEL:.0f} USDT "
              f"({JUMLAH_LEVEL} level), dengan alokasi tetap {config.RISK_PER_SETUP_PCT}%.")
        print("        Ingat: modal dibaca dari MODAL_DEMO_USDT saat MODE=demo, dan dari MODAL_LIVE_USDT saat MODE=live.")
        if margin > 0:
            lev = max(r["mn"] for r in dikenal) * CADANGAN / margin
            print(f"     c. Atau leverage ~{lev:.0f}x. TIDAK disarankan: risiko likuidasi naik.")
        kecil = sorted(dikenal, key=lambda r: r["perlu"])[:3]
        print("     d. Atau pilih token dengan minimum lebih kecil: " +
              ", ".join(f"{r['nama']} (margin {r['perlu']:.2f})" for r in kecil))
    elif gagal_order:
        print("  1. Batas order minimum tidak diketahui untuk token yang gagal; cek langsung di Bitget.")

    if gagal_sl:
        print("  2. JARAK SL lebih lebar dari RISK_ATR_MAX")
        for r in gagal_sl:
            maks_poin = math.floor(config.RISK_ATR_MAX * r["atr"] / (r["harga"] * 1e-4))
            print(f"     {r['nama']}: buffer {r['buffer_atr']:.1f} ATR. Agar <= {config.RISK_ATR_MAX} ATR, SL_POINTS maksimal ~{maks_poin}.")
        print("     Jarak risiko sebenarnya = titik masuk ke SL, jadi buffer sebaiknya jauh di bawah batas itu.")
        print("     Opsi: SL_BUFFER_ATR (mis. 0.5) yang menyesuaikan volatilitas, atau turunkan SL_POINTS, atau naikkan RISK_ATR_MAX.")

    batas = config.MAX_DAILY_LOSS_USDT / config.MODAL_USDT * 100
    if batas > 10:
        print(f"  Catatan: MAX_DAILY_LOSS_USDT={config.MAX_DAILY_LOSS_USDT} = {batas:.0f}% dari modal, cukup longgar. "
              "Pertimbangkan 5-10% modal.")


if __name__ == "__main__":
    main()