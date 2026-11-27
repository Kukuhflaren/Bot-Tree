"""Tes offline strategi Trend Grid Sederhana (tanpa jaringan, tanpa order)."""
import math

import config
import indikator as ik
import penilai_ai as pa


def candle(i, o, h, l, c):
    return {"t": 1_700_000_000_000 + i * 900_000, "o": o, "h": h, "l": l, "c": c, "v": 1000}


def seri_zigzag(naik=True, n=160, noise=0.0):
    """Tren zigzag: gelombang naik/turun dengan puncak & lembah bertahap."""
    hasil, harga = [], 100.0
    for i in range(n):
        drift = 0.15 if naik else -0.15
        gelombang = math.sin(i / 3.5) * 3.0
        target = 100 + drift * i + gelombang
        o = harga
        c = target
        h = max(o, c) + 0.25
        l = min(o, c) - 0.25
        hasil.append(candle(i, o, h, l, c))
        harga = c
    return hasil


def seri_sideways(n=160):
    hasil, harga = [], 100.0
    for i in range(n):
        target = 100 + math.sin(i / 3.0) * 0.6
        o, c = harga, target
        hasil.append(candle(i, o, max(o, c) + 0.2, min(o, c) - 0.2, c))
        harga = c
    return hasil


def tes_bullish():
    a = ik.analisis(seri_zigzag(True), arah=None)
    assert a["arah"] == 1 and a["label"] == "bullish", a["alasan_tren"]
    assert a["HL"] < a["harga"] < a["HH"] or a["grid"] == []
    for nama, h in a["grid"]:
        assert nama.startswith("S") and h < a["harga"] and a["HL"] < h < a["HH"]
    print(f"  [OK] bullish: adx={a['adx']:.1f} grid={[(n, round(h, 2)) for n, h in a['grid']]} layak={a['layak']}")
    return a


def tes_bearish():
    a = ik.analisis(seri_zigzag(False), arah=None)
    assert a["arah"] == -1 and a["label"] == "bearish", a["alasan_tren"]
    for nama, h in a["grid"]:
        assert nama.startswith("R") and h > a["harga"] and a["HL"] < h < a["HH"]
    print(f"  [OK] bearish: adx={a['adx']:.1f} grid={[(n, round(h, 2)) for n, h in a['grid']]} layak={a['layak']}")
    return a


def tes_sideways_skip():
    a = ik.analisis(seri_sideways(), arah=None)
    assert a["arah"] == 0 and a["grid"] == [] and a["layak"] is False
    assert pa.rencana(a, 1) == []
    print(f"  [OK] sideways di-skip ({a['alasan_tren']})")


def tes_petunjuk_universe_berlawanan():
    a = ik.analisis(seri_zigzag(True), arah=-1)   # universe bilang bearish, bot melihat bullish
    assert a["layak"] is False and a["syarat"][0] is False
    print("  [OK] petunjuk universe yang berlawanan dengan tren asli ditolak")


def tes_geometri(a, long=True):
    grid = pa.rencana(a, a["arah"])
    sl_set = {g["sl"] for g in grid}
    tp_set = {g["tp"] for g in grid}
    assert len(sl_set) <= 1 and len(tp_set) <= 1, "SL/TP harus tunggal untuk seluruh grid"
    atr_v = a["atr"]
    if long:
        assert abs(grid[0]["sl"] - (a["HL"] - config.SL_BUFFER_ATR * atr_v)) < 1e-3 * a["harga"]
        assert abs(grid[0]["tp"] - a["HH"]) < 1e-3 * a["harga"]
    else:
        assert abs(grid[0]["sl"] - (a["HH"] + config.SL_BUFFER_ATR * atr_v)) < 1e-3 * a["harga"]
        assert abs(grid[0]["tp"] - a["HL"]) < 1e-3 * a["harga"]
    for g in grid:
        if g["valid"]:
            assert g["net_rr"] >= config.RR_MIN
            assert config.RISK_ATR_MIN <= g["risk_atr"] <= config.RISK_ATR_MAX
    print(f"  [OK] geometri {'long' if long else 'short'}: {len(grid)} titik, {sum(g['valid'] for g in grid)} valid, SL/TP tunggal")


