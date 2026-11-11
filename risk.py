"""Fase A: modul risk terpusat.

Semua keputusan "boleh order baru?" dan "berapa besar posisi?" lewat sini.
Tidak memanggil exchange. State dibaca dari dict / file state.json nanti.
"""
from __future__ import annotations

from typing import Any

import config


def margin_per_setup(modal_usdt: float | None = None) -> float:
    """Margin (USDT) yang dialokasikan untuk satu setup = RISK_PER_SETUP_PCT% dari modal."""
    modal = config.MODAL_USDT if modal_usdt is None else modal_usdt
    return max(0.0, modal * (config.RISK_PER_SETUP_PCT / 100.0))


def notional_per_setup(modal_usdt: float | None = None) -> float:
    """Notional ≈ margin × leverage (ukuran eksposur di pasar)."""
    return margin_per_setup(modal_usdt) * config.LEVERAGE


def ringkasan_size(modal_usdt: float | None = None) -> dict[str, float]:
    modal = config.MODAL_USDT if modal_usdt is None else modal_usdt
    margin = margin_per_setup(modal)
    notional = margin * config.LEVERAGE
    return {
        "modal_usdt": modal,
        "risk_pct": config.RISK_PER_SETUP_PCT,
        "margin_usdt": round(margin, 4),
        "leverage": config.LEVERAGE,
        "notional_usdt": round(notional, 4),
    }


def boleh_order_baru(state: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Cek pengaman sebelum membuka posisi baru.

    state opsional, bentuk minimal:
      {
        "open_tokens": ["BTC", ...],          # token yang masih terbuka
        "daily_pnl_usdt": -0.5,               # PnL hari ini (negatif = rugi)
        "consecutive_losses": 2,
      }
    """
    state = state or {}

    if config.KILL_SWITCH:
        return False, "KILL_SWITCH aktif"

    if config.DRY_RUN is False and config.MODE == "live":
        # Pengingat: live + dry_run off tetap harus lolos cek di bawah
        pass

    open_tokens = state.get("open_tokens") or []
    if len(open_tokens) >= config.MAX_OPEN_TOKENS:
        return False, f"Sudah {len(open_tokens)} token terbuka (maks {config.MAX_OPEN_TOKENS})"

    daily = float(state.get("daily_pnl_usdt") or 0.0)
    if daily <= -abs(config.MAX_DAILY_LOSS_USDT):
        return False, f"Rugi harian {daily:.2f} USDT menyentuh batas -{config.MAX_DAILY_LOSS_USDT}"

    consec = int(state.get("consecutive_losses") or 0)
    if consec >= config.MAX_CONSECUTIVE_LOSSES:
        return False, f"Rugi beruntun {consec} (maks {config.MAX_CONSECUTIVE_LOSSES})"

    return True, "ok"


def validasi_geometri_risk(risk_atr: float | None, rr: float | None) -> tuple[bool, str]:
    """Cek risk_atr dan RR satu titik grid (dipakai mesin sinyal / paper)."""
    if rr is None or rr < config.RR_MIN:
        return False, f"RR {rr} < min {config.RR_MIN}"
    if risk_atr is None:
        return False, "risk_atr tidak tersedia"
    if risk_atr < config.RISK_ATR_MIN:
        return False, f"risk_atr {risk_atr:.2f} < min {config.RISK_ATR_MIN}"
    if risk_atr > config.RISK_ATR_MAX:
        return False, f"risk_atr {risk_atr:.2f} > max {config.RISK_ATR_MAX}"
    return True, "ok"
