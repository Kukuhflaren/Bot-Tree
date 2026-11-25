"""Offline tests for guarded Demo-state reset; no exchange request is sent."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import demo_phase7
import reset_demo_data as reset


class MockExchange:
    def __init__(self, positions=None, orders=None):
        self.positions = positions or []
        self.orders = orders or []

    def load_markets(self):
        return None

    def fetch_positions(self, symbols=None):
        return self.positions

    def fetch_open_orders(self, symbol=None):
        return self.orders


def test_reset_requires_explicit_confirmation():
    with tempfile.TemporaryDirectory() as temp:
        state = Path(temp) / "state.json"
        state.write_text('{"active":{"keep":true}}', encoding="utf-8")
        try:
            reset.reset_demo_data(
                "wrong",
                MockExchange(),
                state,
                Path(temp) / "trades.jsonl",
                Path(temp) / "backup",
            )
        except ValueError as exc:
            assert "Konfirmasi" in str(exc)
        else:
            raise AssertionError("reset must require exact operator confirmation")
        assert '"keep":true' in state.read_text(encoding="utf-8")
    print("[OK] reset requires explicit confirmation and leaves state untouched")


def test_reset_refuses_exchange_activity():
    old_gate = demo_phase7._demo_config_ok
    demo_phase7._demo_config_ok = lambda: (True, "ok")
    try:
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp) / "state.json"
            state.write_text('{"active":{"keep":true}}', encoding="utf-8")
            exchange = MockExchange([{"symbol": "BTC/USDT:USDT", "contracts": 1}])
            try:
                reset.reset_demo_data(
                    reset.CONFIRMATION_TEXT,
                    exchange,
                    state,
                    backup_root=Path(temp) / "backup",
                )
            except RuntimeError as exc:
                assert "masih memiliki posisi" in str(exc)
            else:
                raise AssertionError("reset must refuse while a position is open")
            assert '"keep":true' in state.read_text(encoding="utf-8")
    finally:
        demo_phase7._demo_config_ok = old_gate
    print("[OK] reset refuses positions/open orders before changing state")


def test_clean_reset_backs_up_state_and_preserves_journal():
    old_gate = demo_phase7._demo_config_ok
    demo_phase7._demo_config_ok = lambda: (True, "ok")
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "state.json"
            journal = root / "trades.jsonl"
            backup_root = root / "backups"
            state.write_text('{"active":{"old":true}}', encoding="utf-8")
            journal.write_text('{"event":"closed"}\n', encoding="utf-8")
            exchange = MockExchange()
            backup = reset.reset_demo_data(
                reset.CONFIRMATION_TEXT,
                exchange,
                state,
                journal,
                backup_root,
            )
            result = json.loads(state.read_text(encoding="utf-8"))
            assert result["active"] == {}
            assert journal.read_text(encoding="utf-8") == '{"event":"closed"}\n'
            assert json.loads((backup / "state.json").read_text(encoding="utf-8"))["active"]["old"]
            assert (backup / "trades.jsonl").exists()
    finally:
        demo_phase7._demo_config_ok = old_gate
    print("[OK] clean reset backs up state and retains the audit journal")


def main():
    test_reset_requires_explicit_confirmation()
    test_reset_refuses_exchange_activity()
    test_clean_reset_backs_up_state_and_preserves_journal()
    print("All Demo reset offline tests passed")


if __name__ == "__main__":
    main()
