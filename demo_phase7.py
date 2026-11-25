"""Phase 7: guarded Bitget Demo order preflight and demo execution adapter.

Execution is disabled unless ALL of these are true:
- MODE=demo
- DRY_RUN=off
- DEMO_API=on
- a Demo API key is configured
- DEMO_CONFIRM is exactly "EUJIAN_DEMO_SAYA_PAHAM"

The adapter uses CCXT UTA/sandbox settings and never supports live MODE.
It verifies current market limits/precision and requires positive stop/TP geometry.
"""
from __future__ import annotations

import argparse
import json
import math
import uuid
from decimal import Decimal
from typing import Any

import ccxt

import bitget_orders
import config
import trade_costs

CONFIRMATION_TEXT = "UJI_DEMO_SAYA_PAHAM"


def _demo_config_ok() -> tuple[bool, str]:
    if config.MODE != "demo":
        return False, "MODE must be demo"
    if config.DRY_RUN:
        return False, "DRY_RUN must be off"
    if not getattr(config, "DEMO_API", False):
        return False, "DEMO_API must be on"
    if getattr(config, "LIVE_CONFIRM", ""):
        # Live confirmation must never be accepted as demo confirmation.
        pass
    if getattr(config, "DEMO_CONFIRM", "") != CONFIRMATION_TEXT:
        return False, f"DEMO_CONFIRM must be exactly {CONFIRMATION_TEXT}"
    if not (config.BITGET_API_KEY and config.BITGET_SECRET_KEY and config.BITGET_PASSPHRASE):
        return False, "Demo API key, secret and passphrase are required"
    return True, "demo execution configuration accepted"


def build_exchange() -> Any:
    exchange = ccxt.bitget({
        "apiKey": config.BITGET_API_KEY,
        "secret": config.BITGET_SECRET_KEY,
        "password": config.BITGET_PASSPHRASE,
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "swap"},
    })
    exchange.set_sandbox_mode(True)
    exchange.has["fetchCurrencies"] = False
    return exchange


def ccxt_symbol(name: str) -> str:
    name = name.upper().replace("USDT/USDT", "USDT")
    if "/" in name:
        return name
    return f"{name}/USDT:USDT"


def _execution_guard(
    exchange: Any, symbol: str, direction: str, entry: float, tp: float, notional: float,
) -> dict[str, float]:
    thresholds = (
        config.DEMO_MAKER_FEE_BPS,
        config.DEMO_TAKER_FEE_BPS,
        config.DEMO_MIN_NET_BPS,
        config.DEMO_MAX_SPREAD_BPS,
        config.DEMO_MIN_BOOK_DEPTH_MULTIPLE,
        config.DEMO_MAX_HOLD_HOURS,
        config.DEMO_BOOK_MAX_AGE_SECONDS,
    )
    if any(not math.isfinite(value) or value < 0 for value in thresholds):
        raise bitget_orders.OrderPlanError("Konfigurasi biaya/market Demo harus finite dan non-negatif")
    if config.DEMO_MIN_BOOK_DEPTH_MULTIPLE < 1 or config.DEMO_MAX_HOLD_HOURS <= 0:
        raise bitget_orders.OrderPlanError("Depth minimum harus >=1× dan time-exit harus positif")
    market = exchange.market(symbol)
    contract_size = float(market.get("contractSize") or 1)
    try:
        book = exchange.fetch_order_book(symbol, limit=20)
        metrics = trade_costs.order_book_metrics(
            book,
            notional,
            contract_size,
            int(exchange.milliseconds()),
            config.DEMO_BOOK_MAX_AGE_SECONDS,
            config.DEMO_MIN_BOOK_DEPTH_MULTIPLE,
        )
    except Exception as exc:
        raise bitget_orders.OrderPlanError(
            f"Order book Demo tidak memenuhi pemeriksaan real-time: {type(exc).__name__}: {exc}"
        ) from exc
    if metrics["spread_bps"] > config.DEMO_MAX_SPREAD_BPS:
        raise bitget_orders.OrderPlanError(
            f"Spread {metrics['spread_bps']:.2f} bps melebihi batas "
            f"{config.DEMO_MAX_SPREAD_BPS:.2f} bps"
        )
    if direction == "LONG" and entry >= metrics["best_ask"]:
        raise bitget_orders.OrderPlanError("Harga LONG marketable; post-only entry ditolak sebelum submit")
    if direction == "SHORT" and entry <= metrics["best_bid"]:
        raise bitget_orders.OrderPlanError("Harga SHORT marketable; post-only entry ditolak sebelum submit")

    try:
        funding = exchange.fetch_funding_rate(symbol)
        funding_rate = float(funding["fundingRate"])
    except Exception as exc:
        raise bitget_orders.OrderPlanError(
            f"Funding rate Demo tidak tersedia untuk estimasi biaya: {type(exc).__name__}: {exc}"
        ) from exc
    if not math.isfinite(funding_rate):
        raise bitget_orders.OrderPlanError("Funding rate Demo tidak valid")
    funding_cost_bps = (
        abs(funding_rate) * 10_000 * config.DEMO_MAX_HOLD_HOURS / 8
    )
    gross_bps, net_bps = trade_costs.estimated_net_bps(
        direction,
        entry,
        tp,
        config.DEMO_MAKER_FEE_BPS,
        config.DEMO_TAKER_FEE_BPS,
        metrics["estimated_round_trip_book_cost_bps"],
        funding_cost_bps,
    )
    if net_bps < config.DEMO_MIN_NET_BPS:
        raise bitget_orders.OrderPlanError(
            f"Estimasi net {net_bps:.2f} bps di bawah minimum "
            f"{config.DEMO_MIN_NET_BPS:.2f} bps"
        )
    return {
        **metrics,
        "funding_rate": funding_rate,
        "funding_cost_bps": funding_cost_bps,
        "gross_reward_bps": gross_bps,
        "entry_fee_bps": config.DEMO_MAKER_FEE_BPS,
        "exit_fee_bps": config.DEMO_TAKER_FEE_BPS,
        "estimated_net_bps": net_bps,
        "minimum_net_bps": config.DEMO_MIN_NET_BPS,
    }


