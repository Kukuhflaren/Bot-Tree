"""Offline Phase 6 journal, metric, drawdown and stop-gate tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from paper_metrics import summarize_events


def test_costs_drawdown_and_insufficient_sample():
    now = datetime.now(timezone.utc)
    events = []
    for index, pnl in enumerate((0.2, -0.1, 0.3, -0.05)):
        trade_id = f"t{index}"
        start = now + timedelta(days=index * 2)
        end = start + timedelta(minutes=20)
        events.extend([
            {"event": "opened", "trade_id": trade_id, "timestamp": start.isoformat(),
             "symbol": "BTC/USDT:USDT", "entry_average": 100, "stop_loss": 98,
             "filled_notional_usdt": 10},
            {"event": "closed", "trade_id": trade_id, "timestamp": end.isoformat(),
             "entry_timestamp": start.isoformat(), "symbol": "BTC/USDT:USDT",
             "entry_average": 100, "stop_loss": 98, "filled_notional_usdt": 10,
             "net_pnl_usdt": pnl},
        ])
    report = summarize_events(events, initial_capital=30, min_trades=30, min_days=7)
    assert report["trades"] == 4
    assert report["net_pnl_after_recorded_fees_and_estimated_slippage_usdt"] < sum((0.2, -0.1, 0.3, -0.05))
    assert report["phase6_gate"]["passed"] is False
    assert report["phase6_gate"]["criteria"]["expectancy_gt_zero"] is True
    assert report["segments"]["major"]["trades"] == 4
    print("[OK] costs, drawdown report, segmentation, strict sample gate")


def test_losing_sequence_hits_drawdown_gate():
    now = datetime.now(timezone.utc)
    events = []
    for index in range(35):
        start = now + timedelta(hours=index * 6)
        end = start + timedelta(minutes=5)
        tid = str(index)
        events += [
            {"event": "opened", "trade_id": tid, "timestamp": start.isoformat(), "symbol": "ALT/USDT:USDT"},
            {"event": "closed", "trade_id": tid, "timestamp": end.isoformat(),
             "entry_timestamp": start.isoformat(), "symbol": "ALT/USDT:USDT",
             "entry_average": 100, "stop_loss": 90, "filled_notional_usdt": 10,
             "net_pnl_usdt": -1},
        ]
    report = summarize_events(events, initial_capital=30, min_trades=30, min_days=7, max_drawdown_pct=25)
    assert report["phase6_gate"]["criteria"]["actual_trades"] == 35
    assert report["phase6_gate"]["passed"] is False
    print("[OK] safety gate fails on negative expectancy/drawdown")


def main():
    test_costs_drawdown_and_insufficient_sample()
    test_losing_sequence_hits_drawdown_gate()
    print("All Phase 6 tests passed")


if __name__ == "__main__":
    main()
