"""Append-only paper trade journal and state-to-journal synchronizer."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

DEFAULT_PATH = "paper_trades.jsonl"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_events(path: str = DEFAULT_PATH) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                    if isinstance(event, dict):
                        events.append(event)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
    except FileNotFoundError:
        return []
    return events


def append_event(event: dict[str, Any], path: str = DEFAULT_PATH) -> None:
    """Append and fsync one JSONL record; fail closed if the audit log cannot be written."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def sync_state(state: dict[str, Any], path: str = DEFAULT_PATH) -> int:
    """Persist newly observed opened/closed paper positions once each.

    Call after every paper cycle. Existing state history is bounded, so keep
    this journal on disk and back it up separately for the full evaluation.
    """
    events = read_events(path)
    known = {(e.get("trade_id"), e.get("event")) for e in events}
    count = 0

    def record_entry(position: dict[str, Any]) -> None:
        nonlocal count
        trade_id = position.get("id")
        key = (trade_id, "opened")
        if not trade_id or key in known:
            return
        payload = {
            "event": "opened",
            "trade_id": trade_id,
            "timestamp": position.get("waktu_buka") or _now(),
            "symbol": position.get("simbol"),
            "direction": "LONG" if int(position.get("arah", 0)) > 0 else "SHORT",
            "entry_levels": position.get("titik_grid") or [],
            "entry_average": position.get("entry_avg"),
            "stop_loss": position.get("sl"),
            "take_profit": position.get("tp"),
            "take_profit_levels": position.get("tp_ladder") or [],
            "take_profit_fraction_per_level": position.get("tp_fraction_per_level"),
            "candle_timeframe": position.get("candle_timeframe"),
            "planned_notional_usdt": position.get("notional"),
            "filled_notional_usdt": position.get(
                "ukuran_masuk_total", position.get("ukuran_terisi", 0),
            ),
            "score": position.get("skor_bot"),
            "risk_reward": position.get("rr_terbaik"),
            "mode": state.get("mode", "paper"),
        }
        append_event(payload, path)
        known.add(key)
        count += 1

    for position in state.get("open_positions") or []:
        record_entry(position)
    for position in state.get("riwayat") or []:
        record_entry(position)
        trade_id = position.get("id")
        key = (trade_id, "closed")
        if not trade_id or key in known or not position.get("hasil"):
            continue
        payload = {
            "event": "closed",
            "trade_id": trade_id,
            "timestamp": position.get("waktu_tutup") or _now(),
            "symbol": position.get("simbol"),
            "direction": "LONG" if int(position.get("arah", 0)) > 0 else "SHORT",
            "entry_timestamp": position.get("waktu_buka"),
            "entry_average": position.get("entry_avg"),
            "stop_loss": position.get("sl"),
            "take_profit": position.get("tp"),
            "exit_price": position["hasil"].get("harga_keluar"),
            "exit_reason": position.get("alasan_tutup"),
            "filled_notional_usdt": position["hasil"].get("notional_terisi", 0),
            "net_pnl_usdt": position["hasil"].get("pnl_bersih", 0),
            "gross_pnl_usdt": position["hasil"].get("pnl_kotor", 0),
            "estimated_fees_usdt": position["hasil"].get("fee", 0),
            "take_profit_events": position.get("tp_events") or [],
            "simulated_slippage_pct": position["hasil"].get("slippage_pct", 0),
            "filled_levels": position["hasil"].get("n_filled", 0),
            "mode": state.get("mode", "paper"),
        }
        append_event(payload, path)
        known.add(key)
        count += 1
    return count
