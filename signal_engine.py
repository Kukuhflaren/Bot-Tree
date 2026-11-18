"""Phase 5 signal pipeline. AI is not imported or called (AI stays disabled).

Input: daftar_ai.json, restricted to symbols still present on the same side in daftar_40.json.
Output: signal.json with bot-ready setups and the scoring/entry metadata.
This module is signal generation only; it never submits orders.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

import config
import data_pasar as dp
import indikator as ik
import penilai_ai as pa
import universe as uni

INPUT_FILE = "daftar_ai.json"
OUTPUT_FILE = "signal.json"
AI_ENABLED = os.getenv("USE_AI", "off").strip().lower() == "on"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: str, data: Any) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    fd, temp_path = tempfile.mkstemp(prefix=".signal-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _read_candidates(path: str) -> list[tuple[str, int, dict[str, Any]]]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    candidates = []
    for key, direction in (("bullish", 1), ("bearish", -1)):
        for item in data.get(key, []):
            symbol = item.get("simbol")
            if symbol:
                candidates.append((symbol, direction, item))
    return candidates


def build_signal(
    symbol: str, direction: int, candidate: dict[str, Any], exchange: Any,
) -> tuple[dict[str, Any] | None, list[str]]:
    candles = dp.ambil_candle(exchange, symbol, "5m", 300)[:-1]
    candles_30m = dp.ambil_candle(exchange, symbol, "30m", 200)[:-1]
    analysis = ik.analisis(
        candles, direction,
        config.NEAR_SR_PERCENT, config.SCORE_MIN,
        config.NEAR_MODE, config.NEAR_ATR_MULT,
        c30=candles_30m,
    )
    grid = pa.rencana(analysis, direction)
    valid_levels = [level for level in grid if level.get("valid")]
    gagal = pa.kegagalan_gate(analysis, valid_levels)
    if gagal:
        return None, gagal

    direction_name = "LONG" if direction > 0 else "SHORT"
    valid_levels.sort(key=lambda level: level["harga"], reverse=direction < 0)
    best = max(valid_levels, key=lambda level: level.get("rr") or 0)
    return {
        "timestamp": _timestamp(),
        "symbol": symbol,
        "direction": direction_name,
        "entry_levels": [
            {"level": level["titik"], "price": level["harga"], "tp": level["tp"],
             "sl": level["sl"], "risk_atr": level["risk_atr"], "rr": level["rr"]}
            for level in valid_levels
        ],
        "sl": best["sl"],
        "tp": best["tp"],
        "risk_atr": best["risk_atr"],
        "rr": best["rr"],
        "score": analysis["mentah"],
        "score_components": {name: score for name, score in analysis["rincian"]},
        "zone": analysis["zona"],
        "conditions": {
            name: bool(passed) for name, passed in zip(
                ("structure", "ema", "macd", "near_sr", "vwap", "trend_30m"),
                analysis["syarat"],
            )
        },
        "bot_ready": True,
        "ai_enabled": False,
        "source": "formula-only",
        "candidate_24h_change_pct": candidate.get("ubah_24j"),
    }, []


def generate(input_file: str = INPUT_FILE, output_file: str = OUTPUT_FILE) -> dict[str, Any]:
    # AI is intentionally a hard-off default; this engine never invokes AI.
    candidates = _read_candidates(input_file)
    daftar_40 = uni.muat_daftar_40()
    signals: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    gate_counts = {nama: 0 for nama in pa.GATE_NAMES}
    gate_counts["displayed_universe_membership"] = 0
    gate_counts["data_or_runtime_error"] = 0
    accepted_candidates = []
    for symbol, direction, candidate in candidates:
        if not uni.ada_di_daftar_40(symbol, direction, daftar_40):
            rejected.append({"symbol": symbol, "reason": "not in current displayed daftar_40 for this side"})
            gate_counts["displayed_universe_membership"] += 1
            continue
        accepted_candidates.append((symbol, direction, candidate))

    exchange = dp.exchange_publik() if accepted_candidates else None
    for symbol, direction, candidate in accepted_candidates:
        try:
            signal, gagal = build_signal(symbol, direction, candidate, exchange)
            if signal:
                signals.append(signal)
            else:
                rejected.append({"symbol": symbol, "reason": "failed gates: " + ", ".join(gagal)})
                for nama in gagal:
                    gate_counts[nama] += 1
        except Exception as exc:
            rejected.append({"symbol": symbol, "reason": f"{type(exc).__name__}: {exc}"})
            gate_counts["data_or_runtime_error"] += 1

    result = {
        "generated_at": _timestamp(),
        "ai_enabled": False,
        "source_count": len(candidates),
        "bot_ready_count": len(signals),
        "rejection_counts": gate_counts,
        "signals": signals,
        "rejected": rejected,
    }
    _atomic_json(output_file, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Formula-only Bot-Tree signal pipeline")
    parser.add_argument("--input", default=INPUT_FILE)
    parser.add_argument("--output", default=OUTPUT_FILE)
    args = parser.parse_args()
    result = generate(args.input, args.output)
    print(f"Signals: {result['bot_ready_count']}/{result['source_count']} bot-ready -> {args.output}")
    print("Rejection counts (gate failures may overlap):")
    for gate, count in result["rejection_counts"].items():
        print(f"  {gate}: {count}")
    print("AI disabled; no orders are submitted.")


if __name__ == "__main__":
    main()
