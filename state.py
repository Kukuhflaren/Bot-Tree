"""Manajemen state bot (paper / demo / live).

State disimpan di state.json. Digunakan oleh paper engine dan (nanti) order module.
Tidak memanggil exchange.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

import config

FILE_STATE = "state.json"


def _waktu_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_kosong() -> dict[str, Any]:
    """State awal bersih."""
    return {
        "versi": 1,
        "mode": config.MODE,
        "dibuat": _waktu_iso(),
        "diperbarui": _waktu_iso(),
        "modal_awal": config.MODAL_USDT,
        "modal_saat_ini": config.MODAL_USDT,
        "daily_pnl_usdt": 0.0,
        "daily_reset_tanggal": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "consecutive_losses": 0,
        "total_trades": 0,
        "total_wins": 0,
        "total_losses": 0,
        "open_positions": [],
        "riwayat": [],
        "log": [],
    }


def muat(path: str | None = None) -> dict[str, Any]:
    """Muat state dari file. Jika belum ada, buat state kosong."""
    path = path or FILE_STATE
    if not os.path.isfile(path):
        s = state_kosong()
        simpan(s, path)
        return s
    with open(path, encoding="utf-8") as f:
        s = json.load(f)
    # Reset daily PnL jika hari sudah berganti (UTC)
    hari_ini = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if s.get("daily_reset_tanggal") != hari_ini:
        s["daily_pnl_usdt"] = 0.0
        s["daily_reset_tanggal"] = hari_ini
        s["diperbarui"] = _waktu_iso()
        simpan(s, path)
    return s


def simpan(state: dict[str, Any], path: str | None = None) -> None:
    """Simpan state ke file."""
    path = path or FILE_STATE
    state["diperbarui"] = _waktu_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)


def tambah_log(state: dict[str, Any], pesan: str, level: str = "info") -> None:
    """Tambah entri log (maksimal 200 baris terakhir)."""
    state.setdefault("log", []).append({
        "waktu": _waktu_iso(),
        "level": level,
        "pesan": pesan,
    })
    state["log"] = state["log"][-200:]


def ringkasan(state: dict[str, Any]) -> str:
    """Teks ringkas untuk ditampilkan."""
    open_n = len(state.get("open_positions") or [])
    return (
        f"Mode={state.get('mode')} | Modal={state.get('modal_saat_ini'):.2f} USDT | "
        f"Daily PnL={state.get('daily_pnl_usdt'):+.2f} | "
        f"Open={open_n} | ConsecLoss={state.get('consecutive_losses')} | "
        f"Trades={state.get('total_trades')} (W{state.get('total_wins')}/L{state.get('total_losses')})"
    )
