# Status fase Bot-Tree

Diperbarui: 2026-11-18

| Fase | Isi | Status |
|------|-----|--------|
| **A** | Risk gate, universe, watchlist, blacklist | ✅ Siap (`cek_risk_universe.py`) |
| **B** | Entry/SL/TP tertulis, konfirmasi 30m, grid validasi | ✅ Ada di `indikator.py` + `penilai_ai.py` |
| **C** | Scanner continuous | ✅ `scanner.py` (siklus paper) |
| **D** | Paper engine (fill, partial, slippage, fee, state) | ✅ `paper.py` + `state.py` + unit test |
| **E** | Bitget UTA v3 sizing preflight | 🟡 Implemented; exchange submit intentionally disabled/requires Demo |
| **5** | Formula-only signal pipeline, AI off | ✅ `signal_engine.py` |
| **6** | Paper evaluation, journal and safety workflow | 🟡 Implemented; needs real 1–2 week run |
| **7** | Bitget Demo UTA v3 adapter | 🟡 Preflight, hard demo/live gates and sandbox send adapter; official schema and manual demo tests remain required |
| **8** | Real-money safeguards | ⬜ Not implemented; live submission disabled |
| **9** | Phased real-capital rollout | ⬜ Requires evidence and written thresholds |
| **10** | Dashboard, rTokens, optional AI | ⬜ Later work |

## Demo execution gate

Phase 7 sends no order unless `MODE=demo`, `DRY_RUN=off`, `DEMO_API=on`, the exact demo confirmation is present and Demo API credentials are configured. `MODE=live` is always rejected. Verify the official UTA v3 request/response and test TP/SL, fills, cancels and restart reconciliation before using `--send`.

```bash
python tes_phase6.py
python tes_demo_phase7.py
python demo_phase7.py BTC LONG 65000 63000 68000 10
```
