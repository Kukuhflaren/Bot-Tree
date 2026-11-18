"""Phase 6 paper runner: durable journal, loss stops, and evaluation window.

All execution remains simulated by paper.py using public market data. Existing
positions continue to be monitored after a stop; the runner only disables new
entries. No Bitget order endpoints or private API keys are used.
"""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone

import paper
import paper_journal
import risk
import state as st


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_cycle(state: dict, journal_path: str, *, allow_new: bool = True) -> tuple[bool, str]:
    allowed, reason = risk.boleh_order_baru(state)
    if not allow_new:
        allowed, reason = False, "new entries disabled by CLI"
    paper.satu_siklus(state, buka_baru=allowed)
    # Persist paper.py state before journaling; a journal failure raises so the
    # operator knows the evaluation record is incomplete.
    st.simpan(state)
    paper_journal.sync_state(state, journal_path)

    # Re-check after realized PnL was updated. Existing positions are still
    # monitored in subsequent cycles; only new entries are stopped.
    allowed_after, reason_after = risk.boleh_order_baru(state)
    return allowed_after and allow_new, reason_after if not allowed_after else reason


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 paper evaluation runner")
    parser.add_argument("--interval", type=int, default=300, help="Seconds between paper cycles")
    parser.add_argument("--days", type=float, default=14, help="Evaluation duration (default 14 days)")
    parser.add_argument("--journal", default=paper_journal.DEFAULT_PATH)
    parser.add_argument("--once", action="store_true", help="Run exactly one paper cycle")
    parser.add_argument("--no-open", action="store_true", help="Only manage existing paper position")
    args = parser.parse_args()
    if args.interval < 1 or args.days <= 0:
        parser.error("--interval must be positive and --days must be greater than zero")

    state = st.muat()
    started = _utc_now()
    deadline = started + timedelta(days=args.days)
    print(f"Phase 6 paper runner | journal={args.journal} | duration={args.days:g} days")
    print("Simulation only. Loss stops block new entries but keep monitoring open positions.")

    try:
        while True:
            allowed, reason = run_cycle(state, args.journal, allow_new=not args.no_open)
            if not allowed and not args.no_open:
                print(f"Safety stop: no new entries ({reason}). Existing position monitoring continues.")
                paper_journal.append_event({
                    "event": "safety_stop",
                    "timestamp": _utc_now().isoformat(),
                    "reason": reason,
                    "daily_pnl_usdt": state.get("daily_pnl_usdt"),
                    "consecutive_losses": state.get("consecutive_losses"),
                }, args.journal)
            if args.once or _utc_now() >= deadline:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("Stopped by user; state and journal remain available.")
        st.simpan(state)

    paper_journal.sync_state(state, args.journal)
    print(f"Paper evaluation ended at {_utc_now().isoformat()}; journal: {args.journal}")
    print("Review with: python paper_metrics.py --journal " + args.journal)


if __name__ == "__main__":
    main()
