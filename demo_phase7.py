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
import uuid
from decimal import Decimal
from typing import Any

import ccxt

import bitget_orders
import config

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
    params = {
        "uta": True,
        "marginMode": plan["marginMode"],
        "posSide": plan["posSide"],
        "reduceOnly": plan["reduceOnly"],
        "takeProfitTriggerPrice": str(plan["takeProfitTriggerPrice"]),
        "stopLossTriggerPrice": str(plan["stopLossTriggerPrice"]),
        "triggerType": plan["triggerType"],
        "clientOid": plan["clientOid"],
    }
    result = ex.create_order(
        plan["symbol"], plan["orderType"], plan["side"],
        plan["amountContracts"], plan["price"], params,
    )
    return result


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
