"""Gabungan aman untuk masa uji Paper, Phase 6, dan preflight Demo.

Menjalankan paper cycle dan sinkronisasi journal, menghitung gate Phase 6,
kemudian membuat preflight Phase 7 dari sinyal bot. Tidak mengirim order.

Pakai:
  python uji_paper_demo.py --once
  python uji_paper_demo.py --once --journal paper_trades.jsonl
  python uji_paper_demo.py --once --demo-preflight
"""
from __future__ import annotations

import argparse

import demo_phase7
import paper
import paper_metrics
import paper_phase6
import paper_journal
import state as st


def jalankan_demo_preflight() -> int:
    signals = paper.muat_sinyal_layak(maks=3)
    if not signals:
        print("Phase 7: tidak ada sinyal layak untuk preflight.")
        return 0
    count = 0
    for signal in signals:
        symbol = signal["simbol"]
        direction = "LONG" if signal["arah"] == "BULLISH" else "SHORT"
        levels = signal.get("titik_grid") or []
        valid = [level for level in levels if level.get("valid")]
        if not valid:
            continue
        level = valid[0]
        try:
            plan = demo_phase7.preflight(
                symbol, direction,
                float(level["harga"]), float(level["sl"]), float(level["tp"]),
                6.25,
            )
            print("Phase 7 preflight:")
            print(f"  {symbol} {direction} entry={level['harga']} sl={level['sl']} tp={level['tp']}")
            print(f"  minimum={plan['minimumNotionalUSDT']} actual={plan['estimatedNotionalUSDT']}")
            count += 1
        except Exception as exc:
            print(f"Phase 7 preflight ditolak {symbol}: {type(exc).__name__}: {exc}")
    print(f"Phase 7: {count} rencana preflight berhasil dibuat; tidak ada order dikirim.")
    return count


def main():
    parser = argparse.ArgumentParser(description="Jalur terpadu Paper -> Phase 6 -> preflight Demo")
    parser.add_argument("--once", action="store_true", help="Satu siklus paper lalu keluar")
    parser.add_argument("--journal", default="paper_trades.jsonl")
    parser.add_argument("--demo-preflight", action="store_true", help="Buat preflight untuk sinyal layak")
    args = parser.parse_args()

    state = st.muat()
    print("=== PHASE 6 / PAPER ===")
    allowed, reason = paper_phase6.run_cycle(state, args.journal, allow_new=True)
    if not allowed:
        print(f"Safety stop paper: {reason}")

    print("\n=== PHASE 6 METRICS ===")
    events = paper_journal.read_events(args.journal)
    summary = paper_metrics.summarize_events(events, initial_capital=state.get("modal_awal") or 25)
    gate = summary["phase6_gate"]
    print(f"Trades={summary['trades']} | days={summary['duration_days']} | "
          f"expectancy={summary['expectancy_usdt_per_trade']} | "
          f"maxDD={summary['max_drawdown_pct_initial_capital']}% | "
          f"gate={'LULUS' if gate['passed'] else 'BELUM LULUS'}")

    if args.demo_preflight:
        print("\n=== PHASE 7 / DEMO PREFLIGHT ===")
        jalankan_demo_preflight()
    print("\nTidak ada order Demo/Live dikirim. Tambahkan --demo-preflight hanya untuk preflight.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
