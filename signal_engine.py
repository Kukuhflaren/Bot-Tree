"""Phase 5 signal pipeline. AI is not imported or called (AI stays disabled).

Input: daftar_ai.json, produced by the existing formula fallback or selector.
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


def build_signal(symbol: str, direction: int, candidate: dict[str, Any], exchange: Any) -> dict[str, Any] | None:
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
    # Existing engine applies stricter conditions than the minimum four; retain
    # them all as hard gates: trend, EMA, MACD, near S/R, VWAP, and 30m trend.
    if not analysis.get("layak") or not valid_levels:
        return None

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
    }


def generate(input_file: str = INPUT_FILE, output_file: str = OUTPUT_FILE) -> dict[str, Any]:
    # AI is intentionally a hard-off default; this engine never invokes AI.
    candidates = _read_candidates(input_file)
    exchange = dp.exchange_publik()
    signals: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    for symbol, direction, candidate in candidates:
        try:
            signal = build_signal(symbol, direction, candidate, exchange)
            if signal:
                signals.append(signal)
            else:
                rejected.append({"symbol": symbol, "reason": "mandatory technical/risk gates not met"})
        except Exception as exc:
            rejected.append({"symbol": symbol, "reason": f"{type(exc).__name__}: {exc}"})

    result = {
        "generated_at": _timestamp(),
        "ai_enabled": False,
        "source_count": len(candidates),
        "bot_ready_count": len(signals),
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
    print("AI disabled; no orders are submitted.")


if __name__ == "__main__":
    main()
