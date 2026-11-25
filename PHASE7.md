# Phase 7 — Bitget Demo Adapter

Phase 7 remains disabled until a dedicated **Bitget Demo API Key** has been configured. It does not read or reuse a live key. The continuous loop also requires manual verification via `DEMO_LOOP_EXECUTION_VERIFIED=on`; keep it `off` until all exchange-side cases are demonstrated.

## Safe preflight

```bash
python demo_phase7.py BTC LONG 65000 63000 68000 10
```

The command loads public market metadata, verifies market minimum/precision and TP/SL geometry, then checks a fresh order book, spread, depth, funding, estimated market impact, and net reward after fees. It rejects marketable post-only prices and sends **nothing** unless `--send` is supplied.

Initial configurable assumptions (verify the actual account schedule before testing):

| Setting | Default | Behavior |
|---|---:|---|
| `DEMO_MAKER_FEE_BPS` | 6 bps/side | Estimated maker entry fee |
| `DEMO_TAKER_FEE_BPS` | 6 bps/side | Conservative exit fee |
| `DEMO_MIN_NET_BPS` | 15 bps | Minimum estimated net target after modeled costs |
| `DEMO_MAX_SPREAD_BPS` | 10 bps | Reject wider spread |
| `DEMO_MIN_BOOK_DEPTH_MULTIPLE` | 5× | Require this notional depth on both sides |
| `DEMO_BOOK_MAX_AGE_SECONDS` | 3 seconds | Reject stale/missing book data |
| `DEMO_MAX_HOLD_HOURS` | 5 hours | Submit reduce-only market exit after timeout |

Funding uses the current funding rate prorated over the configured holding window; it is an estimate, not the exchange's realized funding ledger. Order-book VWAP is a conservative impact estimate, not a fill guarantee.

The entry adapter requests `postOnly=True`. This is not proof of maker execution: confirm the actual UTA v3 request/response and verify an immediately marketable order is rejected or cancelled without a taker fill before enabling the continuous loop.

## Enabling the demo sandbox

Add these values only to `.env`:

```dotenv
MODE=demo
DRY_RUN=off
DEMO_API=on
DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM
DEMO_LOOP_EXECUTION_VERIFIED=off
BITGET_API_KEY=<DEMO API key>
BITGET_SECRET_KEY=<DEMO secret>
BITGET_PASSPHRASE=<DEMO passphrase>
```

Then run:

```bash
python tes_demo_phase7.py
python cek_koneksi.py
python demo_phase7.py BTC LONG 65000 63000 68000 10
```

Only after reviewing the preflight and exchange's exact returned market schema may the same command be retried with `--send`:

```bash
python demo_phase7.py BTC LONG 65000 63000 68000 10 --send
```

The continuous runner is stricter: `uji_demo_unified.py --send-demo` also
requires `DEMO_LOOP_EXECUTION_VERIFIED=on`. Keep it `off` until the complete
loop has passed the order, partial-fill, cancellation, TP/SL, and restart tests
below. The runner refreshes the initial pipeline at startup and after six idle
hours; it will not restart while a Demo position or tracked pending order is
still active. API/reconciliation errors stop new entries instead of being
treated as an empty account.

Before any pipeline starts, the runner reconciles stored client IDs, exchange
order IDs, open orders and positions. Unknown/unobserved submissions stop the
runner and leave state untouched. It records actual fill amount, average fill
price and USDT fees from exchange trades, plus realized USDT funding cash flow
from CCXT `fetch_funding_history`;
if fee/funding history or close fills are missing, PnL is not finalized and new entries remain blocked. Cancels are considered
complete only after a terminal exchange status is observed. A network timeout
after submit is never retried automatically. At the configured hold timeout,
the runner cancels residual entry orders and submits a reduce-only market exit;
an uncertain exit is likewise never resubmitted.

## Paper fill assumptions

The paper engine requires a configurable trade-through (default 1 bps) and
candle close confirmation before an entry/TP is treated as filled. Entry fill
notional per candle is capped at `PAPER_FILL_PARTICIPATION_PCT` (default 1%) of
the candle's estimated quote volume. These are conservative bar-based
assumptions, not order-book queue simulation or evidence of Demo execution.

## Required demo test cases

1. One limit entry in each direction; verify actual post-only status and exchange-side TP/SL triggers.
2. One partial fill and one full fill.
3. Cancellation of the remaining limit levels.
4. TP and SL trigger behavior.
5. Minimum-size rejection and precision rounding.
6. API timeout behavior: verify reconciliation by client ID and prove the runner does not duplicate entry/exit orders.
7. Process restart and reconciliation against open/demo orders.
8. Time exit at the configured hold limit; verify residual entry cancellation and reduce-only closure.
9. Comparison against the Phase 6 paper journal with slippage, fees and variance documented.

## Safe state reset

Stop the runner, inspect the Demo account's positions, open orders and order
history, and resolve any uncertain submit manually. Then run:

```bash
python tes_reset_demo_data.py
python reset_demo_data.py --confirm RESET_DEMO_BERSIH
```

The reset tool requires valid Demo configuration and independently refuses
when the exchange reports any open position/order or when API reconciliation
fails. It backs up the old state and journal under `demo_backups/<timestamp>/`,
resets only `demo_test_state.json`, and preserves `demo_test_trades.jsonl`.
An empty open-order/position response does not itself prove a historical
uncertain order was rejected; the operator must confirm its final history
status before using the confirmation phrase.

Live MODE is hard-rejected. Before live or demo order submission, verify the current official UTA v3 schema and exchange response because CCXT parameter forwarding can change. No Demo result authorizes real capital.
