"""Unit test offline untuk runner Demo terpadu."""
from __future__ import annotations

import uji_demo_unified as unified


class MockExchange:
    def __init__(self, positions=None):
        self.positions = positions or []
        self.closed = {}
        self.orders = []
        self.cancelled = []

    def fetch_positions(self, symbols=None):
        return self.positions

    def fetch_closed_orders(self, symbol, limit=20):
        return self.closed.get(symbol, [])

    def fetch_open_orders(self, symbol=None):
        if symbol is None:
            return self.orders
        return [order for order in self.orders if order.get("symbol") == symbol]

    def cancel_order(self, order_id, symbol):
        self.cancelled.append((order_id, symbol))
        self.orders = [order for order in self.orders if order.get("id") != order_id]


def test_active_positions_only_counts_nonzero_contracts():
    exchange = MockExchange([
        {"symbol": "BTC/USDT:USDT", "contracts": 1},
        {"symbol": "ETH/USDT:USDT", "contracts": 0},
    ])
    rows = unified.active_positions(exchange, ["BTC/USDT:USDT", "ETH/USDT:USDT"])
    assert "BTC/USDT:USDT" in rows
    assert "ETH/USDT:USDT" not in rows
    print("[OK] active Demo positions ignore zero contracts")


def test_position_lookup_failure_is_not_treated_as_empty():
    class BrokenExchange(MockExchange):
        def fetch_positions(self, symbols=None):
            raise OSError("network unavailable")

    try:
        unified.active_positions(BrokenExchange(), [])
    except RuntimeError as exc:
        assert "Gagal merekonsiliasi posisi" in str(exc)
    else:
        raise AssertionError("position lookup failure must fail closed")
    print("[OK] position lookup failure blocks new entries")


def test_position_without_contract_size_fails_closed():
    exchange = MockExchange([{"symbol": "BTC/USDT:USDT"}])
    try:
        unified.active_positions(exchange, [])
    except RuntimeError as exc:
        assert "tidak memberi ukuran posisi" in str(exc)
    else:
        raise AssertionError("unknown position size must fail closed")
    print("[OK] incomplete position data blocks new entries")


def test_idle_timeout_is_six_hours():
    now = unified.datetime(2026, 1, 1, 6, tzinfo=unified.timezone.utc)
    state = {"cycle_started_at": "2026-01-01T00:00:00+00:00"}
    assert unified.idle_timeout(state, now)
    assert not unified.idle_timeout(
        state, unified.datetime(2026, 1, 1, 5, 59, tzinfo=unified.timezone.utc)
    )
    print("[OK] idle pipeline refresh triggers at six hours")


def test_pending_entry_is_tracked_and_cancelled():
    exchange = MockExchange()
    exchange.orders = [{
        "id": "order-1",
        "symbol": "BTC/USDT:USDT",
        "clientOrderId": "bt-client-1",
    }]
    active = {
        "symbol": "BTC/USDT:USDT",
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
    }

    assert unified.cancel_tracked_orders(exchange, active, exchange.orders)
    assert exchange.cancelled == [("order-1", "BTC/USDT:USDT")]
    assert not exchange.orders
    print("[OK] tracked pending entry is cancelled and verified")


def test_unconfirmed_cancel_keeps_order_active():
    class CancelNotApplied(MockExchange):
        def cancel_order(self, order_id, symbol):
            self.cancelled.append((order_id, symbol))

    exchange = CancelNotApplied()
    exchange.orders = [{
        "id": "order-1",
        "symbol": "BTC/USDT:USDT",
        "clientOrderId": "bt-client-1",
    }]
    active = {
        "symbol": "BTC/USDT:USDT",
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
    }

    assert not unified.cancel_tracked_orders(exchange, active, exchange.orders)
    assert exchange.orders
    print("[OK] unconfirmed cancellation holds the lifecycle")


def test_pending_demo_order_survives_reconciliation():
    exchange = MockExchange()
    exchange.orders = [{
        "id": "order-1",
        "symbol": "BTC/USDT:USDT",
        "clientOrderId": "bt-client-1",
    }]
    state = {"active": {"bt-client-1": {
        "symbol": "BTC/USDT:USDT",
        "entry": 100,
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
    }}}

    positions, closed = unified.reconcile_demo_state(exchange, state, "unused.jsonl")
    assert not positions
    assert not closed
    assert "bt-client-1" in state["active"]
    assert state["active"]["bt-client-1"]["order_observed"]
    print("[OK] pending entry remains active until filled or cancelled")


