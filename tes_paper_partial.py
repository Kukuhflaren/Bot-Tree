"""Unit test partial fill untuk paper.py.

Tidak butuh koneksi Bitget / AI. Semua data palsu.
Jalankan:  python tes_paper_partial.py
"""
from __future__ import annotations

import copy

import paper
import state as st


def _pos_contoh(arah: int = 1, notional: float = 7.5) -> dict:
    """Posisi long 3 level (S1, S2, HL) — belum ada fill."""
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
        "id": "test-partial",
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


def _candle(o: float, h: float, l: float, c: float) -> dict:
    return {"t": 0, "o": o, "h": h, "l": l, "c": c, "v": 1000}


def _state() -> dict:
    return st.state_kosong()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_belum_ada_fill_tidak_bisa_exit():
    pos = _pos_contoh()
    # Candle menyentuh SL dan TP, tapi belum ada fill
    c = _candle(100, 104, 96, 100)
    assert paper._cek_exit(pos, c) is None
    print("  [OK] belum ada fill -> exit = None")


def test_fill_satu_level():
    pos = _pos_contoh()
    # Harga turun sampai S1 (100), belum ke S2
    c = _candle(100.5, 100.5, 99.5, 100.2)
    filled = paper._cek_fill(pos, c)
    assert len(filled) == 1
    assert filled[0]["nama"] == "S1"
    assert filled[0]["status"] == "filled"
    assert paper._n_filled(pos) == 1
    assert paper._n_pending(pos) == 2

    pos["ukuran_terisi"] = pos["notional"] * (1 / 3)
    pos["entry_avg"] = paper._hitung_entry_avg(pos)
    assert abs(pos["entry_avg"] - 100.0) < 1e-9
    assert abs(pos["ukuran_terisi"] - 2.5) < 1e-9
    print("  [OK] fill 1 level -> entry=100, terisi=2.5/7.5")


def test_fill_multi_level_satu_candle():
    pos = _pos_contoh()
    # Gap turun: low 97.5 → S1 + S2 + HL semua terisi
    c = _candle(100.5, 100.5, 97.5, 98.0)
    filled = paper._cek_fill(pos, c)
    assert len(filled) == 3
    assert paper._n_filled(pos) == 3
    assert paper._n_pending(pos) == 0

    pos["ukuran_terisi"] = pos["notional"]
    pos["entry_avg"] = paper._hitung_entry_avg(pos)
    # rata-rata (100+99+98)/3 = 99
    assert abs(pos["entry_avg"] - 99.0) < 1e-9
    print("  [OK] fill 3 level sekaligus (gap) -> entry=99")


def test_partial_lalu_tp():
    state = _state()
    pos = _pos_contoh()
    state["open_positions"] = [pos]

    # 1) Fill hanya S1
    c1 = _candle(100.5, 100.5, 99.5, 100.0)
    paper.update_posisi(state, pos, c1)
    assert paper._n_filled(pos) == 1
    assert abs(pos["ukuran_terisi"] - 2.5) < 1e-9
    assert pos["status"] == "open"

    # 2) Harga naik ke TP (103)
    c2 = _candle(100.5, 103.5, 100.0, 103.0)
    paper.update_posisi(state, pos, c2)

    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "tp"
    assert len(state["open_positions"]) == 0
    assert len(state["riwayat"]) == 1

    hasil = pos["hasil"]
    # PnL hanya dari 2.5 notional, entry 100 → TP 103 = +3%
    # kotor = 2.5 * 0.03 = 0.075, fee = 2.5 * 0.0012 = 0.003, bersih ≈ 0.072
    assert hasil["n_filled"] == 1
    assert abs(hasil["notional_terisi"] - 2.5) < 1e-9
    assert hasil["pnl_bersih"] > 0
    assert pos["pending_dibatalkan"] == 2  # S2 + HL di-cancel
    print(f"  [OK] partial 1/3 -> TP | PnL={hasil['pnl_bersih']:+.4f} | cancel 2 pending")


def test_partial_lalu_sl():
    """Harga menuju SL pasti melewati level yang lebih dalam → level itu ikut terisi.

    Ini perilaku geometris yang benar: tidak mungkin kena SL tanpa melewati HL.
    Jadi 'partial lalu SL dengan sisa pending di antara entry dan SL' hampir tidak terjadi.
    Test ini memverifikasi: fill bertahap → lalu SL mengisi sisa + menutup.
    """
    state = _state()
    pos = _pos_contoh()
    state["open_positions"] = [pos]

    # Fill hanya S1 (low 99.5, belum ke S2=99)
    c1 = _candle(100.5, 100.5, 99.5, 100.0)
    paper.update_posisi(state, pos, c1)
    assert paper._n_filled(pos) == 1
    assert abs(pos["ukuran_terisi"] - 2.5) < 1e-9
    assert abs(pos["entry_avg"] - 100.0) < 1e-9
    assert pos["status"] == "open"

    # Harga turun tembus SL (97). Low=96.5 melewati S2=99 dan HL=98 → ikut terisi
    c2 = _candle(100.0, 100.0, 96.5, 97.0)
    paper.update_posisi(state, pos, c2)

    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "sl"
    hasil = pos["hasil"]
    # Semua 3 level terisi karena path ke SL melewati semuanya
    assert hasil["n_filled"] == 3
    assert abs(hasil["notional_terisi"] - 7.5) < 1e-9
    assert hasil["pnl_bersih"] < 0
    assert pos["pending_dibatalkan"] == 0
    print(f"  [OK] fill S1 -> path ke SL mengisi sisa + tutup | PnL={hasil['pnl_bersih']:+.4f}")


