# Phase 7 — Bitget Demo Adapter

Phase 7 remains disabled until a dedicated **Bitget Demo API Key** has been configured. It does not read or reuse a live key.

## Safe preflight

```bash
python demo_phase7.py BTC LONG 65000 63000 68000 10
```

The command loads public market metadata, verifies market minimum/precision, validates TP/SL geometry and prints a complete payload preview. It sends **nothing** unless `--send` is supplied.

## Enabling the demo sandbox

Add these values only to `.env`:

```dotenv
MODE=demo
DRY_RUN=off
DEMO_API=on
DEMO_CONFIRM=UJI_DEMO_SAYA_PAHAM
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

## Required demo test cases

1. One limit entry in each direction, with exchange-side TP and SL trigger fields.
2. One partial fill and one full fill.
3. Cancellation of the remaining limit levels.
4. TP and SL trigger behavior.
5. Minimum-size rejection and precision rounding.
6. API timeout/retry behavior with duplicate client order ID.
7. Process restart and reconciliation against open/demo orders.
8. Comparison against the Phase 6 paper journal with slippage, fees and variance documented.

Live MODE is hard-rejected. Before live or demo order submission, verify the current official UTA v3 schema and exchange response because CCXT parameter forwarding can change. No Demo result authorizes real capital.