def tes_net_rr_manual():
    # long: harga 100, HL 98, HH 106, ATR 1 -> SL = 98-0.4 = 97.6
    a = {"arah": 1, "harga": 101.0, "atr": 1.0, "HL": 98.0, "HH": 106.0, "grid": [("S1", 100.0)]}
    g = pa.rencana(a, 1)[0]
    risk, reward = 100.0 - 97.6, 106.0 - 100.0
    exp = (reward / 100 * 100 - config.FEE_ROUNDTRIP_PCT) / (risk / 100 * 100 + config.FEE_ROUNDTRIP_PCT)
    assert abs(g["net_rr"] - exp) < 0.01, (g["net_rr"], exp)
    print(f"  [OK] Net RR manual cocok: {g['net_rr']:.3f}")


def tes_candle_ekstrem():
    c = seri_zigzag(True)
    last = c[-1]
    c[-1] = candle(len(c), last["o"], last["o"] + 8, last["o"] - 0.1, last["o"] + 7.5)
    a = ik.analisis(c, arah=None)
    assert a["ekstrem"] is True and a["layak"] is False
    print("  [OK] candle ekstrem membuat token tidak layak")


# ---------------------------------------------------------------- exit paper: time exit & candle ekstrem
def _pos_terisi():
    import paper
    import state as st
    import tes_paper_partial as tp
    state = st.state_kosong()
    pos = tp._pos_contoh(1)
    pos["atr"] = 1.0
    state["open_positions"].append(pos)
    paper.update_posisi(state, pos, {"t": 0, "o": 100.5, "h": 100.5, "l": 99.5, "c": 100.0, "v": 1})  # fill S1
    assert pos["entry_avg"] is not None and pos["ukuran_terisi"] > 0
    return paper, state, pos


def tes_time_exit_dengan_posisi():
    import datetime as dt
    paper, state, pos = _pos_terisi()
    buka = dt.datetime.fromisoformat(pos["waktu_buka"])
    t_ms = int((buka + dt.timedelta(hours=config.MAX_HOLD_HOURS + 0.1)).timestamp() * 1000)
    paper.update_posisi(state, pos, {"t": t_ms, "o": 100.0, "h": 100.4, "l": 99.7, "c": 100.2, "v": 1})
    assert pos["status"] == "closed" and pos["alasan_tutup"] == "time_exit"
    assert state["total_trades"] == 1 and not state["open_positions"]
    print("  [OK] time exit menutup posisi yang sudah terisi")


def tes_time_exit_tanpa_fill():
    import datetime as dt
    import paper
    import state as st
    import tes_paper_partial as tp
    state = st.state_kosong()
    pos = tp._pos_contoh(1)
    state["open_positions"].append(pos)
    buka = dt.datetime.fromisoformat(pos["waktu_buka"])
    t_ms = int((buka + dt.timedelta(hours=config.MAX_HOLD_HOURS + 0.1)).timestamp() * 1000)
    paper.update_posisi(state, pos, {"t": t_ms, "o": 105.0, "h": 105.5, "l": 104.5, "c": 105.0, "v": 1})  # tidak menyentuh grid
    assert pos["alasan_tutup"] == "time_exit" and state["total_trades"] == 0 and not state["open_positions"]
    assert all(t["status"] == "cancelled" for t in pos["titik_grid"])
    print("  [OK] time exit tanpa fill hanya membatalkan limit (bukan trade)")


def tes_candle_ekstrem_melawan_arah():
    paper, state, pos = _pos_terisi()
    paper.update_posisi(state, pos, {"t": 1000, "o": 100.0, "h": 100.1, "l": 97.6, "c": 97.6 + 0.0, "v": 1})
    # body -2.4 ATR (<2.5) belum memicu; SL 97.0 belum tersentuh
    assert pos["status"] == "open"
    paper.update_posisi(state, pos, {"t": 2000, "o": 100.0, "h": 100.1, "l": 97.4, "c": 97.4, "v": 1})
    assert pos["status"] == "closed" and pos["alasan_tutup"] == "candle_ekstrem"
    print("  [OK] candle ekstrem melawan arah menutup posisi")


if __name__ == "__main__":
    print("Tes strategi Trend Grid Sederhana")
    bull = tes_bullish()
    bear = tes_bearish()
    tes_sideways_skip()
    tes_petunjuk_universe_berlawanan()
    if bull["grid"]:
        tes_geometri(bull, long=True)
    if bear["grid"]:
        tes_geometri(bear, long=False)
    tes_net_rr_manual()
    tes_candle_ekstrem()
    tes_time_exit_dengan_posisi()
    tes_time_exit_tanpa_fill()
    tes_candle_ekstrem_melawan_arah()
    print("Semua tes strategi lolos")
