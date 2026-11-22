"""Penilaian kelayakan objektif Bot-Tree, terpisah dari pemilih dan penilai teknikal AI.

Seluruh keputusan kelayakan dihitung dari data market dan konfigurasi bot.
AI opsional hanya menerima ringkasan hasil formula dan tidak boleh mengubah hasil.

Pakai:
  python ai_kelayakan.py
  python ai_kelayakan.py BTC ETH SOL
  python ai_kelayakan.py --pakai-ai
"""
from __future__ import annotations

import argparse
import json
import sys

import ai_pemilih as ap
import config
import data_pasar as dp
import indikator as ik
import penilai_ai as pa
import risk
import universe as uni


def min_notional(market: dict, harga: float):
    limits = (market or {}).get("limits") or {}
    candidates = []
    cost = (limits.get("cost") or {}).get("min")
    amount = (limits.get("amount") or {}).get("min")
    contract_size = float((market or {}).get("contractSize") or 1)
    if cost:
        candidates.append(float(cost))
    if amount:
        candidates.append(float(amount) * harga * contract_size)
    return max(candidates) if candidates else None


def susun_token(argumen: list[str]) -> list[str]:
    if argumen:
        return argumen
    data = uni.muat_data_daftar_40()
    watchlist = uni.muat_watchlist()
    watchset = set(watchlist)
    all_names = []
    seen = set()
    for side in ("bullish", "bearish"):
        for item in data[side]:
            name = uni.base_simbol(item["simbol"])
            if name not in seen:
                seen.add(name)
                all_names.append(name)
    prior = [name for name in watchlist if name in seen]
    return prior + [name for name in all_names if name not in watchset]


def nilai_token(exchange, name: str) -> dict:
    symbol = f"{name.upper()}/USDT:USDT"
    candles = dp.ambil_candle(exchange, symbol, config.CANDLE_TIMEFRAME, 300)[:-1]
    if len(candles) < 60:
        return {"nama": name, "harga": None, "layak_bot": False,
                "alasan": ["data candle kurang dari 60"]}

    direction = 1
    if name in {uni.base_simbol(item["simbol"]) for item in uni.muat_data_daftar_40().get("bearish", [])}:
        direction = -1

    analysis = ik.analisis(
        candles, direction,
        config.NEAR_SR_PERCENT, config.SCORE_MIN,
        config.NEAR_MODE, config.NEAR_ATR_MULT,
        c30=candles,
    )
    grid = pa.rencana(analysis, direction)
    valid = [level for level in grid if level.get("valid")]
    failed = pa.kegagalan_gate(analysis, valid)
    price = float(analysis["harga"])
    atr = float(analysis.get("atr") or 0)
    market = (getattr(exchange, "markets", None) or {}).get(symbol) or {}
    minimum = min_notional(market, price)
    notional = risk.notional_per_setup()
    notional_ok = minimum is None or notional >= minimum
    result = {
        "nama": name,
        "simbol": symbol,
        "arah": "LONG" if direction > 0 else "SHORT",
        "harga": price,
        "candle": config.CANDLE_TIMEFRAME,
        "skor_bot": int(analysis["mentah"]),
        "zona": analysis["zona"],
        "atr_persen": round(atr / price * 100, 3) if price else None,
        "syarat": analysis["syarat"],
        "grid_total": len(grid),
        "grid_valid": len(valid),
        "rr_terbaik": max((level.get("rr") or 0 for level in valid), default=None),
        "minimum_notional_usdt": minimum,
        "notional_setup_usdt": notional,
        "minimum_notional_ok": notional_ok,
        "gate_gagal": failed,
        "layak_bot": not failed and notional_ok,
    }
    return result


def prompt_objektif(rows: list[dict]) -> str:
    ringkasan = []
    for row in rows:
        ringkasan.append(
            f"{row['nama']}|arah={row.get('arah','-')}|harga={row.get('harga','-')}|"
            f"candle={row.get('candle','-')}|skor={row.get('skor_bot','-')}|"
            f"grid_valid={row.get('grid_valid','-')}|rr={row.get('rr_terbaik','-')}|"
            f"minimum_ok={row.get('minimum_notional_ok','-')}|gate_gagal={','.join(row.get('gate_gagal',[])) or '-'}"
        )
    return """Kamu adalah penilai objektif kelayakan token untuk bot futures.
Gunakan HANYA angka formula yang diberikan. Jangan mengubah layak_bot, skor, gate, harga, atau minimum notional.
Untuk tiap token berikan verdict: MASUK, TUNGGU, atau TOLAK.
Tugas: beri penjelasan singkat, risiko, dan faktor yang mendukung/menolak. Jangan menjanjikan profit.
Jawab HANYA JSON valid:
{"hasil":[{"simbol":"BTC","verdict":"TUNGGU","alasan":"...","risiko":"..."}]}

DATA FORMULA:
""" + "\n".join(ringkasan)


def main():
    parser = argparse.ArgumentParser(description="AI + formula: cek kelayakan semua atau token terpilih")
    parser.add_argument("simbol", nargs="*", help="Token pilihan, mis. BTC ETH SOL")
    parser.add_argument("--pakai-ai", action="store_true", help="Tambahkan penilaian ringkas AI; formula tetap menentukan layak_bot")
    args = parser.parse_args()
    names = susun_token([name.upper() for name in args.simbol])
    exchange = dp.exchange_publik()
    try:
        exchange.load_markets()
    except Exception as exc:
        print(f"Pasar minimum/precision gagal dimuat: {type(exc).__name__}")

    rows = []
    for name in names:
        try:
            rows.append(nilai_token(exchange, name))
        except Exception as exc:
            rows.append({"nama": name, "layak_bot": False,
                         "alasan": [f"{type(exc).__name__}: {exc}"]})

    ai_hasil = {}
    if args.pakai_ai:
        try:
            ap.cek_jatah()
            text, tokens = ap.panggil_ai(prompt_objektif(rows))
            ap.catat_pakai(tokens)
            data = ap.ambil_json(text)
            ai_hasil = {
                str(item["simbol"]).upper(): item
                for item in (data.get("hasil") or [])
                if isinstance(item, dict) and item.get("simbol")
            }
        except Exception as exc:
            print(f"Penilaian AI dilewati: {type(exc).__name__}: {exc}")

    print(f"\nCek kelayakan {len(rows)} token | candle {config.CANDLE_TIMEFRAME} | "
          f"TP {getattr(config, 'TP_METHOD', 'sr')} | SL {getattr(config, 'SL_METHOD', 'atr')}")
    for row in rows:
        status = "LAYAK" if row["layak_bot"] else "TOLAK"
        gate = ", ".join(row.get("gate_gagal", [])) or "-"
        ai = ai_hasil.get(row["nama"], {})
        ai_text = ""
        if ai:
            ai_text = f" | AI={ai.get('verdict','-')}: {ai.get('alasan','-')} | Risiko={ai.get('risiko','-')}"
        print(
            f"{row['nama']:8} {status:5} {row.get('arah','-'):5} "
            f"harga={row.get('harga','-')} skor={row.get('skor_bot','-')} "
            f"grid={row.get('grid_valid','-')}/{row.get('grid_total','-')} "
            f"RR={row.get('rr_terbaik','-')} gate={gate}{ai_text}"
        )

    layak = sum(1 for row in rows if row["layak_bot"])
    print(f"\nRingkasan formula: {layak}/{len(rows)} layak. "
          "AI tidak dapat mengubah gate, skor, atau keputusan layak_bot.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
