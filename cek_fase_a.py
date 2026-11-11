"""Verifikasi Fase A: risk + universe.

Jalankan: python cek_fase_a.py
"""
import config
import risk
import universe as uni


def ok(pesan):
    print(f"  [OK] {pesan}")


def gagal(pesan):
    print(f"  [X]  {pesan}")


def main():
    print("=== Cek Fase A: Fondasi risk & universe ===\n")
    masalah = 0

    print("1. Parameter risk")
    if config.MAX_OPEN_TOKENS == 1:
        ok(f"MAX_OPEN_TOKENS={config.MAX_OPEN_TOKENS}")
    else:
        gagal(f"MAX_OPEN_TOKENS={config.MAX_OPEN_TOKENS} (disarankan 1 di awal)")
        masalah += 1
    if config.RISK_PER_SETUP_PCT <= 10:
        ok(f"RISK_PER_SETUP_PCT={config.RISK_PER_SETUP_PCT}% modal")
    else:
        gagal(f"RISK_PER_SETUP_PCT={config.RISK_PER_SETUP_PCT}% terlalu besar")
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
    mode = config.WATCHLIST_MODE
    if mode == "prefer":
        ok(f"WATCHLIST_MODE=prefer | {len(wl)} simbol diprioritaskan (bukan dibatasi)")
    elif mode == "only":
        ok(f"WATCHLIST_MODE=only | {len(wl)} simbol (universe sempit)")
    else:
        ok("WATCHLIST_MODE=off")

    if not config.TOKEN_BLACKLIST:
        ok("TOKEN_BLACKLIST kosong (eksperimen — tidak ada yang ditolak blacklist)")
    else:
        ok(f"TOKEN_BLACKLIST aktif: {len(config.TOKEN_BLACKLIST)} pola")

    # prefer/off: ETH harus lolos universe; only: hanya isi watchlist
    eth_ok, eth_alasan = uni.lolos_universe("ETH", wl)
    btc_ok, _ = uni.lolos_universe("BTC", wl)
    nvda_ok, nvda_alasan = uni.lolos_universe("NVDA", wl)

    if btc_ok:
        ok("BTC lolos saring universe")
    else:
        gagal("BTC ditolak universe")
        masalah += 1

    if mode == "only":
        if eth_ok and "ETH" in wl:
            ok("ETH di watchlist → lolos")
        elif not eth_ok:
            ok(f"ETH di luar watchlist → ditolak (mode only) ({eth_alasan})")
        if not nvda_ok:
            ok(f"NVDA ditolak ({nvda_alasan})")
    else:
        # prefer / off: token di luar watchlist tetap lolos (kecuali blacklist)
        if eth_ok:
            ok("ETH lolos (mode prefer/off — tidak dibatasi watchlist)")
        else:
            gagal(f"ETH ditolak padahal mode {mode}: {eth_alasan}")
            masalah += 1
        if config.TOKEN_BLACKLIST and uni.kena_blacklist("NVDA"):
            if not nvda_ok:
                ok(f"NVDA ditolak blacklist ({nvda_alasan})")
            else:
                gagal("NVDA seharusnya blacklist")
                masalah += 1
        else:
            if nvda_ok:
                ok("NVDA lolos (tidak di blacklist / blacklist kosong)")
            else:
                ok(f"NVDA ditolak: {nvda_alasan}")

    # Uji prioritas prefer
    if mode == "prefer" and wl:
        dummy = [
            {"simbol": "AAA/USDT:USDT", "skor": 100, "ubah_24j": 1},
            {"simbol": f"{wl[0]}/USDT:USDT", "skor": 1, "ubah_24j": 1},
        ]
        urut = uni.prioritaskan_watchlist(dummy, wl, 2)
        if urut and urut[0]["simbol"].startswith(wl[0]):
            ok(f"prefer: {wl[0]} naik ke depan meski skor lebih rendah")
        else:
            gagal("prefer: prioritas watchlist tidak bekerja")
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
        ok("risk_atr 1.2 + RR 1.5 lolos")
    else:
        gagal(f"setup wajar ditolak: {a2}")
        masalah += 1

    print("\n=== Hasil ===")
    if masalah == 0:
        print("Fase A SIAP untuk mode universe Anda saat ini.")
    else:
        print(f"Ada {masalah} item perlu diperbaiki.")
    return masalah


if __name__ == "__main__":
    raise SystemExit(main())
