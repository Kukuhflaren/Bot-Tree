"""Verifikasi Fase A: risk + universe.

Jalankan: python cek_fase_a.py
Tidak butuh API key (kecuali Anda menambah tes live nanti).
"""
import config
import risk
import universe as uni


def ok(pesan):
    print(f"  [OK] {pesan}")


def gagal(pesan):
    print(f"  [X]  {pesan}")


def main():
    print("=== Cek Fondasi risk & universe ===\n")
    masalah = 0

    # --- Config risk ---
    print("1. Parameter risk")
    if config.MAX_OPEN_TOKENS == 1:
        ok(f"MAX_OPEN_TOKENS={config.MAX_OPEN_TOKENS}")
    else:
        gagal(f"MAX_OPEN_TOKENS={config.MAX_OPEN_TOKENS} (disarankan 1 di awal)")
        masalah += 1
    if config.RISK_PER_SETUP_PCT <= 10:
        ok(f"RISK_PER_SETUP_PCT={config.RISK_PER_SETUP_PCT}% modal")
    else:
        gagal(f"RISK_PER_SETUP_PCT={config.RISK_PER_SETUP_PCT}% terlalu besar untuk modal kecil")
        masalah += 1
    ok(f"RISK_ATR_MIN={config.RISK_ATR_MIN} | RISK_ATR_MAX={config.RISK_ATR_MAX}")
    ok(f"RR_MIN={config.RR_MIN} | SL_POINTS={config.SL_POINTS}")
    ok(f"MAX_DAILY_LOSS={config.MAX_DAILY_LOSS_USDT} | MAX_CONSECUTIVE={config.MAX_CONSECUTIVE_LOSSES}")
    ok(f"KILL_SWITCH={config.KILL_SWITCH} | DRY_RUN={config.DRY_RUN} | MODE={config.MODE}")

    size = risk.ringkasan_size()
    print("\n2. Ukuran posisi (satu setup)")
    ok(
        f"Modal {size['modal_usdt']} → margin {size['margin_usdt']} USDT "
        f"({size['risk_pct']}%) → notional ≈ {size['notional_usdt']} USDT @ {size['leverage']}x"
    )

    print("\n3. boleh_order_baru()")
    b, alasan = risk.boleh_order_baru({})
    if b:
        ok(f"state kosong → {alasan}")
    else:
        gagal(f"state kosong ditolak: {alasan}")
        masalah += 1

    b2, a2 = risk.boleh_order_baru({"open_tokens": ["BTC"]})
    if not b2 and config.MAX_OPEN_TOKENS <= 1:
        ok(f"1 token terbuka → ditolak ({a2})")
    else:
        gagal(f"1 token terbuka: boleh={b2} alasan={a2}")
        masalah += 1

    b3, a3 = risk.boleh_order_baru({"daily_pnl_usdt": -abs(config.MAX_DAILY_LOSS_USDT)})
    if not b3:
        ok(f"daily loss limit → ditolak ({a3})")
    else:
        gagal("daily loss limit tidak menolak")
        masalah += 1

    b4, a4 = risk.boleh_order_baru({"consecutive_losses": config.MAX_CONSECUTIVE_LOSSES})
    if not b4:
        ok(f"consecutive losses → ditolak ({a4})")
    else:
        gagal("consecutive losses tidak menolak")
        masalah += 1

    print("\n4. Universe")
    wl = uni.muat_watchlist()
    if config.WATCHLIST_MODE == "only" and len(wl) >= 10:
        ok(f"WATCHLIST_MODE=only | {len(wl)} simbol di {config.WATCHLIST_FILE}")
    elif config.WATCHLIST_MODE == "off":
        ok("WATCHLIST_MODE=off (universe lebar + blacklist)")
    else:
        gagal(f"Watchlist mode={config.WATCHLIST_MODE} isi={len(wl)} — periksa watchlist.json")
        masalah += 1

    for contoh, harus_tolak in [("CSOPSK2LHKD", True), ("NVDA", True), ("BTC", False), ("ETH", False)]:
        ok_u, alasan = uni.lolos_universe(contoh, wl)
        if harus_tolak and not ok_u:
            ok(f"{contoh} ditolak ({alasan})")
        elif not harus_tolak and ok_u:
            ok(f"{contoh} lolos")
        else:
            gagal(f"{contoh}: lolos={ok_u} alasan={alasan} (diharapkan tolak={harus_tolak})")
            masalah += 1

    print("\n5. Geometri risk")
    v, a = risk.validasi_geometri_risk(0.3, 14.9)
    if not v:
        ok(f"risk_atr 0.3 + RR 14.9 ditolak ({a})")
    else:
        gagal("risk_atr terlalu kecil masih lolos")
        masalah += 1
    v2, a2 = risk.validasi_geometri_risk(1.2, 1.5)
    if v2:
        ok(f"risk_atr 1.2 + RR 1.5 lolos")
    else:
        gagal(f"setup wajar ditolak: {a2}")
        masalah += 1

    print("\n=== Hasil ===")
    if masalah == 0:
        print("Fondasi risk & universe siap. Lanjut penyaring dengan watchlist, lalu entry/exit tertulis.")
    else:
        print(f"Ada {masalah} item perlu diperbaiki sebelum menganggap Fondasi risk & universe selesai.")
    return masalah


if __name__ == "__main__":
    raise SystemExit(main())
