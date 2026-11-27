"""Unit test slippage untuk paper.py.

Tidak butuh koneksi Bitget. Jalankan:  python tes_paper_slippage.py
"""
from __future__ import annotations

import paper
import state as st
import config
import penilai_ai


def _pos(arah: int = 1, notional: float = 7.5) -> dict:
    if arah > 0:
        levels = [
            {"nama": "S1", "harga": 100.0, "tp": 103.0, "status": "pending"},
            {"nama": "S2", "harga": 99.0, "tp": 103.0, "status": "pending"},
            {"nama": "HL", "harga": 98.0, "tp": 102.5, "status": "pending"},
        ]
        sl, tp = 97.0, 103.0
    else:
        levels = [
            {"nama": "R1", "harga": 100.0, "tp": 97.0, "status": "pending"},
            {"nama": "R2", "harga": 101.0, "tp": 97.0, "status": "pending"},
            {"nama": "HH", "harga": 102.0, "tp": 97.5, "status": "pending"},
        ]
        sl, tp = 103.0, 97.0
    return {
        "id": "test-slip",
        "simbol": "TEST/USDT:USDT",
        "arah": arah,
        "waktu_buka": "2026-01-01T00:00:00+00:00",
        "margin": 1.5,
        "leverage": 5.0,
        "notional": notional,
        "titik_grid": levels,
        "sl": sl,
        "tp": tp,
        "entry_avg": None,
        "ukuran_terisi": 0.0,
        "status": "open",
    }


def _c(o, h, l, c):
    return {"t": 0, "o": o, "h": h, "l": l, "c": c, "v": 1000}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_limit_fill_normal_tanpa_gap():
    """Fill normal: harga_fill = harga limit."""
    pos = _pos()
    # low 99.5 menyentuh S1=100, open masih di atas limit
    filled = paper._cek_fill(pos, _c(100.5, 100.5, 99.5, 100.0))
    assert len(filled) == 1
    assert filled[0]["harga_fill"] == 100.0
    print("  [OK] limit fill normal -> harga_fill = limit")


def test_limit_fill_gap_through_long():
    """Gap down menembus buy limit → fill di open (lebih baik untuk long)."""
    pos = _pos()
    # open 98.5 sudah di bawah S1=100; low 98.0
    filled = paper._cek_fill(pos, _c(98.5, 99.0, 98.0, 98.8))
    assert len(filled) >= 1
    s1 = next(t for t in pos["titik_grid"] if t["nama"] == "S1")
    assert s1["status"] == "filled"
    assert s1["harga_fill"] == 98.5  # open, lebih baik dari 100
    print(f"  [OK] gap-through long limit -> fill @ open {s1['harga_fill']} (lebih baik)")


def test_limit_fill_gap_through_short():
    """Gap up menembus sell limit → fill di open (lebih baik untuk short)."""
    pos = _pos(arah=-1)
    filled = paper._cek_fill(pos, _c(101.5, 102.0, 101.0, 101.8))
    r1 = next(t for t in pos["titik_grid"] if t["nama"] == "R1")
    assert r1["status"] == "filled"
    assert r1["harga_fill"] == 101.5  # open > limit 100
    print(f"  [OK] gap-through short limit -> fill @ open {r1['harga_fill']} (lebih baik)")


def test_entry_avg_pakai_harga_fill():
    """entry_avg memakai harga_fill, bukan harga limit."""
    pos = _pos()
    paper._cek_fill(pos, _c(98.5, 99.0, 98.0, 98.8))  # gap fill S1+S2+HL mungkin
    avg = paper._hitung_entry_avg(pos)
    # minimal S1 filled @ 98.5
    assert avg is not None
    assert avg < 100.0  # lebih baik dari limit murni
    print(f"  [OK] entry_avg pakai harga_fill = {avg:.4f} (< 100)")


def test_sl_slippage_long_adverse():
    """Long SL: candle low di bawah SL → exit di low (lebih buruk)."""
    harga = paper._harga_exit_sl(97.0, 1, _c(99, 99, 95.0, 96))
    assert harga == 95.0
    print("  [OK] long SL slippage -> exit @ low 95 (bukan 97)")


def test_sl_slippage_short_adverse():
    """Short SL: candle high di atas SL → exit di high (lebih buruk)."""
    harga = paper._harga_exit_sl(103.0, -1, _c(101, 106.0, 101, 105))
    assert harga == 106.0
    print("  [OK] short SL slippage -> exit @ high 106 (bukan 103)")


def test_sl_tanpa_slippage_flag():
    """Jika SLIPPAGE_SL=False, exit tepat di level SL."""
    old = paper.SLIPPAGE_SL
    paper.SLIPPAGE_SL = False
    try:
        harga = paper._harga_exit_sl(97.0, 1, _c(99, 99, 95.0, 96))
        assert harga == 97.0
        print("  [OK] SLIPPAGE_SL=False -> exit tepat @ 97")
    finally:
        paper.SLIPPAGE_SL = old


def test_tp_tidak_ambil_slippage_positif():
    """TP limit: tetap di harga TP meski candle high lebih tinggi."""
    harga = paper._harga_exit_tp(103.0, 1, _c(102, 105, 102, 104))
    assert harga == 103.0
    print("  [OK] TP tidak ambil slippage positif (tetap 103)")


