"""Reset Demo runner state only after explicit clean-account verification."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

import demo_phase7
import uji_demo_unified as unified

CONFIRMATION_TEXT = "RESET_DEMO_BERSIH"
BASE_DIR = Path(__file__).resolve().parent


def reset_demo_data(
    confirmation: str,
    exchange=None,
    state_path: Path | None = None,
    journal_path: Path | None = None,
    backup_root: Path | None = None,
) -> Path:
    if confirmation != CONFIRMATION_TEXT:
        raise ValueError(f"Konfirmasi harus persis {CONFIRMATION_TEXT}")
    accepted, reason = demo_phase7._demo_config_ok()
    if not accepted:
        raise RuntimeError(f"Reset ditolak: {reason}")

    client = exchange or demo_phase7.build_exchange()
    client.load_markets()
    positions = unified.active_positions(client, [])
    orders = unified.open_orders(client)
    if positions or orders:
        raise RuntimeError(
            "Reset ditolak: akun Demo masih memiliki posisi atau open order. "
            "Selesaikan dan verifikasi di exchange terlebih dahulu."
        )

    state_file = state_path or BASE_DIR / unified.DEMO_STATE
    journal_file = journal_path or BASE_DIR / unified.DEMO_JOURNAL
    backup_dir = backup_root or BASE_DIR / "demo_backups"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = backup_dir / stamp
    destination.mkdir(parents=True, exist_ok=False)

    for source in (state_file, journal_file):
        if source.exists():
            shutil.copy2(source, destination / source.name)

    reset_state = {
        "active": {},
        "started": datetime.now(timezone.utc).isoformat(),
        "send_attempts": 0,
        "opened_orders": 0,
        "cycle_started_at": None,
        "pipeline_ready": False,
    }
    temporary = state_file.with_name(state_file.name + ".tmp")
    temporary.write_text(
        json.dumps(reset_state, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(temporary, state_file)
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset state eksperimen Demo setelah akun dipastikan bersih",
    )
    parser.add_argument(
        "--confirm",
        required=True,
        choices=(CONFIRMATION_TEXT,),
        help="Konfirmasi eksplisit setelah memeriksa order/posisi Demo di Bitget",
    )
    args = parser.parse_args()
    backup = reset_demo_data(args.confirm)
    print(f"State Demo direset. Backup state/jurnal: {backup}")
    print("Jurnal demo_test_trades.jsonl tetap dipertahankan.")


if __name__ == "__main__":
    main()
