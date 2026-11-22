"""Unit test offline untuk runner Demo terpadu."""
from __future__ import annotations

import uji_demo_unified as unified


class MockExchange:
    def __init__(self, positions=None):
        self.positions = positions or []
        self.closed = {}

    def fetch_positions(self, symbols=None):
        return self.positions

    def fetch_closed_orders(self, symbol, limit=20):
        return self.closed.get(symbol, [])


def test_active_positions_only_counts_nonzero_contracts():
    exchange = MockExchange([
        {"symbol": "BTC/USDT:USDT", "contracts": 1},
        {"symbol": "ETH/USDT:USDT", "contracts": 0},
    ])
    rows = unified.active_positions(exchange, ["BTC/USDT:USDT", "ETH/USDT:USDT"])
    assert "BTC/USDT:USDT" in rows
    assert "ETH/USDT:USDT" not in rows
    print("[OK] active Demo positions ignore zero contracts")


def test_find_closed_exit():
    exchange = MockExchange()
    exchange.closed["BTC/USDT:USDT"] = [
        {"timestamp": 100, "average": 61000, "reduceOnly": True, "type": "limit"},
    ]
    price, reason = unified.find_closed_exit(exchange, "BTC/USDT:USDT")
    assert price == 61000
    assert reason == "limit"
    print("[OK] closed Demo exit read from reduce-only order")


def test_risk_notional_uses_latest_config():
    value = unified.risk_notional()
    assert value > 0
    print(f"[OK] Demo risk notional={value:.4f}")


def main():
    test_active_positions_only_counts_nonzero_contracts()
    test_find_closed_exit()
    test_risk_notional_uses_latest_config()
    print("All unified Demo offline tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