def test_sl_diprioritaskan_atas_tp():
    """Candle yang menyentuh SL dan TP sekaligus → SL menang."""
    pos = _pos_contoh()
    # Fill dulu
    paper._cek_fill(pos, _candle(100.5, 100.5, 99.5, 100.0))
    pos["entry_avg"] = paper._hitung_entry_avg(pos)
    pos["ukuran_terisi"] = 2.5

    # Candle ekstrem: low di bawah SL, high di atas TP
    c = _candle(100, 104, 96, 100)
    alasan = paper._cek_exit(pos, c)
    assert alasan == "sl"
    print("  [OK] SL diprioritaskan jika SL+TP tersentuh dalam 1 candle")


def test_tp_efektif_konservatif():
    """Saat partial, TP efektif = TP terdekat (bukan terjauh)."""
    pos = _pos_contoh()
    # Hanya HL yang terisi (TP-nya 102.5, lebih dekat dari 103)
    pos["titik_grid"][2]["status"] = "filled"
    pos["entry_avg"] = 98.0
    pos["ukuran_terisi"] = 2.5

    tp = paper._tp_efektif(pos)
    assert tp == 102.5  # TP milik HL, bukan 103
    print("  [OK] TP efektif partial = TP terdekat dari level filled")


def test_short_partial_fill():
    state = _state()
    pos = _pos_contoh(arah=-1)
    state["open_positions"] = [pos]

    # Short: harga naik menyentuh R1 (100)
    c1 = _candle(99.5, 100.5, 99.5, 100.2)
    paper.update_posisi(state, pos, c1)
    assert paper._n_filled(pos) == 1
    assert abs(pos["entry_avg"] - 100.0) < 1e-9

    # Turun ke TP (97)
    c2 = _candle(100, 100, 96.5, 97.0)
    paper.update_posisi(state, pos, c2)
    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "tp"
    assert pos["hasil"]["pnl_bersih"] > 0
    assert pos["pending_dibatalkan"] == 2
    print(f"  [OK] short partial 1/3 -> TP | PnL={pos['hasil']['pnl_bersih']:+.4f}")


def test_cancel_sisa_pending():
    pos = _pos_contoh()
    pos["titik_grid"][0]["status"] = "filled"
    n = paper._cancel_sisa_pending(pos)
    assert n == 2
    assert all(t["status"] != "pending" for t in pos["titik_grid"])
    print("  [OK] cancel sisa pending")


def test_pnl_hanya_dari_ukuran_terisi():
    pos = _pos_contoh()
    pos["titik_grid"][0]["status"] = "filled"
    pos["entry_avg"] = 100.0
    pos["ukuran_terisi"] = 2.5  # partial

    # Full notional 7.5, partial 2.5 → PnL harus ~1/3 dari full
    hasil_partial = paper._hitung_pnl(pos, 103.0)

    pos_full = copy.deepcopy(pos)
    pos_full["ukuran_terisi"] = 7.5
    hasil_full = paper._hitung_pnl(pos_full, 103.0)

    # partial harus sekitar 1/3 full
    rasio = hasil_partial["pnl_bersih"] / hasil_full["pnl_bersih"]
    assert 0.30 < rasio < 0.36
    print(f"  [OK] PnL partial ~ 1/3 full (rasio={rasio:.3f})")


def test_tp_bertingkat_menutup_25_persen_dan_sisa_ke_sl():
    state = _state()
    pos = _pos_contoh()
    pos["tp_ladder"] = [
        {"harga": 103.0, "status": "pending"},
        {"harga": 105.0, "status": "pending"},
    ]
    pos["tp_fraction_per_level"] = 0.25
    pos["ukuran_masuk_total"] = 0.0
    pos["ukuran_ditutup"] = 0.0
    pos["realisasi"] = {"pnl_kotor": 0.0, "fee": 0.0, "pnl_bersih": 0.0, "notional": 0.0}
    state["open_positions"] = [pos]

    paper.update_posisi(state, pos, _candle(100.5, 100.5, 97.5, 99.0))
    assert paper._n_filled(pos) == 3
    assert pos["ukuran_terisi"] == 7.5

    paper.update_posisi(state, pos, _candle(100.0, 103.5, 99.0, 103.0))
    assert pos["status"] == "open"
    assert abs(pos["ukuran_terisi"] - 5.625) < 1e-9
    assert abs(pos["tp_events"][0]["notional"] - 1.875) < 1e-9

    paper.update_posisi(state, pos, _candle(103.5, 105.5, 103.0, 105.0))
    assert pos["status"] == "open"
    assert abs(pos["ukuran_terisi"] - 3.75) < 1e-9
    assert paper._tp_efektif(pos) is None

    paper.update_posisi(state, pos, _candle(100.0, 100.0, 96.0, 97.0))
    assert pos["status"] == "closed"
    assert pos["alasan_tutup"] == "sl"
    assert pos["hasil"]["notional_terisi"] == 7.5
    assert len(pos["tp_events"]) == 2
    assert state["total_trades"] == 1
    assert abs(state["modal_saat_ini"] - (state["modal_awal"] + pos["hasil"]["pnl_bersih"])) < 1e-4
    print("  [OK] two S/R targets realize 25% each; remaining position exits at SL")


