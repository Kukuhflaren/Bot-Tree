"""Conservative, exchange-data-based Demo execution cost estimates."""
from __future__ import annotations

import math
from typing import Any


def _levels_depth(levels: list, contract_size: float) -> float:
    total = 0.0
    for level in levels:
        if len(level) < 2:
            continue
        price, amount = float(level[0]), float(level[1])
        if price <= 0 or amount < 0:
            raise ValueError("Invalid order-book level")
        total += price * amount * contract_size
    return total


def _vwap(levels: list, notional: float, contract_size: float) -> float:
    remaining = notional
    quote_total = 0.0
    contracts_total = 0.0
    for level in levels:
        price, amount = float(level[0]), float(level[1])
        if price <= 0 or amount < 0:
            raise ValueError("Invalid order-book level")
        level_quote = price * amount * contract_size
        used_quote = min(remaining, level_quote)
        used_contracts = used_quote / (price * contract_size)
        quote_total += used_contracts * contract_size * price
        contracts_total += used_contracts * contract_size
        remaining -= used_quote
        if remaining <= max(notional * 1e-12, 1e-12):
            break
    if remaining > max(notional * 1e-9, 1e-9) or contracts_total <= 0:
        raise ValueError("Order book does not have enough depth for the requested notional")
    return quote_total / contracts_total


def order_book_metrics(
    book: dict[str, Any],
    notional_usdt: float,
    contract_size: float,
    now_ms: int,
    max_age_seconds: float,
    min_depth_multiple: float,
) -> dict[str, float]:
    bids, asks = book.get("bids"), book.get("asks")
    timestamp = book.get("timestamp")
    if not bids or not asks or timestamp is None:
        raise ValueError("Fresh order-book timestamp and both sides are required")
    timestamp = float(timestamp)
    if not math.isfinite(timestamp) or now_ms - timestamp < 0:
        raise ValueError("Invalid or future order-book timestamp")
    if (now_ms - timestamp) / 1000 > max_age_seconds:
        raise ValueError("Order book is stale")
    if notional_usdt <= 0 or contract_size <= 0:
        raise ValueError("Notional and contract size must be positive")

    best_bid = max(float(level[0]) for level in bids)
    best_ask = min(float(level[0]) for level in asks)
    if best_bid <= 0 or best_ask <= best_bid:
        raise ValueError("Order book is crossed or has invalid prices")
    mid = (best_bid + best_ask) / 2
    spread_bps = (best_ask - best_bid) / mid * 10_000
    bid_depth = _levels_depth(bids, contract_size)
    ask_depth = _levels_depth(asks, contract_size)
    required_depth = notional_usdt * min_depth_multiple
    if bid_depth < required_depth or ask_depth < required_depth:
        raise ValueError("Order-book depth is below the configured minimum")

    buy_vwap = _vwap(sorted(asks, key=lambda row: float(row[0])), notional_usdt, contract_size)
    sell_vwap = _vwap(sorted(bids, key=lambda row: float(row[0]), reverse=True), notional_usdt, contract_size)
    round_trip_cost_bps = max(0.0, (buy_vwap - sell_vwap) / mid * 10_000)
    return {
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread_bps": spread_bps,
        "bid_depth_usdt": bid_depth,
        "ask_depth_usdt": ask_depth,
        "buy_vwap": buy_vwap,
        "sell_vwap": sell_vwap,
        "estimated_round_trip_book_cost_bps": round_trip_cost_bps,
    }


def estimated_net_bps(
    direction: str,
    entry: float,
    take_profit: float,
    entry_fee_bps: float,
    exit_fee_bps: float,
    book_cost_bps: float,
    funding_cost_bps: float,
) -> tuple[float, float]:
    if entry <= 0 or take_profit <= 0:
        raise ValueError("Entry and take-profit prices must be positive")
    direction = direction.upper()
    if direction not in ("LONG", "SHORT"):
        raise ValueError("Direction must be LONG or SHORT")
    gross_bps = (take_profit / entry - 1) * 10_000
    if direction == "SHORT":
        gross_bps = -gross_bps
    costs = (entry_fee_bps, exit_fee_bps, book_cost_bps, funding_cost_bps)
    if any(not math.isfinite(value) or value < 0 for value in costs):
        raise ValueError("Execution costs must be finite and non-negative")
    return gross_bps, gross_bps - sum(costs)
