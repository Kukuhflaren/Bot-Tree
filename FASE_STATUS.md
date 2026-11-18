# Status fase Bot-Tree

Diperbarui: 2026-11-18

| Fase | Isi | Status |
|------|-----|--------|
| **A** | Risk gate, universe, watchlist, blacklist | ✅ Siap (`cek_fase_a.py`) |
| **B** | Entry/SL/TP tertulis, konfirmasi 30m, grid validasi | ✅ Ada di `indikator.py` + `penilai_ai.py` |
| **C** | Scanner continuous | ✅ `scanner.py` (siklus paper) |
| **D** | Paper engine (fill, partial, slippage, fee, state) | ✅ `paper.py` + `state.py` + unit test |
| **E** | Bitget UTA v3 order placement + exchange-side TP/SL | 🟡 Sizing/preflight groundwork only; submission deliberately disabled |
| **5** | Formula-only signal pipeline, AI off | ✅ `signal_engine.py` (reads `daftar_ai.json`, outputs `signal.json`) |
| **6** | Paper evaluation, durable trade journal, metrics and safety-stop workflow | 🟡 Implemented locally (`paper_phase6.py`, `paper_journal.py`, `paper_metrics.py`); requires a real 1–2 week run and trade sample |
| **7** | Bitget Demo UTA v3 order verification | ⬜ Blocked on Phase E adapter verification and Demo API Key |
| **8** | Real-money safeguards | ⬜ Not implemented; live order submission is not enabled |
| **9** | Phased real-capital rollout | ⬜ Requires written thresholds and successful demo/paper evidence |
| **10** | Dashboard, rTokens, optional AI second opinion | ⬜ Later work |

## Current safety gate

`bitget_orders.py` only builds and validates offline sizing plans. It does **not** send orders. Phase 6 remains simulated; `paper_phase6.py` uses public data and continues monitoring open paper positions after risk stops while blocking new entries. No phase here authorizes live trading.

## Local checks

```bash
python tes_bitget_orders.py
python tes_phase6.py
python paper_metrics.py --journal paper_trades.jsonl --capital 30
```
