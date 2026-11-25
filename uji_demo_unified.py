"""Continuous scanner paper/Phase 6 and guarded Demo/Phase 7 lifecycle.

Tanpa --send-demo, semua operasi tetap preflight dan tidak mengirim order.
Loop Demo baru dapat mengirim order setelah gate konfigurasi dan verifikasi
manual Phase 7 lolos. Pipeline penuh diulang setelah enam jam tanpa posisi fill.

Pakai:
  python uji_demo_unified.py --once
  python uji_demo_unified.py --days 14 --interval 300 --send-demo
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
import demo_phase7
import paper_journal
import paper_metrics
import paper_phase6
import risk
import state as st


DEMO_STATE = "demo_test_state.json"
DEMO_JOURNAL = "demo_test_trades.jsonl"
BASE_DIR = Path(__file__).resolve().parent
IDLE_RESCAN_SECONDS = 6 * 60 * 60
PIPELINE_STEPS = (
    ("cek_koneksi.py", []),
    ("penyaring.py", []),
    ("cek_risk_universe.py", []),
    ("tes_paper_partial.py", []),
    ("tes_paper_slippage.py", []),
    ("cek_kelayakan.py", []),
    ("signal_engine.py", []),
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(script: str, args: list[str] | None = None) -> tuple[bool, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / script), *(args or [])],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"{script} timeout setelah 300 detik: {exc}"
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    return result.returncode == 0, output[-6000:]


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_json(path: str, value: dict) -> None:
    destination = Path(path)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, destination)


def demo_gate() -> tuple[bool, str]:
    if not getattr(config, "DEMO_LOOP_EXECUTION_VERIFIED", False):
        return False, "DEMO_LOOP_EXECUTION_VERIFIED harus on setelah validasi manual Phase 7"
    accepted, reason = demo_phase7._demo_config_ok()
    if not accepted:
        return False, reason
    if config.MAX_OPEN_TOKENS < 1:
        return False, "MAX_OPEN_TOKENS harus minimal 1"
    if not st.muat().get("open_positions"):
        return True, "gate demo lolos"
    return True, "gate demo lolos; paper position dapat tetap berjalan terpisah"


def active_positions(exchange, symbols: list[str]) -> dict[str, dict]:
    try:
        rows = exchange.fetch_positions(symbols) if symbols else exchange.fetch_positions()
    except Exception as exc:
        raise RuntimeError(f"Gagal merekonsiliasi posisi Demo: {type(exc).__name__}: {exc}") from exc
    found = {}
    for row in rows or []:
        symbol = str(row.get("symbol") or "")
        if row.get("contracts") is None:
            raise RuntimeError(
                f"Exchange tidak memberi ukuran posisi untuk {symbol or 'simbol tidak diketahui'}"
            )
        try:
            contracts = float(row["contracts"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Exchange mengembalikan ukuran posisi yang tidak valid") from exc
        if not math.isfinite(contracts):
            raise RuntimeError("Exchange mengembalikan ukuran posisi yang tidak finite")
        if contracts and symbol:
            if symbol in found:
                raise RuntimeError(
                    f"Exchange mengembalikan beberapa posisi untuk {symbol}; "
                    "rekonsiliasi satu-posisi tidak aman"
                )
            found[symbol] = row
        elif contracts:
            raise RuntimeError("Exchange mengembalikan posisi tanpa simbol")
    return found


def open_orders(exchange, symbols: list[str] | None = None) -> list[dict]:
    try:
        if symbols:
            orders = []
            for symbol in sorted(set(symbols)):
                orders.extend(exchange.fetch_open_orders(symbol))
            return orders
        return list(exchange.fetch_open_orders() or [])
    except Exception as exc:
        raise RuntimeError(f"Gagal merekonsiliasi order Demo: {type(exc).__name__}: {exc}") from exc


def _client_order_id(order: dict) -> str:
    return str(order.get("clientOrderId") or (order.get("info") or {}).get("clientOid") or "")


def _is_reduce_only(order: dict) -> bool:
    value = order.get("reduceOnly")
    if value is None:
        value = (order.get("info") or {}).get("reduceOnly")
    return value is True or str(value).strip().lower() in ("1", "true", "yes")


def _tracked_orders(orders: list[dict], active: dict) -> list[dict]:
    order_ids = {
        str(value) for value in (
            active.get("exchange_order_id"), active.get("exit_order_id"),
        ) if value
    }
    client_oids = {
        str(value) for value in (
            active.get("client_oid"), active.get("exit_client_oid"),
        ) if value
    }
    return [
        order for order in orders
        if str(order.get("id") or "") in order_ids
        or _client_order_id(order) in client_oids
    ]


def find_tracked_closed_order(exchange, active: dict) -> dict | None:
    try:
        orders = exchange.fetch_closed_orders(active["symbol"], limit=20)
    except Exception as exc:
        raise RuntimeError(
            f"Gagal memeriksa status order {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc
    tracked = _tracked_orders(list(orders or []), active)
    return max(tracked, key=lambda order: float(order.get("timestamp") or 0)) if tracked else None


def _filled_amount(order: dict) -> float:
    try:
        return float(order.get("filled") or (order.get("info") or {}).get("baseVolume") or 0)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Exchange mengembalikan jumlah fill order yang tidak valid") from exc


def cancel_tracked_orders(exchange, active: dict, orders: list[dict]) -> bool:
    """Cancel only this trade's tracked entry orders; confirm cancellation before continuing."""
    tracked = [
        order for order in _tracked_orders(orders, active)
        if not _is_reduce_only(order)
    ]
    for order in tracked:
        order_id = order.get("id")
        if not order_id:
            raise RuntimeError(
                f"Order pending {active['symbol']} tidak memiliki ID exchange; "
                "reconciliation manual diperlukan"
            )
        active["cancel_status"] = "requested"
        active["cancel_requested_at"] = now_iso()
        try:
            exchange.cancel_order(str(order_id), active["symbol"])
        except Exception as exc:
            raise RuntimeError(
                f"Gagal membatalkan order {order_id}: {type(exc).__name__}: {exc}"
            ) from exc

    remaining = [
        order for order in _tracked_orders(open_orders(exchange, [active["symbol"]]), active)
        if not _is_reduce_only(order)
    ]
    if remaining:
        print(f"  Cancel belum terkonfirmasi untuk {active['symbol']}; entry baru ditahan.")
        return False
    if tracked or active.get("exchange_order_id"):
        terminal = find_tracked_closed_order(exchange, active)
        if not terminal:
            active["cancel_status"] = "unconfirmed"
            print(f"  Status cancel belum ditemukan untuk {active['symbol']}; entry baru ditahan.")
            return False
        status = str(terminal.get("status") or "").lower()
        if status in ("closed", "filled") or _filled_amount(terminal) > 0:
            active["filled"] = True
            active["cancel_status"] = "filled_during_cancel"
            return True
        if status not in ("canceled", "cancelled", "rejected", "expired"):
            active["cancel_status"] = "unconfirmed"
            return False
    active["cancel_status"] = "confirmed"
    return True


