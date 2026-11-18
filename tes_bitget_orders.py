"""Offline unit tests for Phase E sizing. No network or API credentials needed."""
from __future__ import annotations

from decimal import Decimal

from bitget_orders import OrderPlanError, plan_grid_orders


class FakeExchange:
    def market(self, symbol):
        assert symbol == "BTC/USDT:USDT"
        return {
            "contractSize": 1,
            "limits": {"cost": {"min": 5.0}, "amount": {"min": 0.0001}},
        }

    def amount_to_precision(self, symbol, amount):
        return str(Decimal(str(amount)).quantize(Decimal("0.0001")))


def test_reduce_levels_to_meet_minimum():
    orders = plan_grid_orders(
        FakeExchange(), "BTC/USDT:USDT",
        [{"titik": "S1", "harga": 100, "tp": 110},
         {"titik": "S2", "harga": 99, "tp": 110},
         {"titik": "HL", "harga": 98, "tp": 110}],
        8, max_notional_usdt=8, sl=95, direction="LONG",
    )
    assert len(orders) == 1
    assert orders[0]["estimated_notional_usdt"] >= 5
    assert orders[0]["estimated_notional_usdt"] <= 8
    print("[OK] reduces grid count while satisfying minimum without exceeding budget")


def test_budget_below_minimum_rejected():
    try:
        plan_grid_orders(
            FakeExchange(), "BTC/USDT:USDT",
            [{"titik": "S1", "harga": 100, "tp": 110}],
            4, max_notional_usdt=4, sl=95, direction="LONG",
        )
    except OrderPlanError:
        print("[OK] rejects budget below minimum")
        return
    raise AssertionError("expected minimum-size rejection")


def test_wrong_side_tp_sl_rejected():
    try:
        plan_grid_orders(
            FakeExchange(), "BTC/USDT:USDT",
            [{"titik": "S1", "harga": 100, "tp": 90}],
            8, max_notional_usdt=8, sl=95, direction="LONG",
        )
    except OrderPlanError:
        print("[OK] rejects invalid LONG TP/SL geometry")
        return
    raise AssertionError("expected geometry rejection")


def main():
    test_reduce_levels_to_meet_minimum()
    test_budget_below_minimum_rejected()
    test_wrong_side_tp_sl_rejected()
    print("All Phase E sizing tests passed")


if __name__ == "__main__":
    main()
