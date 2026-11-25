"""Offline Phase 7 configuration and payload tests. No API or order is sent."""
from __future__ import annotations

import demo_phase7
import trade_costs


class MockExchange:
    def __init__(self):
        self.sent = []

    def market(self, symbol):
        return {"contractSize": 1}

    def milliseconds(self):
        return 1_000_000

    def fetch_order_book(self, symbol, limit=20):
        return {
            "timestamp": 999_999,
            "bids": [[99.99, 10]],
            "asks": [[100.01, 10]],
        }

    def fetch_funding_rate(self, symbol):
        return {"fundingRate": 0.00001}

    def load_markets(self):
        return None

    def create_order(self, *args):
        self.sent.append(args)
        return {"id": "demo-order-1", "status": "open"}


def test_demo_confirm_text_constant():
    assert demo_phase7.CONFIRMATION_TEXT == "UJI_DEMO_SAYA_PAHAM"
    print("[OK] demo confirmation string is explicit")


def test_ccxt_symbol_normalization():
    assert demo_phase7.ccxt_symbol("BTC") == "BTC/USDT:USDT"
    assert demo_phase7.ccxt_symbol("BTC/USDT:USDT") == "BTC/USDT:USDT"
    print("[OK] CCXT symbol normalization")


def test_live_mode_never_accepted_by_demo_gate(monkeypatch):
    old_mode = demo_phase7.config.MODE
    demo_phase7.config.MODE = "live"
    try:
        accepted, reason = demo_phase7._demo_config_ok()
        assert not accepted
        assert "demo" in reason.lower()
    finally:
        demo_phase7.config.MODE = old_mode
    print("[OK] live MODE is rejected by demo adapter")


def test_orderbook_cost_and_depth_are_validated():
    book = {
        "timestamp": 999_999,
        "bids": [[99.99, 10]],
        "asks": [[100.01, 10]],
    }
    metrics = trade_costs.order_book_metrics(book, 10, 1, 1_000_000, 3, 5)
    assert metrics["spread_bps"] < 10
    assert metrics["bid_depth_usdt"] >= 50
    assert metrics["estimated_round_trip_book_cost_bps"] > 0
    book["timestamp"] = 900_000
    try:
        trade_costs.order_book_metrics(book, 10, 1, 1_000_000, 0.5, 5)
    except ValueError as exc:
        assert "stale" in str(exc)
    else:
        raise AssertionError("stale book must be rejected")
    print("[OK] order book spread, depth, staleness and impact costs are measured")


def test_net_bps_accounts_for_both_fees_and_market_costs():
    gross, net = trade_costs.estimated_net_bps("LONG", 100, 100.5, 6, 6, 4, 1)
    assert abs(gross - 50) < 1e-9
    assert abs(net - 33) < 1e-9
    print("[OK] net reward subtracts entry/exit fee, book impact and funding")


def test_guard_rejects_unprofitable_setup():
    exchange = MockExchange()
    try:
        demo_phase7._execution_guard(exchange, "BTC/USDT:USDT", "LONG", 99.9, 100.0, 10)
    except Exception as exc:
        assert "net" in str(exc).lower()
    else:
        raise AssertionError("setup below minimum net bps must be rejected")
    print("[OK] low-net setup is rejected before submit")


def test_demo_order_is_submitted_post_only(monkeypatch):
    exchange = MockExchange()
    old_gate, old_builder = demo_phase7._demo_config_ok, demo_phase7.build_exchange
    demo_phase7._demo_config_ok = lambda: (True, "ok")
    demo_phase7.build_exchange = lambda: exchange
    plan = {
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "orderType": "limit",
        "amountContracts": 1,
        "price": 99.9,
        "estimatedNotionalUSDT": 10,
        "takeProfitTriggerPrice": 100.5,
        "stopLossTriggerPrice": 99,
        "triggerType": "mark_price",
        "marginMode": "cross",
        "posSide": "long",
        "reduceOnly": False,
        "clientOid": "test-client",
    }
    try:
        result = demo_phase7.send_demo_order(plan)
    finally:
        demo_phase7._demo_config_ok, demo_phase7.build_exchange = old_gate, old_builder
    params = exchange.sent[0][-1]
    assert params["postOnly"] is True
    assert result["id"] == "demo-order-1"
    print("[OK] Demo entry adapter requests post-only maker execution")


def main():
    test_demo_confirm_text_constant()
    test_ccxt_symbol_normalization()
    test_live_mode_never_accepted_by_demo_gate(None)
    test_orderbook_cost_and_depth_are_validated()
    test_net_bps_accounts_for_both_fees_and_market_costs()
    test_guard_rejects_unprofitable_setup()
    test_demo_order_is_submitted_post_only(None)
    print("All Phase 7 offline tests passed")


if __name__ == "__main__":
    main()
