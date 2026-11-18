"""Fase D — Paper Trading Engine.\n\nMensimulasikan grid limit + TP/SL tanpa mengirim order ke Bitget.\nHanya memakai data candle publik. State disimpan di state.json.\n\nAlur:\n  1. Baca sinyal layak (dari penilai_ai.json atau daftar_ai.json + analisis ulang).\n  2. Cek risk.boleh_order_baru(state).\n  3. Buka posisi paper (grid limit pending).\n  4. Setiap candle baru: cek fill limit, TP, SL, lonjakan ekstrem.\n  5. Tutup posisi → hitung PnL setelah fee → update state.\n\nPakai:\n  python paper.py                  # satu siklus (cek sinyal + update posisi)\n  python paper.py --loop           # loop terus (setiap ~60 detik)\n  python paper.py --status         # tampilkan ringkasan state saja\n  python paper.py --reset          # reset state (hati-hati)\n"""
from __future__ import annotations

import argparse
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import config
import data_pasar as dp
import indikator as ik
import penilai_ai as pa
import risk
import state as st

BIAYA_PP = 0.12  # % fee pulang-pergi (perkiraan taker 2 sisi)
FILE_SINYAL = "penilai_ai.json"
FILE_DAFTAR = "daftar_ai.json"

# Slippage paper (konservatif):
# - Limit entry: jika candle gap menembus limit, fill di open (bisa lebih baik/buruk tergantung arah)
# - SL: selalu fill di extreme candle (low untuk long, high untuk short) — adverse
# - TP: diasumsikan limit, fill di harga TP (tanpa slippage positif)
SLIPPAGE_SL = True   # True = SL pakai extreme candle (realistis saat gap)
SLIPPAGE_LIMIT_GAP = True  # True = gap-through limit fill di open


def _waktu_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id_posisi(simbol: str) -> str:
    base = simbol.split("/")[0]
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"paper-{ts}-{base}-{uuid.uuid4().hex[:6]}"