def pipeline_awal(pakai_ai: bool = False) -> bool:
    """Run the required startup checks and candidate pipeline; fail closed on required steps."""
    for script, args in PIPELINE_STEPS:
        ok, output = run_command(script, args)
        print(f"Pipeline {script}: {'OK' if ok else 'GAGAL'}")
        if output:
            print(output[-1200:])
        if not ok:
            return False

    if pakai_ai:
        ok, output = run_command("ai_kelayakan.py", ["--pakai-ai"])
        print(f"Pipeline AI kelayakan (opsional): {'OK' if ok else 'dilewati'}")
        if output:
            print(output[-1200:])
    return True


def refresh_candidates() -> bool:
    """Refresh market universe and formula signals for the regular five-minute scan."""
    for script in ("penyaring.py", "signal_engine.py"):
        ok, output = run_command(script)
        print(f"Refresh {script}: {'OK' if ok else 'GAGAL'}")
        if output:
            print(output[-1200:])
        if not ok:
            return False
    return True


def idle_timeout(demo_state: dict, now: datetime | None = None) -> bool:
    cycle_started = demo_state.get("cycle_started_at")
    if not cycle_started:
        return True
    try:
        started = datetime.fromisoformat(cycle_started)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("cycle_started_at pada demo state tidak valid") from exc
    if started.tzinfo is None:
        raise RuntimeError("cycle_started_at harus memiliki timezone")
    current = now or datetime.now(timezone.utc)
    return (current - started).total_seconds() >= IDLE_RESCAN_SECONDS


def demo_time_exit_due(active: dict, now: datetime | None = None) -> bool:
    opened_at = active.get("first_filled_at") or active.get("timestamp")
    if not opened_at:
        raise RuntimeError("Waktu fill posisi Demo tidak tersedia; time-exit tidak aman")
    try:
        started = datetime.fromisoformat(opened_at)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Waktu fill posisi Demo tidak valid") from exc
    if started.tzinfo is None:
        raise RuntimeError("Waktu fill posisi Demo harus memiliki timezone")
    current = now or datetime.now(timezone.utc)
    return (current - started).total_seconds() >= config.DEMO_MAX_HOLD_HOURS * 3600


def find_closed_exit(
    exchange, symbol: str, after_timestamp: str | None = None,
) -> tuple[float | None, str]:
    try:
        orders = exchange.fetch_closed_orders(symbol, limit=20)
    except Exception as exc:
        raise RuntimeError(f"Gagal membaca closed orders {symbol}: {type(exc).__name__}: {exc}") from exc
    reduce = [order for order in orders or [] if _is_reduce_only(order)]
    if after_timestamp:
        try:
            started = datetime.fromisoformat(after_timestamp).timestamp() * 1000
            reduce = [
                order for order in reduce
                if float(order.get("timestamp") or 0) >= started
            ]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Timestamp order Demo tidak valid") from exc
    candidates = reduce
    if not candidates:
        return None, "belum ada closed reduce-only order untuk trade ini"
    latest = max(candidates, key=lambda order: float(order.get("timestamp") or 0))
    price = float(latest.get("average") or latest.get("price") or 0)
    reason = str(latest.get("type") or "closed_order")
    return (price if price > 0 else None), reason