def preflight(symbol: str, direction: str, entry: float, sl: float, tp: float,
              notional_usdt: float) -> dict[str, Any]:
    """Build and validate a demo limit plan without sending an order."""
    ex = build_exchange() if _demo_config_ok()[0] else ccxt.bitget({
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {"defaultType": "swap"},
    })
    ex.load_markets()
    sym = ccxt_symbol(symbol)
    market = ex.market(sym)
    min_n = bitget_orders.market_min_notional(market, entry)
    if min_n is None:
        raise bitget_orders.OrderPlanError("Demo minimum order notional is unknown")

    direction = direction.upper()
    if direction == "LONG":
        if not (sl < entry < tp):
            raise bitget_orders.OrderPlanError("LONG requires SL < entry < TP")
        side = "buy"
    elif direction == "SHORT":
        if not (tp < entry < sl):
            raise bitget_orders.OrderPlanError("SHORT requires TP < entry < SL")
        side = "sell"
    else:
        raise bitget_orders.OrderPlanError("direction must be LONG or SHORT")

    contract_size = Decimal(str(market.get("contractSize") or 1))
    contracts = Decimal(str(notional_usdt)) / (Decimal(str(entry)) * contract_size)
    amount_text = ex.amount_to_precision(sym, float(contracts))
    actual_contracts = Decimal(amount_text)
    actual_notional = actual_contracts * Decimal(str(entry)) * contract_size
    if actual_contracts <= 0 or actual_notional < min_n:
        raise bitget_orders.OrderPlanError(
            f"Demo rounded order {actual_notional} USDT is below minimum {min_n} USDT"
        )
    execution_guard = _execution_guard(
        ex, sym, direction, entry, tp, float(actual_notional),
    )

    plan = {
        "symbol": sym,
        "side": side,
        "orderType": "limit",
        "price": entry,
        "amountContracts": float(actual_contracts),
        "estimatedNotionalUSDT": float(actual_notional),
        "minimumNotionalUSDT": float(min_n),
        "takeProfitTriggerPrice": tp,
        "stopLossTriggerPrice": sl,
        "triggerType": "mark_price",
        "marginMode": "cross",
        "posSide": "long" if direction == "LONG" else "short",
        "reduceOnly": False,
        "clientOid": "bt-" + uuid.uuid4().hex[:18],
        "executionGuard": execution_guard,
    }
    return plan


def send_demo_order(plan: dict[str, Any]) -> dict[str, Any]:
    """Send one Demo order only after all preflight gates pass.

    This intentionally never switches to live MODE. CCXT parameter names are
    kept as explicit UTA TP/SL trigger fields; verify and adapt only from the
    repository's official-demo test after the returned exchange schema is seen.
    """
    accepted, reason = _demo_config_ok()
    if not accepted:
        raise RuntimeError(f"Demo execution refused: {reason}")

    ex = build_exchange()
    ex.load_markets()
    direction = "LONG" if plan["side"] == "buy" else "SHORT"
    guard = _execution_guard(
        ex,
        plan["symbol"],
        direction,
        float(plan["price"]),
        float(plan["takeProfitTriggerPrice"]),
        float(plan["estimatedNotionalUSDT"]),
    )
    params = {
        "uta": True,
        "marginMode": plan["marginMode"],
        "posSide": plan["posSide"],
        "reduceOnly": plan["reduceOnly"],
        "postOnly": True,
        "takeProfitTriggerPrice": str(plan["takeProfitTriggerPrice"]),
        "stopLossTriggerPrice": str(plan["stopLossTriggerPrice"]),
        "triggerType": plan["triggerType"],
        "clientOid": plan["clientOid"],
    }
    result = ex.create_order(
        plan["symbol"], plan["orderType"], plan["side"],
        plan["amountContracts"], plan["price"], params,
    )
    return {**result, "executionGuard": guard}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 7 guarded Bitget Demo preflight")
    parser.add_argument("symbol", help="Base symbol or CCXT symbol, for example BTC or BTC/USDT:USDT")
    parser.add_argument("direction", choices=("LONG", "SHORT"))
    parser.add_argument("entry", type=float)
    parser.add_argument("sl", type=float)
    parser.add_argument("tp", type=float)
    parser.add_argument("notional", type=float, help="Estimated notional USDT")
    parser.add_argument("--send", action="store_true", help="Send one Demo order; all hard gates still apply")
    args = parser.parse_args()

    plan = preflight(args.symbol, args.direction, args.entry, args.sl, args.tp, args.notional)
    print(json.dumps({"preflight": plan}, indent=2, ensure_ascii=False))

    if not args.send:
        print("No exchange order sent. Re-run with --send only after demo-key configuration and manual review.")
        return
    print("Sending one order to the Bitget sandbox only...")
    response = send_demo_order(plan)
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
