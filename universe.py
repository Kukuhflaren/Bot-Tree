"""Fase A: universe — blacklist + watchlist.

Dipakai penyaring dan (nanti) mesin sinyal agar filter token konsisten.
"""
from __future__ import annotations

import json
import os

import config


def kena_blacklist(nama_base: str) -> bool:
    """True jika base name cocok pola blacklist (sama / awalan / akhiran)."""
    n = nama_base.upper()
    for pola in config.TOKEN_BLACKLIST:
        if not pola:
            continue
        if n == pola or n.startswith(pola) or n.endswith(pola):
            return True
    return False


def muat_watchlist(path: str | None = None) -> list[str]:
    path = path or config.WATCHLIST_FILE
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    simbol = data.get("simbol") or []
    return [str(s).strip().upper() for s in simbol if str(s).strip()]


def lolos_universe(nama_base: str, watchlist: list[str] | None = None) -> tuple[bool, str]:
    """Apakah base name boleh masuk pipeline.

    Urutan:
      1. Blacklist → tolak
      2. WATCHLIST_MODE=only → harus ada di watchlist
      3. selain itu → lolos
    """
    base = nama_base.upper()
    if kena_blacklist(base):
        return False, "blacklist"

    if config.WATCHLIST_MODE == "only":
        wl = watchlist if watchlist is not None else muat_watchlist()
        if not wl:
            return False, "watchlist kosong (WATCHLIST_MODE=only)"
        if base not in wl:
            return False, "di luar watchlist"

    return True, "ok"