def test_open_position_keeps_pending_order_until_trade_exit():
    exchange = MockExchange([{
        "symbol": "BTC/USDT:USDT",
        "contracts": 1,
        "entryPrice": 100,
    }])
    exchange.orders = [{
        "id": "order-1",
        "symbol": "BTC/USDT:USDT",
        "clientOrderId": "bt-client-1",
    }]
    state = {"active": {"bt-client-1": {
        "symbol": "BTC/USDT:USDT",
        "entry": 100,
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
    }}}

    unified.reconcile_demo_state(exchange, state, "unused.jsonl")
    assert state["active"]["bt-client-1"]["filled"]
    assert not exchange.cancelled
    assert exchange.orders
    print("[OK] open position is monitored without cancelling its pending entry")


def test_closed_position_cancels_pending_entry_before_restart():
    exchange = MockExchange()
    exchange.orders = [{
        "id": "order-1",
        "symbol": "BTC/USDT:USDT",
        "clientOrderId": "bt-client-1",
    }]
    state = {"active": {"bt-client-1": {
        "timestamp": unified.now_iso(),
        "symbol": "BTC/USDT:USDT",
        "entry": 100,
        "sl": 95,
        "tp": 110,
        "notional": 10,
        "direction": "LONG",
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
        "filled": True,
    }}}
    old_append, old_read, old_exit = (
        unified.paper_journal.append_event,
        unified.paper_journal.read_events,
        unified.find_closed_exit,
    )
    events = []
    unified.paper_journal.append_event = lambda event, _path: events.append(event)
    unified.paper_journal.read_events = lambda _path: events
    unified.find_closed_exit = lambda *_args, **_kwargs: (105, "limit")
    try:
        positions, closed = unified.reconcile_demo_state(exchange, state, "unused.jsonl")
    finally:
        unified.paper_journal.append_event = old_append
        unified.paper_journal.read_events = old_read
        unified.find_closed_exit = old_exit

    assert not positions
    assert closed
    assert not state["active"]
    assert exchange.cancelled == [("order-1", "BTC/USDT:USDT")]
    assert events[0]["event"] == "closed"
    print("[OK] closed position cancels residual entry before the next cycle")


def test_missing_order_status_is_not_assumed_cancelled():
    exchange = MockExchange()
    state = {"active": {"bt-client-1": {
        "symbol": "BTC/USDT:USDT",
        "entry": 100,
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
        "order_observed": True,
    }}}

    unified.reconcile_demo_state(exchange, state, "unused.jsonl")
    assert "bt-client-1" in state["active"]
    assert state["active"]["bt-client-1"]["submission_uncertain"]
    print("[OK] missing order history is held for manual reconciliation")


def test_unobserved_submit_is_held_for_manual_reconciliation():
    exchange = MockExchange()
    state = {"active": {"bt-client-1": {
        "symbol": "BTC/USDT:USDT",
        "entry": 100,
        "exchange_order_id": "order-1",
        "client_oid": "bt-client-1",
        "order_observed": False,
    }}}

    unified.reconcile_demo_state(exchange, state, "unused.jsonl")
    assert state["active"]["bt-client-1"]["submission_uncertain"]
    print("[OK] unobserved submission cannot trigger a duplicate entry")


def test_demo_loop_execution_requires_manual_verification():
    old = unified.config.DEMO_LOOP_EXECUTION_VERIFIED
    unified.config.DEMO_LOOP_EXECUTION_VERIFIED = False
    try:
        accepted, reason = unified.demo_gate()
        assert not accepted
        assert "DEMO_LOOP_EXECUTION_VERIFIED" in reason
    finally:
        unified.config.DEMO_LOOP_EXECUTION_VERIFIED = old
    print("[OK] continuous Demo execution stays locked until verification")


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
    test_position_lookup_failure_is_not_treated_as_empty()
    test_position_without_contract_size_fails_closed()
    test_idle_timeout_is_six_hours()
    test_pending_entry_is_tracked_and_cancelled()
    test_unconfirmed_cancel_keeps_order_active()
    test_pending_demo_order_survives_reconciliation()
    test_open_position_keeps_pending_order_until_trade_exit()
    test_closed_position_cancels_pending_entry_before_restart()
    test_missing_order_status_is_not_assumed_cancelled()
    test_unobserved_submit_is_held_for_manual_reconciliation()
    test_demo_loop_execution_requires_manual_verification()
    test_find_closed_exit()
    test_risk_notional_uses_latest_config()
    print("All unified Demo offline tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
