"""Evaluate the append-only Phase 6 paper journal after estimated costs."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import paper_journal

MAJORS = {"BTC", "ETH", "SOL"}


def _parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        return None


def _union_seconds(intervals: list[tuple[datetime, datetime]]) -> float:
    if not intervals:
        return 0.0
    intervals.sort(key=lambda pair: pair[0])
    start, end = intervals[0]
    total = 0.0
    for next_start, next_end in intervals[1:]:
        if next_start <= end:
            end = max(end, next_end)
        else:
            total += max(0.0, (end - start).total_seconds())
            start, end = next_start, next_end
    return total + max(0.0, (end - start).total_seconds())


def summarize_events(
    events: list[dict[str, Any]], *, initial_capital: float,
    min_trades: int = 30, min_days: float = 7, max_drawdown_pct: float = 25,
    slippage_bps_per_side: float = 1,
) -> dict[str, Any]:
    opened = {e.get("trade_id"): e for e in events if e.get("event") == "opened" and e.get("trade_id")}
    closed = [e for e in events if e.get("event") == "closed" and e.get("trade_id")]
    # Deduplicate in case the journal was manually concatenated.
    by_id = {e["trade_id"]: e for e in closed}
    trades = sorted(by_id.values(), key=lambda e: (_parse_time(e.get("timestamp")) or datetime.min.replace(tzinfo=timezone.utc)))
    if initial_capital <= 0:
        raise ValueError("initial_capital must be greater than zero")
    if min_trades < 1 or min_days < 0 or max_drawdown_pct < 0 or slippage_bps_per_side < 0:
        raise ValueError("gate thresholds and slippage must be non-negative; min_trades must be positive")

    pnl_values: list[float] = []
    rs: list[float] = []
    segments: dict[str, dict[str, Any]] = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl_usdt": 0.0})
    equity = peak = initial_capital
    max_dd = 0.0
    for trade in trades:
        notional = float(trade.get("filled_notional_usdt") or 0)
        reported_net = float(trade.get("net_pnl_usdt") or 0)
        # paper.py already deducts its configured round-trip fee. Apply a
        # conservative additional adverse slippage haircut on entry + exit.
        slippage_cost = notional * 2 * (slippage_bps_per_side / 10000)
        net = reported_net - slippage_cost
        pnl_values.append(net)
        entry = float(trade.get("entry_average") or 0)
        stop = float(trade.get("stop_loss") or 0)
        risk_usdt = abs(entry - stop) / entry * notional if entry > 0 else 0
        if risk_usdt > 0:
            rs.append(net / risk_usdt)
        equity += net
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        base = str(trade.get("symbol") or "").split("/")[0].upper()
        segment = "major" if base in MAJORS else "altcoin"
        bucket = segments[segment]
        bucket["trades"] += 1
        bucket["wins"] += net > 0
        bucket["net_pnl_usdt"] += net
        trade["_estimated_slippage_cost_usdt"] = slippage_cost

    opened_times = [_parse_time(e.get("timestamp")) for e in opened.values()]
    close_times = [_parse_time(e.get("timestamp")) for e in trades]
    valid_times = [t for t in opened_times + close_times if t]
    span_seconds = max((max(valid_times) - min(valid_times)).total_seconds(), 0) if len(valid_times) > 1 else 0
    duration_days = span_seconds / 86400
    intervals: list[tuple[datetime, datetime]] = []
    for trade_id, close_event in by_id.items():
        start = _parse_time(opened.get(trade_id, {}).get("timestamp")) or _parse_time(close_event.get("entry_timestamp"))
        end = _parse_time(close_event.get("timestamp"))
        if start and end and end >= start:
            intervals.append((start, end))
    busy_seconds = _union_seconds(intervals)
    idle_pct = max(0.0, 100 * (1 - min(busy_seconds, span_seconds) / span_seconds)) if span_seconds > 0 else None

    total = len(trades)
    net_total = sum(pnl_values)
    dd_pct = max_dd / initial_capital * 100
    enough_duration = duration_days >= min_days
    enough_sample = total >= min_trades
    positive_expectancy = (net_total / total > 0) if total else False
    acceptable_dd = dd_pct <= max_drawdown_pct
    passed = enough_sample and enough_duration and positive_expectancy and acceptable_dd

    for bucket in segments.values():
        n = bucket["trades"]
        bucket["net_pnl_usdt"] = round(bucket["net_pnl_usdt"], 6)
        bucket["win_rate_pct"] = round(100 * bucket["wins"] / n, 2) if n else 0
        del bucket["wins"]

    return {
        "trades": total,
        "duration_days": round(duration_days, 3),
        "win_rate_pct": round(100 * sum(value > 0 for value in pnl_values) / total, 2) if total else None,
        "net_pnl_after_recorded_fees_and_estimated_slippage_usdt": round(net_total, 6),
        "expectancy_usdt_per_trade": round(net_total / total, 6) if total else None,
        "average_r_after_estimated_slippage": round(sum(rs) / len(rs), 4) if rs else None,
        "max_drawdown_usdt": round(max_dd, 6),
        "max_drawdown_pct_initial_capital": round(dd_pct, 4),
        "trades_per_day": round(total / duration_days, 3) if duration_days > 0 else None,
        "idle_time_pct_approx": round(idle_pct, 2) if idle_pct is not None else None,
        "segments": dict(segments),
        "assumptions": {
            "recorded_fee": "paper.py recorded round-trip estimate",
            "extra_slippage_bps_per_side": slippage_bps_per_side,
            "extra_slippage_model": "filled notional × 2 sides × bps; deducted from net PnL",
            "max_drawdown": "realized trade-equity peak-to-trough, percentage of initial paper capital",
            "idle_time": "approximate occupancy from observed open/close intervals; excludes time before first and after last observed event",
        },
        "phase6_gate": {
            "passed": passed,
            "criteria": {
                "min_trades": min_trades,
                "actual_trades": total,
                "min_days": min_days,
                "actual_days": round(duration_days, 3),
                "expectancy_gt_zero": positive_expectancy,
                "max_drawdown_pct_limit": max_drawdown_pct,
                "actual_drawdown_pct": round(dd_pct, 4),
            },
            "warning": "This is a configurable screening gate, not evidence of future profitability or a demo/live authorization.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 append-only paper journal report")
    parser.add_argument("--journal", default=paper_journal.DEFAULT_PATH)
    parser.add_argument("--capital", type=float, default=30)
    parser.add_argument("--min-trades", type=int, default=30)
    parser.add_argument("--min-days", type=float, default=7)
    parser.add_argument("--max-dd-pct", type=float, default=25)
    parser.add_argument("--slippage-bps-per-side", type=float, default=1)
    args = parser.parse_args()
    report = summarize_events(
        paper_journal.read_events(args.journal), initial_capital=args.capital,
        min_trades=args.min_trades, min_days=args.min_days,
        max_drawdown_pct=args.max_dd_pct,
        slippage_bps_per_side=args.slippage_bps_per_side,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
