# Phase 6 — Paper Trading Validation

Phase 6 is an **evaluation workflow**, not an automated strategy approval. It remains paper-only.

## Durable journal and runner

Run one cycle:

```bash
python paper_phase6.py --once
```

Run a 14-day evaluation (default) with a 5-minute cycle:

```bash
python paper_phase6.py --days 14 --interval 300
```

Every position the paper engine opens is appended to `paper_trades.jsonl` with symbol, direction, planned entry levels, SL, TP and notional. When closed, a second record stores fills, exit reason, PnL and the paper engine's estimated fees/slippage. The journal is append-only; back it up and do not edit it during the evaluation. The runner continues to monitor an existing position after a safety stop but prevents new entries when the existing kill switch, daily loss limit or consecutive-loss limit is reached.

The existing paper engine estimates round-trip taker fees at 0.12% of filled notional and models adverse stop gaps. Metrics apply an additional configurable conservative slippage haircut (default 1 bp per side) to the filled notional so results are not treated as fee-free or perfectly executed. Adjust these assumptions to match verified account fee tiers and observed demo slippage.

## Report and strict screening gate

```bash
python paper_metrics.py --journal paper_trades.jsonl --capital 30 \
  --min-trades 30 --min-days 7 --max-dd-pct 25 --slippage-bps-per-side 1
python tes_phase6.py
```

The report includes net expectancy after recorded paper fees plus estimated extra slippage, average R, realized equity drawdown, trades/day, approximate idle time, and major (BTC/ETH/SOL) versus altcoin segments. The default screen requires at least 30 closed trades, 7 observation days, positive expectancy and maximum drawdown no greater than 25% of initial paper capital. It is intentionally not possible to pass with only a few trades. Change thresholds only before the run and record why.

## Operational cautions

- Start the runner after preparing the normal paper inputs (`daftar_ai.json` or existing approved signal snapshots). No AI call or private exchange order is made by this runner.
- It never submits orders and must not be used to infer that a live strategy is safe.
- Daily PnL uses the repository's UTC reset. A consecutive-loss stop stays effective until the consecutive-loss counter is safely reset through the normal state workflow; investigate before manually resetting.
- Idle-time calculation is approximate and only spans observed first-open to last-close intervals. Continuous, unattended operation and host downtime should be documented separately.
- A passing threshold is a minimum research screen only; it is not proof of an edge or permission to progress to demo or live.