def test_integrasi_sl_gap_partial():
    """Skenario lengkap: fill S1 normal → gap SL dengan slippage → PnL lebih buruk."""
    state = st.state_kosong()
    pos = _pos()
    state["open_positions"] = [pos]

    # Fill S1 normal
    paper.update_posisi(state, pos, _c(100.5, 100.5, 99.5, 100.0))
    assert paper._n_filled(pos) == 1
    assert abs(pos["entry_avg"] - 100.0) < 1e-9

    # Gap down ke SL: low=94 (jauh di bawah SL 97), open=96
    # Path melewati S2+HL → ikut terisi, lalu SL dengan slippage
    paper.update_posisi(state, pos, _c(96.0, 96.0, 94.0, 94.5))
    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "sl"
    hasil = pos["hasil"]
    # Exit harus di 94 (low), bukan 97
    assert hasil["harga_keluar"] == 94.0
    assert hasil["slippage_pct"] > 0  # adverse
    assert hasil["pnl_bersih"] < 0
    print(
        f"  [OK] integrasi SL gap | keluar={hasil['harga_keluar']} "
        f"slip={hasil['slippage_pct']:+.3f}% PnL={hasil['pnl_bersih']:+.4f}"
    )


def test_integrasi_tp_tanpa_slippage_ekstra():
    """Partial fill → TP: exit tepat di TP, slippage ~0."""
    state = st.state_kosong()
    pos = _pos()
    state["open_positions"] = [pos]

    paper.update_posisi(state, pos, _c(100.5, 100.5, 99.5, 100.0))  # fill S1
    paper.update_posisi(state, pos, _c(101, 104, 101, 103.5))  # TP

    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "tp"
    hasil = pos["hasil"]
    # TP efektif S1 = 103
    assert abs(hasil["harga_keluar"] - 103.0) < 1e-9
    assert abs(hasil.get("slippage_pct", 0)) < 0.01
    print(f"  [OK] TP exit tepat @ {hasil['harga_keluar']} | slip={hasil.get('slippage_pct', 0):+.3f}%")


def test_konfigurasi_candle_terbaru():
    assert config.CANDLE_TIMEFRAME in ("5m", "15m", "30m")
    print(f"  [OK] candle config terbaru = {config.CANDLE_TIMEFRAME}")


def test_metode_tp_sl_terbaru():
    data = {"atr": 10, "HH": 110, "HL": 90}
    assert penilai_ai.tp_untuk(data, 1, 100) == 110
    assert penilai_ai.tp_untuk(data, -1, 100) == 90
    assert abs(penilai_ai.buffer_sl(data) - config.SL_BUFFER_ATR * 10) < 1e-9
    print("  [OK] TP di HH/HL dan SL = SL_BUFFER_ATR x ATR")


def test_slippage_membuat_loss_lebih_dalam():
    """Bandingkan PnL SL dengan vs tanpa slippage — dengan slippage harus lebih buruk."""
    # Dengan slippage
    pos1 = _pos()
    pos1["titik_grid"][0]["status"] = "filled"
    pos1["titik_grid"][0]["harga_fill"] = 100.0
    pos1["entry_avg"] = 100.0
    pos1["ukuran_terisi"] = 2.5
    c = _c(99, 99, 94.0, 95)
    keluar_slip = paper._harga_exit_sl(97.0, 1, c)
    pnl_slip = paper._hitung_pnl(pos1, keluar_slip)

    # Tanpa slippage (exit di 97)
    pnl_teori = paper._hitung_pnl(pos1, 97.0)

    assert keluar_slip == 94.0
    assert pnl_slip["pnl_bersih"] < pnl_teori["pnl_bersih"]
    print(
        f"  [OK] slippage memperdalam loss: "
        f"teori={pnl_teori['pnl_bersih']:+.4f} vs slip={pnl_slip['pnl_bersih']:+.4f}"
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=== Unit test slippage (paper.py) ===\n")
    # Pastikan flag default aktif
    paper.SLIPPAGE_SL = True
    paper.SLIPPAGE_LIMIT_GAP = True

    tests = [
        test_limit_fill_normal_tanpa_gap,
        test_limit_fill_gap_through_long,
        test_limit_fill_gap_through_short,
        test_entry_avg_pakai_harga_fill,
        test_sl_slippage_long_adverse,
        test_sl_slippage_short_adverse,
        test_sl_tanpa_slippage_flag,
        test_tp_tidak_ambil_slippage_positif,
        test_integrasi_sl_gap_partial,
        test_integrasi_tp_tanpa_slippage_ekstra,
        test_konfigurasi_candle_terbaru,
        test_metode_tp_sl_terbaru,
        test_slippage_membuat_loss_lebih_dalam,
    ]
    gagal = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  [X]  {t.__name__}: {e}")
            gagal += 1
        except Exception as e:
            print(f"  [X]  {t.__name__}: {type(e).__name__}: {e}")
            gagal += 1

    print()
    if gagal == 0:
        print(f"SEMUA LULUS ({len(tests)} test)")
    else:
        print(f"GAGAL: {gagal}/{len(tests)}")
    return gagal


if __name__ == "__main__":
    raise SystemExit(main())
