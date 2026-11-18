"""Phase E groundwork: validate and size Bitget UTA order plans safely.

This module intentionally does NOT submit exchange orders. UTA v3 field and
contract-quantity semantics must be verified with a dedicated demo account
before enabling execution. It can build/test a per-level order plan from live
public market metadata without API credentials.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_CEILING
from typing import Any


class OrderPlanError(ValueError):
    """The proposed orders cannot safely satisfy exchange constraints."""


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except Exception as exc:
        raise OrderPlanError(f"{label} must be a valid number") from exc
    if not result.is_finite():
        raise OrderPlanError(f"{label} must be finite")
    return result


def market_min_notional(market: dict[str, Any], price: float) -> Decimal | None:
    """Estimate one order's min notional using CCXT market limits.

    Returns None if CCXT provides no usable minimum; callers must fail closed
    rather than assume that an unknown exchange minimum is zero.
    """
    px = _decimal(price, "price")
    if px <= 0:
        raise OrderPlanError("price must be greater than zero")
    limits = market.get("limits") or {}
    cost_min = (limits.get("cost") or {}).get("min")
    amount_min = (limits.get("amount") or {}).get("min")
    contract_size = _decimal(market.get("contractSize") or 1, "contractSize")
    candidates: list[Decimal] = []
    if cost_min is not None:
        candidates.append(_decimal(cost_min, "minimum cost"))
    if amount_min is not None:
        candidates.append(_decimal(amount_min, "minimum amount") * px * contract_size)
    return max(candidates) if candidates else None


def _ceil_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise OrderPlanError("market amount precision must be positive")
    return (quantity / step).to_integral_value(rounding=ROUND_CEILING) * step


def plan_grid_orders(
    exchange: Any,
    symbol: str,
    levels: list[dict[str, Any]],
    total_notional_usdt: float,
    *,
    max_notional_usdt: float | None = None,
    sl: float,
    direction: str,
) -> list[dict[str, Any]]:
    """Return a sized per-level plan or raise; never silently exceed budget.

    If the requested number of levels cannot individually meet minimum order
    notional, deeper levels are removed first until the remaining levels fit.
    Each retained order gets an equal share of the requested total notional,
    rounded UP to market amount precision. If rounding/minimums exceed the
    explicit budget, the plan is rejected instead of increasing exposure.

    This plan is for review/dry-run only; no order is submitted.
    """
    if direction not in ("LONG", "SHORT"):
        raise OrderPlanError("direction must be LONG or SHORT")
    if not levels:
        raise OrderPlanError("at least one valid entry level is required")
    budget = _decimal(total_notional_usdt, "total_notional_usdt")
    hard_cap = _decimal(max_notional_usdt if max_notional_usdt is not None else total_notional_usdt,
                        "max_notional_usdt")
    stop = _decimal(sl, "sl")
    if budget <= 0 or hard_cap <= 0 or budget > hard_cap:
        raise OrderPlanError("notional budget must be positive and within max_notional_usdt")
    if stop <= 0:
        raise OrderPlanError("SL must be positive")

    market = exchange.market(symbol)
    min_n = market_min_notional(market, float(levels[0]["harga"]))
    if min_n is None:
        raise OrderPlanError(f"minimum order size unknown for {symbol}; refusing to guess")
    if min_n <= 0:
        raise OrderPlanError("market minimum notional is invalid")

    # Precision is expressed by CCXT as a tick size when precisionMode= TICK_SIZE;
    # amount_to_precision is authoritative for the final formatted quantity.
    retained = list(levels)
    while retained and budget / len(retained) < min_n:
        retained.pop()  # preserve the closest/first levels
    if not retained:
        raise OrderPlanError(
            f"budget {budget} USDT cannot meet minimum {min_n} USDT for even one level"
        )

    each_notional = budget / len(retained)
    contract_size = _decimal(market.get("contractSize") or 1, "contractSize")
    result: list[dict[str, Any]] = []
    estimated_total = Decimal("0")
    for level in retained:
        entry = _decimal(level.get("harga"), "entry price")
        tp = _decimal(level.get("tp"), "take profit")
        if entry <= 0 or tp <= 0:
            raise OrderPlanError("entry and TP must be positive")
        if direction == "LONG" and not (stop < entry < tp):
            raise OrderPlanError("LONG levels require SL < entry < TP")
        if direction == "SHORT" and not (tp < entry < stop):
            raise OrderPlanError("SHORT levels require TP < entry < SL")

        raw_contracts = each_notional / (entry * contract_size)
        amount_text = exchange.amount_to_precision(symbol, float(raw_contracts))
        contracts = _decimal(amount_text, "rounded order amount")
        actual_notional = contracts * entry * contract_size
        if contracts <= 0 or actual_notional < min_n:
            raise OrderPlanError(f"rounded amount for {level.get('titik')} is below exchange minimum")
        estimated_total += actual_notional
        result.append({
            "level": str(level.get("titik", "entry")),
            "symbol": symbol,
            "direction": direction,
            "side": "buy" if direction == "LONG" else "sell",
            "order_type": "limit",
            "price": float(entry),
            "amount_contracts": float(contracts),
            "estimated_notional_usdt": float(actual_notional),
            "sl": float(stop),
            "tp": float(tp),
            "reduce_only": False,
            "exchange_managed_tpsl_required": True,
        })

    if estimated_total > hard_cap:
        raise OrderPlanError(
            f"rounded plan {estimated_total} USDT exceeds hard cap {hard_cap} USDT"
        )
    return result


def assert_submission_disabled() -> None:
    """Fail closed until the UTA v3 adapter is verified against Demo."""
    raise RuntimeError(
        "Exchange submission is intentionally disabled: verify Bitget UTA v3 "
        "order fields, TP/SL attachment, partial-fill behavior and demo headers first."
    )
