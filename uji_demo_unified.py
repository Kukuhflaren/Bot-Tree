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
    try:
        result = subprocess.run(
            [sys.executable, str(BASE_DIR / script), *(args or [])],
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        return False, f"{script} timeout setelah 300 detik: {exc}"
    output = (result.stdout + "\n" + result.stderr).strip()
    return result.returncode == 0, output[-6000:]


def read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
            return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def write_json(path: str, value: dict) -> None:
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


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
    return value is True or str(value).strip().lower() in ("1", "true")


def _tracked_orders(orders: list[dict], active: dict) -> list[dict]:
    order_id = str(active.get("exchange_order_id") or "")
    client_oid = str(active.get("client_oid") or "")
    return [
        order for order in orders
        if (order_id and str(order.get("id") or "") == order_id)
        or (client_oid and _client_order_id(order) == client_oid)
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
    tracked = _tracked_orders(orders, active)
    for order in tracked:
        order_id = order.get("id")
        if not order_id:
            raise RuntimeError(
                f"Order pending {active['symbol']} tidak memiliki ID exchange; "
                "reconciliation manual diperlukan"
            )
        try:
            exchange.cancel_order(str(order_id), active["symbol"])
        except Exception as exc:
            raise RuntimeError(
                f"Gagal membatalkan order {order_id}: {type(exc).__name__}: {exc}"
            ) from exc

    remaining = _tracked_orders(open_orders(exchange, [active["symbol"]]), active)
    if remaining:
        print(f"  Cancel belum terkonfirmasi untuk {active['symbol']}; entry baru ditahan.")
        return False
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


def close_demo_trade(exchange, active: dict, trade_id: str, journal: str) -> None:
    symbol = active["symbol"]
    exit_price, reason = find_closed_exit(exchange, symbol, active.get("timestamp"))
    if exit_price is None:
        return
    entry = float(active["entry"])
    notional = float(active["notional"])
    direction = active["direction"]
    gross = notional * ((exit_price / entry - 1) if direction == "LONG"
                        else (1 - exit_price / entry))
    fee = float(active.get("fee_usdt") or 0)
    payload = {
        "event": "closed",
        "trade_id": trade_id,
        "timestamp": now_iso(),
        "entry_timestamp": active["timestamp"],
        "symbol": symbol,
        "direction": direction,
        "entry_average": entry,
        "exit_price": exit_price,
        "exit_reason": reason,
        "stop_loss": active["sl"],
        "take_profit": active["tp"],
        "filled_notional_usdt": notional,
        "gross_pnl_usdt": round(gross, 6),
        "estimated_fees_usdt": fee,
        "net_pnl_usdt": round(gross - fee, 6),
        "mode": "demo",
        "candle_timeframe": active.get("candle_timeframe"),
    }
    paper_journal.append_event(payload, journal)


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
            mark = float(position.get("markPrice") or position.get("entryPrice") or item["entry"])
            unrealized = float(position.get("unrealizedPnl") or 0)
            print(
                f"  {item['symbol']} OPEN entry={item['entry']} mark={mark} "
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
    if not demo_state.get("pipeline_ready"):
        demo_state["pipeline_ready"] = pipeline_awal(pakai_ai)
        if not demo_state["active"] or not demo_state.get("cycle_started_at"):
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
                        if canceled and not item.get("submission_uncertain"):
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
                                        "fee_usdt": 0,
                                        "candle_timeframe": signal.get("candle_timeframe"),
                                        "client_oid": trade_id,
                                        "order_observed": False,
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
                                        "event": "opened",
                                        "trade_id": trade_id,
                                        "timestamp": now_iso(),
                                        "symbol": plan["symbol"],
                                        "direction": direction,
                                        "entry_average": float(level["price"]),
                                        "stop_loss": float(level["sl"]),
                                        "take_profit": float(level["tp"]),
                                        "filled_notional_usdt": float(plan["estimatedNotionalUSDT"]),
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
