"""Unit test offline untuk runner Demo terpadu."""
from __future__ import annotations

import uji_demo_unified as unified


class MockExchange:
    def __init__(self, positions=None):
        self.positions = positions or []
        self.closed = {}
        self.orders = []
        self.cancelled = []
        self.trades = []
        self.funding = []

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
        order = next((row for row in self.orders if row.get("id") == order_id), None)
        if order:
            self.closed.setdefault(symbol, []).append({
                **order,
                "status": "canceled",
                "timestamp": 1_800_000_000_000,
            })
        self.orders = [order for order in self.orders if order.get("id") != order_id]

    def fetch_my_trades(self, symbol, since=None, limit=None):
        return self.trades

    def fetch_funding_history(self, symbol, since=None, limit=None, params=None):
        return self.funding

    def market(self, symbol):
        return {"contractSize": 1}

    def load_markets(self):
        return None

    def create_order(self, *args):
        self.created = getattr(self, "created", [])
        self.created.append(args)
        if getattr(self, "fail_create", False):
            raise TimeoutError("network timeout")
        return {"id": "exit-order", "status": "closed"}


def test_run_command_uses_utf8_pipe():
    captured = {}

    class Result:
        returncode = 0
        stdout = "Modal 25 \u2192 margin"
        stderr = ""

    def fake_run(*_args, **kwargs):
        captured.update(kwargs)
        return Result()

    original = unified.subprocess.run
    unified.subprocess.run = fake_run
    try:
        ok, output = unified.run_command("scanner.py", ["--sekali"])
    finally:
        unified.subprocess.run = original
    assert ok
    assert "\u2192" in output
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["env"]["PYTHONIOENCODING"] == "utf-8"
    print("[OK] pipeline subprocess reads UTF-8 instead of the Windows pipe code page")


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


def test_time_exit_clock_starts_at_first_fill():
    submitted = {
        "timestamp": "2026-01-01T00:00:00+00:00",
        "first_filled_at": "2026-01-01T02:00:00+00:00",
    }
    original = unified.config.DEMO_MAX_HOLD_HOURS
    unified.config.DEMO_MAX_HOLD_HOURS = 5
    try:
        assert not unified.demo_time_exit_due(
            submitted, unified.datetime(2026, 1, 1, 6, 59, tzinfo=unified.timezone.utc)
        )
        assert unified.demo_time_exit_due(
            submitted, unified.datetime(2026, 1, 1, 7, 0, tzinfo=unified.timezone.utc)
        )
    finally:
        unified.config.DEMO_MAX_HOLD_HOURS = original
    print("[OK] five-hour timeout starts from the actual first fill, not order submission")


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
        "timestamp": unified.now_iso(),
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
        "timestamp": unified.now_iso(),
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
    exchange.closed["BTC/USDT:USDT"] = [{
        "id": "exit-order",
        "symbol": "BTC/USDT:USDT",
        "timestamp": 1_800_000_000_001,
        "status": "closed",
        "average": 105,
        "reduceOnly": True,
        "type": "market",
    }]
    exchange.trades = [
        {
            "order": "order-1",
            "amount": 1,
            "price": 100,
            "fee": {"cost": 0.06, "currency": "USDT"},
        },
        {
            "order": "exit-order",
            "amount": 1,
            "price": 105,
            "fee": {"cost": 0.063, "currency": "USDT"},
        },
    ]
    exchange.funding = [{
        "timestamp": 1_800_000_000_000,
        "amount": 0.01,
        "code": "USDT",
        "info": {"businessType": "contract_settle_fee"},
    }]
    old_append, old_read, old_exit = (
        unified.paper_journal.append_event,
        unified.paper_journal.read_events,
        unified.find_closed_exit,
    )
    events = []
    unified.paper_journal.append_event = lambda event, _path: events.append(event)
    unified.paper_journal.read_events = lambda _path: events
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
    assert [event["event"] for event in events] == ["opened", "closed"]
    assert events[-1]["actual_fees_usdt"] == 0.123
    assert events[-1]["net_pnl_usdt"] == 4.887
    assert events[-1]["funding_cashflow_usdt"] == 0.01
    print("[OK] close reconciles actual fills, fees, funding and residual cancellation")


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


def test_time_exit_uses_reduce_only_and_does_not_retry_timeout(monkeypatch=None):
    class TimeoutExchange(MockExchange):
        fail_create = True

    exchange = TimeoutExchange()
    item = {
        "symbol": "BTC/USDT:USDT",
        "direction": "LONG",
        "client_oid": "bt-entry-1",
        "entry": 100,
    }
    original_persist = unified._persist_active
    unified._persist_active = lambda _active: None
    try:
        try:
            unified._submit_time_exit(
                exchange, item, {"contracts": 0.25}, [],
            )
        except RuntimeError as exc:
            assert "tidak pasti" in str(exc)
        else:
            raise AssertionError("network timeout must leave exit status uncertain")
        unified._submit_time_exit(exchange, item, {"contracts": 0.25}, [])
    finally:
        unified._persist_active = original_persist
    assert len(exchange.created) == 1
    assert exchange.created[0][1:5] == ("market", "sell", 0.25, None)
    assert exchange.created[0][5]["reduceOnly"] is True
    assert item["exit_submission_uncertain"] is True
    print("[OK] time exit is reduce-only and uncertain submit is never retried")


def test_risk_notional_uses_latest_config():
    value = unified.risk_notional()
    assert value > 0
    print(f"[OK] Demo risk notional={value:.4f}")


def main():
    test_run_command_uses_utf8_pipe()
    test_active_positions_only_counts_nonzero_contracts()
    test_position_lookup_failure_is_not_treated_as_empty()
    test_position_without_contract_size_fails_closed()
    test_idle_timeout_is_six_hours()
    test_time_exit_clock_starts_at_first_fill()
    test_pending_entry_is_tracked_and_cancelled()
    test_unconfirmed_cancel_keeps_order_active()
    test_pending_demo_order_survives_reconciliation()
    test_open_position_keeps_pending_order_until_trade_exit()
    test_closed_position_cancels_pending_entry_before_restart()
    test_missing_order_status_is_not_assumed_cancelled()
    test_unobserved_submit_is_held_for_manual_reconciliation()
    test_demo_loop_execution_requires_manual_verification()
    test_find_closed_exit()
    test_time_exit_uses_reduce_only_and_does_not_retry_timeout()
    test_risk_notional_uses_latest_config()
    print("All unified Demo offline tests passed")


if __name__ == "__main__":
    raise SystemExit(main())
