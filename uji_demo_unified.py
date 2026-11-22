"""Uji terpadu: scanner, paper/Phase 6, dan Demo/Phase 7.

Tanpa --send-demo, semua operasi tetap preflight dan tidak mengirim order.
Dengan --send-demo, satu order Demo dapat dikirim hanya setelah gate Demo
mode/demo/key/confirmation/DRY_RUN dan preflight pasar semuanya lolos.

Pakai:
  python uji_demo_unified.py --once
  python uji_demo_unified.py --days 14 --interval 300 --send-demo
"""
from __future__ import annotations

import argparse
import json
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
import state as st


DEMO_STATE = "demo_test_state.json"
DEMO_JOURNAL = "demo_test_trades.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_command(script: str, args: list[str] | None = None) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, script, *(args or [])],
        capture_output=True,
        text=True,
        timeout=300,
    )
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
    accepted, reason = demo_phase7._demo_config_ok()
    if not accepted:
        return False, reason
    if config.MAX_OPEN_TOKENS < 1:
        return False, "MAX_OPEN_TOKENS harus minimal 1"
    if not st.muat().get("open_positions"):
        return True, "gate demo lolos"
    return True, "gate demo lolos; paper position dapat tetap berjalan terpisah"


def active_positions(exchange, symbols: list[str]) -> dict[str, dict]:
    found = {}
    if not symbols:
        return found
    try:
        rows = exchange.fetch_positions(symbols)
    except Exception:
        try:
            rows = exchange.fetch_positions()
        except Exception:
            rows = []
    for row in rows or []:
        contracts = float(row.get("contracts") or row.get("contractSize") or 0)
        symbol = str(row.get("symbol") or "")
        if contracts and symbol:
            found[symbol] = row
    return found


def find_closed_exit(exchange, symbol: str) -> tuple[float | None, str]:
    try:
        orders = exchange.fetch_closed_orders(symbol, limit=20)
    except Exception:
        return None, "closed_orders tidak tersedia"
    reduce = [order for order in orders or [] if order.get("reduceOnly")]
    candidates = reduce or list(orders or [])
    if not candidates:
        return None, "belum ada closed order"
    latest = max(candidates, key=lambda order: float(order.get("timestamp") or 0))
    price = float(latest.get("average") or latest.get("price") or 0)
    reason = str(latest.get("type") or "closed_order")
    return (price if price > 0 else None), reason


def close_demo_trade(exchange, active: dict, trade_id: str, journal: str) -> None:
    symbol = active["symbol"]
    exit_price, reason = find_closed_exit(exchange, symbol)
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


def load_demo_state() -> dict:
    state = read_json(DEMO_STATE)
    state.setdefault("active", {})
    state.setdefault("started", now_iso())
    state.setdefault("send_attempts", 0)
    state.setdefault("opened_orders", 0)
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
    parser = argparse.ArgumentParser(description="Uji terpadu Demo: scanner + Paper/Phase 6 + Demo/Phase 7")
    parser.add_argument("--days", type=float, default=14, help="Durasi loop Demo")
    parser.add_argument("--interval", type=int, default=300, help="Detik antar putaran")
    parser.add_argument("--once", action="store_true", help="Satu putaran lalu keluar")
    parser.add_argument("--send-demo", action="store_true", help="Izinkan pengiriman order ke akun Demo")
    parser.add_argument("--refresh", action="store_true", help="Refresh penyaring dan signal engine tiap putaran")
    parser.add_argument("--paper-journal", default="paper_trades.jsonl")
    args = parser.parse_args()
    if args.interval < 10:
        parser.error("--interval minimum 10 detik")

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
    exchange = demo_phase7.build_exchange() if args.send_demo and demo_gate()[0] else None

    try:
        while True:
            if args.refresh:
                ok, output = run_command("penyaring.py")
                print("Refresh penyaring:", "OK" if ok else "GAGAL")
                if not ok:
                    print(output[-1000:])
                ok, output = run_command("signal_engine.py")
                print("Refresh signal.json:", "OK" if ok else "GAGAL")
                if not ok:
                    print(output[-1000:])

            ok, output = run_command("scanner.py", ["--sekali", "--refresh-sinyal"] if args.refresh else ["--sekali"])
            print("=== SCANNER / PAPER ===")
            print(output[-4000:] if output else "Scanner selesai tanpa output.")

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
                live = active_positions(exchange, [item["symbol"] for item in active.values()])
                live_symbols = set(live)
                for trade_id in list(active):
                    item = active[trade_id]
                    if item["symbol"] not in live_symbols:
                        close_demo_trade(exchange, item, trade_id, DEMO_JOURNAL)
                        known_closed = {
                            event.get("trade_id")
                            for event in paper_journal.read_events(DEMO_JOURNAL)
                            if event.get("event") == "closed"
                        }
                        if trade_id in known_closed:
                            del active[trade_id]

                for trade_id, item in active.items():
                    position = live.get(item["symbol"])
                    if position:
                        mark = float(position.get("markPrice") or position.get("entryPrice") or item["entry"])
                        unrealized = float(position.get("unrealizedPnl") or 0)
                        print(
                            f"  {item['symbol']} OPEN entry={item['entry']} mark={mark} "
                            f"unrealized={unrealized:+.4f} USDT"
                        )

                if len(active) < config.MAX_OPEN_TOKENS:
                    signals_ok, signal_output = run_command("signal_engine.py")
                    if signals_ok:
                        signal_data = read_json("signal.json")
                        sent = False
                        for signal in signal_data.get("signals", [])[:3]:
                            if len(active) >= config.MAX_OPEN_TOKENS:
                                break
                            direction = str(signal.get("direction", "")).upper()
                            levels = signal.get("entry_levels") or []
                            if not levels:
                                continue
                            level = levels[0]
                            try:
                                plan = demo_phase7.preflight(
                                    signal["symbol"], direction,
                                    float(level["price"]), float(level["sl"]),
                                    float(level["tp"]), float(risk_notional()),
                                )
                                result = demo_phase7.send_demo_order(plan)
                                trade_id = plan["clientOid"]
                                active[trade_id] = {
                                    "timestamp": now_iso(),
                                    "symbol": plan["symbol"],
                                    "direction": direction,
                                    "entry": float(level["price"]),
                                    "sl": float(level["sl"]),
                                    "tp": float(level["tp"]),
                                    "notional": float(plan["estimatedNotionalUSDT"]),
                                    "fee_usdt": 0,
                                    "candle_timeframe": signal.get("candle_timeframe"),
                                }
                                demo_state["send_attempts"] += 1
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
                                sent = True
                                print(
                                    f"  Demo ORDER terkirim: {plan['symbol']} {direction} "
                                    f"entry={level['price']} sl={level['sl']} tp={level['tp']} "
                                    f"notional={plan['estimatedNotionalUSDT']} clientOid={trade_id}"
                                )
                            except Exception as exc:
                                print(f"  Demo ditolak {signal.get('symbol')}: {type(exc).__name__}: {exc}")
                                continue
                            if sent:
                                break
                    else:
                        print("  signal.json gagal refresh.")

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