def _fetch_trade_rows(exchange, active: dict) -> list[dict]:
    method = getattr(exchange, "fetch_my_trades", None)
    if method is None:
        raise RuntimeError("Exchange adapter tidak mendukung fetch_my_trades; akuntansi Demo tidak aman")
    try:
        since = int(datetime.fromisoformat(active["timestamp"]).timestamp() * 1000)
        return list(method(active["symbol"], since=since, limit=1000) or [])
    except Exception as exc:
        raise RuntimeError(
            f"Gagal membaca fill/fee aktual {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc


def _trade_fee_usdt(trades: list[dict]) -> float | None:
    total = 0.0
    for trade in trades:
        fees = trade.get("fees")
        if fees is None:
            fee = trade.get("fee")
            fees = [fee] if fee else []
        if not fees:
            return None
        for fee in fees:
            if (
                not isinstance(fee, dict)
                or fee.get("cost") is None
                or str(fee.get("currency") or "").upper() != "USDT"
            ):
                return None
            try:
                cost = float(fee["cost"])
            except (TypeError, ValueError) as exc:
                raise RuntimeError("Exchange mengembalikan fee aktual yang tidak valid") from exc
            if not math.isfinite(cost):
                raise RuntimeError("Exchange mengembalikan fee aktual yang tidak valid")
            total += abs(cost)
    return total


def _trades_for_order(trades: list[dict], order_id: str) -> list[dict]:
    return [
        trade for trade in trades
        if str(trade.get("order") or (trade.get("info") or {}).get("orderId") or "") == order_id
    ]


def _trade_totals(trades: list[dict]) -> tuple[float, float, float]:
    quantity = 0.0
    weighted_price = 0.0
    for trade in trades:
        try:
            amount = float(trade.get("amount") or 0)
            price = float(trade.get("price") or 0)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Exchange mengembalikan detail fill yang tidak valid") from exc
        if not math.isfinite(amount) or not math.isfinite(price) or amount <= 0 or price <= 0:
            raise RuntimeError("Exchange mengembalikan detail fill yang tidak valid")
        quantity += amount
        weighted_price += amount * price
    if quantity <= 0:
        return 0.0, 0.0, 0.0
    return quantity, weighted_price / quantity, quantity * weighted_price / quantity


def _funding_cashflow_usdt(exchange, active: dict, until_ms: int) -> float:
    method = getattr(exchange, "fetch_funding_history", None)
    if method is None:
        raise RuntimeError("Exchange adapter tidak mendukung fetch_funding_history")
    since_ms = int(datetime.fromisoformat(active["timestamp"]).timestamp() * 1000)
    try:
        rows = method(
            active["symbol"],
            since=since_ms,
            limit=100,
            params={"until": until_ms},
        )
    except Exception as exc:
        raise RuntimeError(
            f"Gagal membaca funding aktual {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc
    cashflow = 0.0
    for row in rows or []:
        details = row.get("info") or {}
        event_type = str(details.get("businessType") or details.get("type") or "").lower()
        if event_type not in ("contract_settle_fee", "funding_fee"):
            continue
        timestamp = row.get("timestamp")
        amount = row.get("amount")
        currency = str(row.get("code") or details.get("coin") or "").upper()
        if timestamp is None or amount is None or currency != "USDT":
            raise RuntimeError("Data funding aktual tidak lengkap atau bukan USDT")
        try:
            timestamp = int(timestamp)
            amount = float(amount)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Exchange mengembalikan funding aktual yang tidak valid") from exc
        if not math.isfinite(amount):
            raise RuntimeError("Exchange mengembalikan funding aktual yang tidak valid")
        if since_ms <= timestamp <= until_ms:
            cashflow += amount
    return cashflow


def _ensure_open_journal(active: dict, trade_id: str, journal: str) -> None:
    existing = paper_journal.read_events(journal)
    if any(event.get("event") == "opened" and event.get("trade_id") == trade_id for event in existing):
        return
    paper_journal.append_event({
        "event": "opened",
        "trade_id": trade_id,
        "timestamp": active.get("timestamp"),
        "symbol": active["symbol"],
        "direction": active["direction"],
        "entry_average": active.get("entry_average"),
        "filled_contracts": active.get("filled_contracts"),
        "filled_notional_usdt": active.get("filled_notional_usdt"),
        "entry_fee_usdt": active.get("entry_fee_usdt"),
        "stop_loss": active["sl"],
        "take_profit": active["tp"],
        "candle_timeframe": active.get("candle_timeframe"),
        "mode": "demo",
    }, journal)


def _reconcile_entry_fills(exchange, active: dict, trade_id: str, journal: str) -> None:
    order_id = str(active.get("exchange_order_id") or "")
    if not order_id:
        active["accounting_pending"] = True
        return
    trades = _trades_for_order(_fetch_trade_rows(exchange, active), order_id)
    if not trades:
        active["accounting_pending"] = True
        return
    quantity, average, _ = _trade_totals(trades)
    try:
        trade_times = [
            float(trade["timestamp"]) for trade in trades
            if trade.get("timestamp") is not None
        ]
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Exchange mengembalikan timestamp fill yang tidak valid") from exc
    if trade_times:
        first_fill_ms = min(trade_times)
        if not math.isfinite(first_fill_ms):
            raise RuntimeError("Exchange mengembalikan timestamp fill yang tidak valid")
        active["first_filled_at"] = datetime.fromtimestamp(
            first_fill_ms / 1000, tz=timezone.utc,
        ).isoformat()
    else:
        active.setdefault("first_filled_at", now_iso())
    fees = _trade_fee_usdt(trades)
    active["filled_contracts"] = quantity
    active["entry_average"] = average
    active["filled"] = quantity > 0
    if fees is None:
        active["accounting_pending"] = True
        return
    market = exchange.market(active["symbol"])
    contract_size = float(market.get("contractSize") or 1)
    active["entry_fee_usdt"] = fees
    active["filled_notional_usdt"] = quantity * contract_size * average
    active["accounting_pending"] = False
    active["open_journaled"] = True
    _ensure_open_journal(active, trade_id, journal)


def _persist_active(active: dict) -> None:
    state = load_demo_state()
    trade_id = str(active.get("client_oid") or "")
    if trade_id:
        state["active"][trade_id] = active
    write_json(DEMO_STATE, state)


def _refresh_exit_order_status(exchange, active: dict, orders: list[dict]) -> None:
    if not active.get("exit_order_id") and not active.get("exit_client_oid"):
        return
    open_exit = [
        order for order in _tracked_orders(orders, active)
        if _is_reduce_only(order)
    ]
    if open_exit:
        latest = max(open_exit, key=lambda order: float(order.get("timestamp") or 0))
        active["exit_order_id"] = str(latest.get("id") or active.get("exit_order_id") or "")
        active["exit_order_status"] = str(latest.get("status") or "open").lower()
        active["exit_submission_uncertain"] = False
        return
    try:
        closed = exchange.fetch_closed_orders(active["symbol"], limit=100)
    except Exception as exc:
        raise RuntimeError(
            f"Gagal memeriksa status time-exit {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc
    exit_id = str(active.get("exit_order_id") or "")
    exit_oid = str(active.get("exit_client_oid") or "")
    terminal_rows = [
        order for order in closed or []
        if _is_reduce_only(order)
        and (
            (exit_id and str(order.get("id") or "") == exit_id)
            or (exit_oid and _client_order_id(order) == exit_oid)
        )
    ]
    terminal = max(terminal_rows, key=lambda order: float(order.get("timestamp") or 0)) if terminal_rows else None
    if terminal:
        active["exit_order_id"] = str(terminal.get("id") or active.get("exit_order_id") or "")
        active["exit_order_status"] = str(terminal.get("status") or "unknown").lower()
        active["exit_filled_contracts"] = _filled_amount(terminal)
        active["exit_submission_uncertain"] = False


def _submit_time_exit(exchange, active: dict, position: dict, orders: list[dict]) -> None:
    if active.get("exit_order_id") or active.get("exit_client_oid"):
        matching = [
            order for order in _tracked_orders(orders, active)
            if _is_reduce_only(order)
        ]
        if matching or active.get("exit_submission_uncertain"):
            return
        if active.get("exit_order_status") in ("closed", "filled"):
            return
        raise RuntimeError("Status time-exit tidak pasti; pengiriman ulang otomatis diblokir")

    if not cancel_tracked_orders(exchange, active, orders):
        return
    quantity = abs(float(position["contracts"]))
    if not math.isfinite(quantity) or quantity <= 0:
        raise RuntimeError("Ukuran posisi tidak valid untuk time-exit")

    client_oid = "bt-exit-" + uuid.uuid4().hex[:16]
    active["exit_client_oid"] = client_oid
    active["exit_submission_uncertain"] = True
    active["exit_requested_at"] = now_iso()
    _persist_active(active)
    side = "sell" if active["direction"] == "LONG" else "buy"
    params = {
        "uta": True,
        "marginMode": "cross",
        "posSide": "long" if active["direction"] == "LONG" else "short",
        "reduceOnly": True,
        "clientOid": client_oid,
    }
    try:
        result = exchange.create_order(
            active["symbol"], "market", side, quantity, None, params,
        )
    except Exception as exc:
        active["exit_submission_uncertain"] = True
        _persist_active(active)
        raise RuntimeError(
            f"Time-exit submit tidak pasti untuk {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc
    if not isinstance(result, dict) or not result.get("id"):
        active["exit_submission_uncertain"] = True
        _persist_active(active)
        raise RuntimeError("Respons time-exit tanpa exchange order ID; retry otomatis diblokir")
    active["exit_order_id"] = str(result["id"])
    active["exit_order_status"] = str(result.get("status") or "submitted").lower()
    active["exit_submission_uncertain"] = False
    _persist_active(active)


def _demo_close_accounting(exchange, active: dict) -> dict | None:
    order_id = str(active.get("exchange_order_id") or "")
    if not order_id:
        return None
    try:
        closed_orders = exchange.fetch_closed_orders(active["symbol"], limit=100)
    except Exception as exc:
        raise RuntimeError(
            f"Gagal membaca closed orders {active['symbol']}: {type(exc).__name__}: {exc}"
        ) from exc
    started_ms = int(datetime.fromisoformat(active["timestamp"]).timestamp() * 1000)
    exit_orders = [
        order for order in closed_orders or []
        if _is_reduce_only(order) and float(order.get("timestamp") or 0) >= started_ms
    ]
    if not exit_orders:
        return None

    trades = _fetch_trade_rows(exchange, active)
    entry_trades = _trades_for_order(trades, order_id)
    exit_order_ids = {str(order.get("id") or "") for order in exit_orders if order.get("id")}
    exit_trades = [
        trade for trade in trades
        if str(trade.get("order") or (trade.get("info") or {}).get("orderId") or "") in exit_order_ids
    ]
    if not entry_trades or not exit_trades:
        return None
    entry_fee = _trade_fee_usdt(entry_trades)
    exit_fee = _trade_fee_usdt(exit_trades)
    if entry_fee is None or exit_fee is None:
        return None

    entry_qty, entry_average, entry_notional = _trade_totals(entry_trades)
    exit_qty, exit_average, _ = _trade_totals(exit_trades)
    tolerance = max(entry_qty * 1e-6, 1e-8)
    if abs(entry_qty - exit_qty) > tolerance:
        return None
    closed_at_ms = max(float(order.get("timestamp") or 0) for order in exit_orders)
    if not closed_at_ms:
        return None
    funding_cashflow = _funding_cashflow_usdt(exchange, active, int(closed_at_ms))
    return {
        "contracts": entry_qty,
        "entry_average": entry_average,
        "entry_notional_usdt": entry_notional,
        "entry_fee_usdt": entry_fee,
        "exit_average": exit_average,
        "exit_fee_usdt": exit_fee,
        "funding_cashflow_usdt": funding_cashflow,
        "exit_reason": str(
            max(exit_orders, key=lambda order: float(order.get("timestamp") or 0)).get("type")
            or "reduce_only"
        ),
    }


def close_demo_trade(exchange, active: dict, trade_id: str, journal: str) -> bool:
    symbol = active["symbol"]
    accounting = _demo_close_accounting(exchange, active)
    if accounting is None:
        active["accounting_pending"] = True
        print(f"  Akuntansi trade {trade_id} belum lengkap; entry baru tetap diblokir.")
        return False
    _ensure_open_journal(active, trade_id, journal)
    entry = accounting["entry_average"]
    exit_price = accounting["exit_average"]
    contracts = accounting["contracts"]
    exchange.load_markets()
    contract_size = float(exchange.market(symbol).get("contractSize") or 1)
    notional = contracts * contract_size * entry
    direction = active["direction"]
    gross = contracts * contract_size * (
        (exit_price - entry) if direction == "LONG" else (entry - exit_price)
    )
    fee = accounting["entry_fee_usdt"] + accounting["exit_fee_usdt"]
    payload = {
        "event": "closed",
        "trade_id": trade_id,
        "timestamp": now_iso(),
        "entry_timestamp": active["timestamp"],
        "symbol": symbol,
        "direction": direction,
        "entry_average": entry,
        "exit_price": exit_price,
        "exit_reason": accounting["exit_reason"],
        "stop_loss": active["sl"],
        "take_profit": active["tp"],
        "filled_contracts": contracts,
        "filled_notional_usdt": notional,
        "gross_pnl_usdt": round(gross, 6),
        "entry_fee_usdt": accounting["entry_fee_usdt"],
        "exit_fee_usdt": accounting["exit_fee_usdt"],
        "actual_fees_usdt": fee,
        "funding_cashflow_usdt": accounting["funding_cashflow_usdt"],
        "net_pnl_usdt": round(gross - fee + accounting["funding_cashflow_usdt"], 6),
        "mode": "demo",
        "candle_timeframe": active.get("candle_timeframe"),
    }
    paper_journal.append_event(payload, journal)
    return True


def reconcile_demo_state(
    exchange, demo_state: dict, journal: str,
) -> tuple[dict[str, dict], bool]:
    """Reconcile persisted bot entries with exchange state; exchange errors remain fatal."""
    active = demo_state["active"]
    positions = active_positions(exchange, [])
    orders = open_orders(exchange)
    trade_closed = False

    for trade_id in list(active):
        item = active[trade_id]
        position = positions.get(item["symbol"])
        tracked = _tracked_orders(orders, item)
        if position:
            item["filled"] = True
            item["order_observed"] = True
            item["submission_uncertain"] = False
            item.setdefault("first_filled_at", now_iso())
            item["filled_contracts"] = abs(float(position["contracts"]))
            item["entry_average"] = float(
                position.get("entryPrice") or item.get("entry_average") or item["entry"]
            )
            mark = float(position.get("markPrice") or position.get("entryPrice") or item["entry"])
            unrealized = float(position.get("unrealizedPnl") or 0)
            _reconcile_entry_fills(exchange, item, trade_id, journal)
            entry_orders = [order for order in tracked if not _is_reduce_only(order)]
            if entry_orders:
                latest_entry = max(entry_orders, key=lambda order: float(order.get("timestamp") or 0))
                item["exchange_order_status"] = str(latest_entry.get("status") or "open").lower()
                item["order_filled_contracts"] = _filled_amount(latest_entry)
                item["order_average_price"] = latest_entry.get("average")
            _refresh_exit_order_status(exchange, item, orders)
            if demo_time_exit_due(item):
                try:
                    _submit_time_exit(exchange, item, position, orders)
                except RuntimeError as exc:
                    print(f"  Time-exit ditahan: {exc}")
            print(
                f"  {item['symbol']} OPEN entry={item.get('entry_average', item['entry'])} mark={mark} "
                f"unrealized={unrealized:+.4f} USDT"
            )
            continue

        if item.get("filled"):
            if not cancel_tracked_orders(exchange, item, orders):
                continue
            close_demo_trade(exchange, item, trade_id, journal)
            known_closed = {
                event.get("trade_id")
                for event in paper_journal.read_events(journal)
                if event.get("event") == "closed"
            }
            if trade_id in known_closed:
                del active[trade_id]
                trade_closed = True
            continue

        if tracked:
            item["order_observed"] = True
            item["submission_uncertain"] = False
            entry_orders = [order for order in tracked if not _is_reduce_only(order)]
            if entry_orders:
                latest_entry = max(entry_orders, key=lambda order: float(order.get("timestamp") or 0))
                item["exchange_order_status"] = str(latest_entry.get("status") or "open").lower()
                item["order_filled_contracts"] = _filled_amount(latest_entry)
                item["order_average_price"] = latest_entry.get("average")
            continue
        if not item.get("order_observed"):
            item["submission_uncertain"] = True
            continue
        if item.get("submission_uncertain"):
            continue
        terminal = find_tracked_closed_order(exchange, item)
        if not terminal:
            item["submission_uncertain"] = True
            continue
        status = str(terminal.get("status") or "").lower()
        if _filled_amount(terminal) > 0 or status in ("closed", "filled"):
            item["filled"] = True
            close_demo_trade(exchange, item, trade_id, journal)
            known_closed = {
                event.get("trade_id")
                for event in paper_journal.read_events(journal)
                if event.get("event") == "closed"
            }
            if trade_id in known_closed:
                del active[trade_id]
                trade_closed = True
        elif status in ("canceled", "cancelled", "rejected", "expired"):
            del active[trade_id]
        else:
            item["submission_uncertain"] = True

    return positions, trade_closed


def has_untracked_activity(
    positions: dict[str, dict], orders: list[dict], active: dict[str, dict],
) -> bool:
    tracked_symbols = {item["symbol"] for item in active.values()}
    if any(symbol not in tracked_symbols for symbol in positions):
        return True
    tracked = [
        order
        for item in active.values()
        for order in _tracked_orders(orders, item)
    ]
    return len(tracked) != len(orders)


def demo_risk_state(journal: str, open_positions: dict[str, dict]) -> dict:
    closed = [
        event for event in paper_journal.read_events(journal)
        if event.get("event") == "closed"
    ]
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        daily_pnl = sum(
            float(event.get("net_pnl_usdt") or 0)
            for event in closed
            if str(event.get("timestamp") or "").startswith(today)
        )
        consecutive_losses = 0
        for event in reversed(closed):
            pnl = float(event.get("net_pnl_usdt") or 0)
            if pnl >= 0:
                break
            consecutive_losses += 1
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Data PnL jurnal Demo tidak valid; entry ditahan") from exc
    return {
        "open_tokens": list(open_positions),
        "daily_pnl_usdt": daily_pnl,
        "consecutive_losses": consecutive_losses,
    }


def load_demo_state() -> dict:
    state = read_json(DEMO_STATE)
    state.setdefault("active", {})
    state.setdefault("started", now_iso())
    state.setdefault("send_attempts", 0)
    state.setdefault("opened_orders", 0)
    state.setdefault("cycle_started_at", None)
    state.setdefault("pipeline_ready", False)
    return state


def print_phase6_metrics(state: dict, journal: str) -> dict:
    events = paper_journal.read_events(journal)
    return paper_metrics.summarize_events(
        events,
        initial_capital=float(state.get("modal_awal") or config.MODAL_USDT),
        min_trades=30,
        min_days=7,
        max_drawdown_pct=25,
        slippage_bps_per_side=1,
    )


def main() -> None:
    os.chdir(BASE_DIR)
    parser = argparse.ArgumentParser(description="Uji terpadu Demo: scanner + Paper/Phase 6 + Demo/Phase 7")
    parser.add_argument("--days", type=float, default=14, help="Durasi loop Demo")
    parser.add_argument("--interval", type=int, default=300, help="Detik antar putaran")
    parser.add_argument("--once", action="store_true", help="Satu putaran lalu keluar")
    parser.add_argument("--send-demo", action="store_true", help="Izinkan pengiriman order ke akun Demo")
    parser.add_argument("--refresh", action="store_true", help="Refresh penyaring dan sinyal tiap scan")
    parser.add_argument("--pakai-ai", action="store_true", help="Jalankan AI kelayakan opsional saat pipeline penuh")
    parser.add_argument("--paper-journal", default="paper_trades.jsonl")
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("--interval minimum 10 detik")
    if args.days <= 0:
        parser.error("--days harus lebih besar dari 0")

    print("=== UJI TERPADU BOT-TREE ===")
    print(f"Mode={config.MODE} | DRY_RUN={config.DRY_RUN} | Candle={config.CANDLE_TIMEFRAME}")
    print(f"TP={getattr(config, 'TP_METHOD', 'sr')} | SL={getattr(config, 'SL_METHOD', 'atr')}")
    print("Paper/Phase 6 tetap diaudit terpisah dari Demo/Phase 7.")

    if args.send_demo:
        accepted, reason = demo_gate()
        if not accepted:
            raise SystemExit(f"Pengiriman Demo ditolak: {reason}")
        print("Gate pengiriman Demo: LOLOS")

    started = datetime.now(timezone.utc)
    deadline = started + timedelta(days=args.days)
    paper_state = st.muat()
    demo_state = load_demo_state()
    demo_state["pipeline_ready"] = False
    exchange = demo_phase7.build_exchange() if args.send_demo else None
    pakai_ai = args.pakai_ai or config.AI_ENABLED
    if args.send_demo and exchange:
        try:
            exchange.load_markets()
            startup_positions, _ = reconcile_demo_state(exchange, demo_state, DEMO_JOURNAL)
            startup_orders = open_orders(exchange)
        except RuntimeError as exc:
            write_json(DEMO_STATE, demo_state)
            raise SystemExit(f"Startup Demo gagal direkonsiliasi; runner dihentikan: {exc}") from exc
        if has_untracked_activity(startup_positions, startup_orders, demo_state["active"]):
            write_json(DEMO_STATE, demo_state)
            raise SystemExit(
                "Startup menemukan posisi/order exchange yang tidak dilacak; "
                "runner Demo dihentikan tanpa reset state."
            )
        unresolved = [
            trade_id for trade_id, item in demo_state["active"].items()
            if item.get("submission_uncertain") or item.get("exit_submission_uncertain")
        ]
        if unresolved:
            write_json(DEMO_STATE, demo_state)
            raise SystemExit(
                "Status submit Demo belum pasti untuk "
                f"{', '.join(unresolved)}; runner dihentikan dan state dipertahankan."
            )
        write_json(DEMO_STATE, demo_state)
    if demo_state["active"] and not demo_state.get("cycle_started_at"):
        demo_state["cycle_started_at"] = min(
            (item.get("timestamp") or now_iso()) for item in demo_state["active"].values()
        )
    if not demo_state["active"]:
        demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
        if not demo_state.get("cycle_started_at"):
            demo_state["cycle_started_at"] = now_iso()
        write_json(DEMO_STATE, demo_state)

    try:
        while True:
            refresh_ok = True
            if args.refresh:
                refresh_ok = refresh_candidates()
                if not refresh_ok:
                    demo_state["pipeline_ready"] = False
                write_json(DEMO_STATE, demo_state)

            scanner_ok, output = run_command(
                "scanner.py",
                ["--sekali", "--refresh-sinyal"] if args.refresh else ["--sekali"],
            )
            print("=== SCANNER / PAPER ===")
            print(output[-4000:] if output else "Scanner selesai tanpa output.")
            if not scanner_ok:
                print("Scanner paper gagal; entry Demo baru ditahan pada putaran ini.")

            paper_state = st.muat()
            paper_phase6.run_cycle(paper_state, args.paper_journal, allow_new=True)
            paper_events = paper_journal.read_events(args.paper_journal)
            paper_report = paper_metrics.summarize_events(
                paper_events,
                initial_capital=float(paper_state.get("modal_awal") or config.MODAL_USDT),
            )
            phase6 = paper_report["phase6_gate"]
            print("=== PHASE 6 / PAPER METRICS ===")
            print(
                f"trades={paper_report['trades']} days={paper_report['duration_days']} "
                f"expectancy={paper_report['expectancy_usdt_per_trade']} "
                f"maxDD={paper_report['max_drawdown_pct_initial_capital']}% "
                f"gate={'LULUS' if phase6['passed'] else 'BELUM LULUS'}"
            )

            print("=== PHASE 7 / DEMO ===")
            if args.send_demo and exchange:
                active = demo_state["active"]
                try:
                    positions, trade_closed = reconcile_demo_state(exchange, demo_state, DEMO_JOURNAL)
                    orders = open_orders(exchange)
                    reconciliation_ok = True
                except RuntimeError as exc:
                    print(f"Rekonsiliasi gagal; entry baru ditahan: {exc}")
                    positions, orders, reconciliation_ok, trade_closed = {}, [], False, False

                if reconciliation_ok and trade_closed and not active:
                    try:
                        positions = active_positions(exchange, [])
                        orders = open_orders(exchange)
                    except RuntimeError as exc:
                        print(f"Verifikasi setelah trade gagal; entry baru ditahan: {exc}")
                        reconciliation_ok = False
                    if reconciliation_ok and not positions and not orders:
                        print("Trade Demo selesai dan order terkait bersih; memulai ulang pipeline.")
                        demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
                        demo_state["cycle_started_at"] = now_iso()

                expired = idle_timeout(demo_state)
                if reconciliation_ok and expired and not any(
                    item.get("filled") for item in active.values()
                ):
                    for trade_id in list(active):
                        item = active[trade_id]
                        try:
                            canceled = cancel_tracked_orders(exchange, item, orders)
                        except RuntimeError as exc:
                            print(f"Cancel gagal; entry baru ditahan: {exc}")
                            canceled = False
                        if canceled and not item.get("submission_uncertain") and not item.get("filled"):
                            del active[trade_id]
                    try:
                        positions = active_positions(exchange, [])
                        orders = open_orders(exchange)
                    except RuntimeError as exc:
                        print(f"Verifikasi cancel gagal; entry baru ditahan: {exc}")
                        reconciliation_ok = False
                    if reconciliation_ok and not active and not positions and not orders:
                        print("Tidak ada entry Demo dalam 6 jam; memulai ulang pipeline.")
                        demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
                        demo_state["cycle_started_at"] = now_iso()
                    elif reconciliation_ok and has_untracked_activity(positions, orders, active):
                        print("Aktivitas exchange tidak dikenal; pipeline dan entry baru ditahan.")

                if reconciliation_ok and not active and not positions and not orders:
                    if not demo_state["pipeline_ready"]:
                        demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
                        demo_state["cycle_started_at"] = now_iso()

                    if args.refresh and refresh_ok:
                        signals_ok, signal_output = True, ""
                    else:
                        signals_ok, signal_output = run_command("signal_engine.py")
                    if not signals_ok:
                        print(f"signal_engine.py gagal; entry Demo ditahan: {signal_output[-1000:]}")
                    elif scanner_ok and refresh_ok and demo_state["pipeline_ready"]:
                        signal_data = read_json("signal.json")
                        if signal_data.get("bot_ready_count", 0) <= 0:
                            print("Tidak ada sinyal formula yang layak.")
                        else:
                            risk_ok, risk_reason = risk.boleh_order_baru(
                                demo_risk_state(DEMO_JOURNAL, positions)
                            )
                            if not risk_ok:
                                print(f"Risk gate: entry Demo ditahan — {risk_reason}")
                                signals = []
                            else:
                                signals = signal_data.get("signals", [])[:3]
                            for signal in signals:
                                direction = str(signal.get("direction", "")).upper()
                                levels = signal.get("entry_levels") or []
                                if not levels:
                                    continue
                                level = levels[0]
                                try:
                                    all_positions = active_positions(exchange, [])
                                    all_orders = open_orders(exchange)
                                    if all_positions or all_orders:
                                        print("Ada posisi/order exchange; entry baru ditahan sampai rekonsiliasi selesai.")
                                        break
                                    risk_ok, risk_reason = risk.boleh_order_baru(
                                        demo_risk_state(DEMO_JOURNAL, all_positions)
                                    )
                                    if not risk_ok:
                                        print(f"Risk gate: entry Demo ditahan — {risk_reason}")
                                        break
                                    plan = demo_phase7.preflight(
                                        signal["symbol"], direction,
                                        float(level["price"]), float(level["sl"]),
                                        float(level["tp"]), float(risk_notional()),
                                    )
                                    trade_id = str(plan["clientOid"])
                                    item = {
                                        "timestamp": now_iso(),
                                        "symbol": plan["symbol"],
                                        "direction": direction,
                                        "entry": float(level["price"]),
                                        "sl": float(level["sl"]),
                                        "tp": float(level["tp"]),
                                        "notional": float(plan["estimatedNotionalUSDT"]),
                                        "candle_timeframe": signal.get("candle_timeframe"),
                                        "client_oid": trade_id,
                                        "order_observed": False,
                                        "submission_uncertain": False,
                                        "execution_guard": plan["executionGuard"],
                                    }
                                    active[trade_id] = item
                                    demo_state["send_attempts"] += 1
                                    write_json(DEMO_STATE, demo_state)
                                    try:
                                        result = demo_phase7.send_demo_order(plan)
                                    except Exception:
                                        item["submission_uncertain"] = True
                                        write_json(DEMO_STATE, demo_state)
                                        raise
                                    if not isinstance(result, dict) or not result.get("id"):
                                        item["submission_uncertain"] = True
                                        write_json(DEMO_STATE, demo_state)
                                        raise RuntimeError(
                                            "Respons submit tidak memiliki ID order; "
                                            "status exchange harus direkonsiliasi manual"
                                        )

                                    item["exchange_order_id"] = str(result.get("id") or "")
                                    write_json(DEMO_STATE, demo_state)
                                    demo_state["opened_orders"] += 1
                                    paper_journal.append_event({
                                        "event": "order_submitted",
                                        "trade_id": trade_id,
                                        "timestamp": now_iso(),
                                        "symbol": plan["symbol"],
                                        "direction": direction,
                                        "exchange_order_id": item["exchange_order_id"],
                                        "order_status": result.get("status"),
                                        "requested_entry": float(level["price"]),
                                        "stop_loss": float(level["sl"]),
                                        "take_profit": float(level["tp"]),
                                        "requested_notional_usdt": float(plan["estimatedNotionalUSDT"]),
                                        "execution_guard": plan["executionGuard"],
                                        "candle_timeframe": signal.get("candle_timeframe"),
                                        "mode": "demo",
                                    }, DEMO_JOURNAL)
                                    print(
                                        f"  Demo ORDER terkirim: {plan['symbol']} {direction} "
                                        f"entry={level['price']} sl={level['sl']} tp={level['tp']} "
                                        f"notional={plan['estimatedNotionalUSDT']} clientOid={trade_id}"
                                    )
                                    break
                                except Exception as exc:
                                    print(f"  Demo ditolak {signal.get('symbol')}: {type(exc).__name__}: {exc}")
                                    break

                write_json(DEMO_STATE, demo_state)
                demo_events = paper_journal.read_events(DEMO_JOURNAL)
                if demo_events:
                    report = paper_metrics.summarize_events(
                        demo_events, initial_capital=float(config.MODAL_DEMO_USDT),
                    )
                    print(
                        f"  Demo trades={report['trades']} closedPnL={report['net_pnl_after_recorded_fees_and_estimated_slippage_usdt']} "
                        f"maxDD={report['max_drawdown_pct_initial_capital']}%"
                    )
                else:
                    print("  Belum ada trade Demo tercatat.")
            else:
                print("  Preflight saja; order Demo tidak dikirim. Tambahkan --send-demo untuk mengirim.")
                if not demo_state["active"] and idle_timeout(demo_state):
                    print("Tidak ada order Demo aktif selama 6 jam; memulai ulang pipeline.")
                    demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
                    demo_state["cycle_started_at"] = now_iso()
                    write_json(DEMO_STATE, demo_state)

            if args.once or datetime.now(timezone.utc) >= deadline:
                break
            print(f"  Tidur {args.interval} detik...\n")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nUji dihentikan oleh operator.")
    finally:
        st.simpan(paper_state)
        write_json(DEMO_STATE, demo_state)

    print("\nHasil akhir:")
    print(f"Paper journal: {args.paper_journal}")
    print(f"Demo journal : {DEMO_JOURNAL}")
    print(f"Demo state   : {DEMO_STATE}")
    print("Tidak ada perintah Live dipanggil.")
    return 0


def risk_notional() -> float:
    return config.MODAL_DEMO_USDT * (config.RISK_PER_SETUP_PCT / 100) * config.LEVERAGE


if __name__ == "__main__":
    raise SystemExit(main())