def test_tp_ladder_short_menutup_25_persen_per_target():
    state = _state()
    pos = _pos_contoh(arah=-1)
    pos["tp_ladder"] = [
        {"harga": 97.0, "status": "pending"},
        {"harga": 95.0, "status": "pending"},
    ]
    pos["tp_fraction_per_level"] = 0.25
    pos["ukuran_masuk_total"] = 0.0
    pos["ukuran_ditutup"] = 0.0
    pos["realisasi"] = {"pnl_kotor": 0.0, "fee": 0.0, "pnl_bersih": 0.0, "notional": 0.0}
    state["open_positions"] = [pos]

    paper.update_posisi(state, pos, _candle(99.5, 102.5, 99.0, 100.0))
    assert paper._n_filled(pos) == 3
    paper.update_posisi(state, pos, _candle(100.0, 101.0, 94.5, 96.0))

    assert pos["status"] == "open"
    assert abs(pos["ukuran_terisi"] - 3.75) < 1e-9
    assert [event["harga"] for event in pos["tp_events"]] == [97.0, 95.0]
    print("  [OK] short TP ladder realizes 25% at descending S/R targets")


def test_paper_memproses_candle_terpilih_baru_saja():
    state = _state()
    pos = _pos_contoh()
    pos["candle_terakhir_diproses"] = 100
    state["open_positions"] = [pos]
    candle_calls = []
    originals = (
        paper.dp.exchange_publik,
        paper.dp.ambil_candle,
        paper.update_posisi,
        paper.st.simpan,
    )
    paper.dp.exchange_publik = lambda: object()
    paper.dp.ambil_candle = lambda _ex, _symbol, timeframe, _limit: (
        candle_calls.append(timeframe) or [
            _candle(100, 101, 99, 100) | {"t": 100},
            _candle(100, 101, 99, 100) | {"t": 200},
            _candle(100, 101, 99, 100) | {"t": 300},
        ]
    )
    paper.update_posisi = lambda _state, _pos, candle: candle_calls.append(candle["t"])
    paper.st.simpan = lambda _state: None
    try:
        paper.satu_siklus(state, buka_baru=False)
    finally:
        (
            paper.dp.exchange_publik,
            paper.dp.ambil_candle,
            paper.update_posisi,
            paper.st.simpan,
        ) = originals
    assert candle_calls == [paper.config.CANDLE_TIMEFRAME, 200]
    assert pos["candle_terakhir_diproses"] == 200
    print(f"  [OK] paper monitor uses {paper.config.CANDLE_TIMEFRAME} and processes each closed candle once")


def test_kandidat_paper_diambil_dari_daftar_40():
    data = paper.uni.muat_data_daftar_40()
    expected = [
        item["simbol"]
        for side in ("bullish", "bearish")
        for item in data[side]
    ]
    calls = []
    originals = (
        paper.dp.exchange_publik,
        paper.dp.ambil_candle,
        paper.ik.analisis,
        paper.pa.rencana,
    )
    try:
        paper.dp.exchange_publik = lambda: object()
        paper.dp.ambil_candle = lambda _exchange, symbol, _timeframe, _limit: (
            calls.append(symbol) or []
        )
        paper.ik.analisis = lambda *_args, **_kwargs: {"layak": False}
        paper.pa.rencana = lambda *_args, **_kwargs: []
        assert paper.muat_sinyal_layak(maks=len(expected) + 1) == []
    finally:
        (
            paper.dp.exchange_publik,
            paper.dp.ambil_candle,
            paper.ik.analisis,
            paper.pa.rencana,
        ) = originals
    assert calls == expected
    print("  [OK] paper candidate analysis reads only the displayed daftar_40 universe")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print("=== Unit test partial fill (paper.py) ===\n")
    tests = [
        test_belum_ada_fill_tidak_bisa_exit,
        test_fill_satu_level,
        test_fill_multi_level_satu_candle,
        test_partial_lalu_tp,
        test_partial_lalu_sl,
        test_sl_diprioritaskan_atas_tp,
        test_tp_efektif_konservatif,
        test_short_partial_fill,
        test_cancel_sisa_pending,
        test_pnl_hanya_dari_ukuran_terisi,
        test_tp_bertingkat_menutup_25_persen_dan_sisa_ke_sl,
        test_tp_ladder_short_menutup_25_persen_per_target,
        test_paper_memproses_candle_terpilih_baru_saja,
        test_kandidat_paper_diambil_dari_daftar_40,
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
