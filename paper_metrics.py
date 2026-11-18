"""Read-only performance summary for the current paper state history.

Metrics are descriptive only. This report does not certify a strategy or
recommend live trading. Keep an external, append-only trade journal for any
multi-week evaluation because state.json intentionally retains a bounded history.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime
from typing import Any


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def summarize(state: dict[str, Any]) -> dict[str, Any]:
    trades = [p for p in (state.get("riwayat") or []) if p.get("hasil")]
    if not trades:
        return {"trades": 0, "message": "No closed paper trades in state history."}

    pnls = [float(p["hasil"].get("pnl_bersih") or 0) for p in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    rs: list[float] = []
    by_segment: dict[str, list[float]] = defaultdict(list)
    equity = peak = 0.0
    max_dd = 0.0
    for pos, pnl in zip(trades, pnls):
        result = pos["hasil"]
        entry = float(pos.get("entry_avg") or result.get("harga_keluar") or 0)
        sl = float(pos.get("sl") or 0)
        notional = float(result.get("notional_terisi") or 0)
        risk_usdt = abs(entry - sl) / entry * notional if entry > 0 else 0
        if risk_usdt > 0:
            rs.append(pnl / risk_usdt)
        equity += pnl
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
        base = str(pos.get("simbol", "")).split("/")[0].upper()
        segment = "major" if base in {"BTC", "ETH", "SOL"} else "altcoin"
        by_segment[segment].append(pnl)

    closes = sorted(t for t in (_parse_time(p.get("waktu_tutup")) for p in trades) if t)
    duration_days = max((closes[-1] - closes[0]).total_seconds() / 86400, 1 / 24) if len(closes) > 1 else 1.0
    opened = [_parse_time(p.get("waktu_buka")) for p in trades]
    valid_opened = [t for t in opened if t]
    if valid_opened and closes:
        observed_seconds = max((max(closes) - min(valid_opened)).total_seconds(), 0)
        busy_seconds = sum(
            max((_parse_time(p.get("waktu_tutup")) or _parse_time(p.get("waktu_buka")) -
                 _parse_time(p.get("waktu_buka"))).total_seconds(), 0)
            for p in trades
        )
        idle_pct = max(0.0, 100.0 * (1 - min(busy_seconds, observed_seconds) / observed_seconds)) if observed_seconds else None
    else:
        idle_pct = None

    return {
        "trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 2),
        "net_pnl_usdt": round(sum(pnls), 6),
        "average_r": round(sum(rs) / len(rs), 4) if rs else None,
        "expectancy_usdt_per_trade": round(sum(pnls) / len(pnls), 6),
        "max_drawdown_usdt_from_trade_equity": round(max_dd, 6),
        "max_drawdown_pct_initial_capital": round(max_dd / float(state.get("modal_awal") or 0) * 100, 4)
        if float(state.get("modal_awal") or 0) > 0 else None,
        "trades_per_day": round(len(trades) / duration_days, 3),
        "idle_time_pct_approx": round(idle_pct, 2) if idle_pct is not None else None,
        "segments_net_pnl_usdt": {name: round(sum(values), 6) for name, values in by_segment.items()},
        "limitations": [
            "Uses only the bounded riwayat array in state.json; it may not cover the full test period.",
            "Idle time is approximate and based on recorded open/close intervals.",
            "Expectancy is net USDT/trade; average R is calculated only where entry, SL and notional exist.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only report for paper state")
    parser.add_argument("--state", default="state.json")
    args = parser.parse_args()
    with open(args.state, encoding="utf-8") as handle:
        state = json.load(handle)
    print(json.dumps(summarize(state), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
