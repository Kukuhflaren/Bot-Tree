"""Universe: blacklist + watchlist.

WATCHLIST_MODE:
  off    — abaikan watchlist; saring hanya blacklist + volume
  prefer — semua token likuid boleh; watchlist diutamakan saat menyusun daftar_40
  only   — hanya base name di watchlist.json yang boleh lolos
"""
from __future__ import annotations

import json
import os

import config


def kena_blacklist(nama_base: str) -> bool:
    """True jika base name cocok pola blacklist (sama / awalan / akhiran)."""
    if not config.TOKEN_BLACKLIST:
        return False
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


def dalam_watchlist(nama_base: str, watchlist: list[str] | None = None) -> bool:
    wl = watchlist if watchlist is not None else muat_watchlist()
    return nama_base.upper() in wl


def lolos_universe(nama_base: str, watchlist: list[str] | None = None) -> tuple[bool, str]:
    """Apakah base name boleh masuk kandidat likuiditas.

    prefer/off: hanya blacklist yang menolak.
    only: harus ada di watchlist.
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


def prioritaskan_watchlist(daftar: list[dict], watchlist: list[str], jumlah: int) -> list[dict]:
    """Susun ulang: isi watchlist yang ada di daftar didahulukan, sisanya menurut skor.

    Tidak menambah token yang tidak lolos saring volume. Hanya mengubah urutan / jatah slot.
    """
    if not daftar or not watchlist or config.WATCHLIST_MODE != "prefer":
        return sorted(daftar, key=lambda k: k.get("skor", 0), reverse=True)[:jumlah]

    wl = {s.upper() for s in watchlist}
    prioritas = []
    lainnya = []
    for k in daftar:
        base = k["simbol"].split("/")[0].upper()
        if base in wl:
            prioritas.append(k)
        else:
            lainnya.append(k)

    prioritas.sort(key=lambda k: k.get("skor", 0), reverse=True)
    lainnya.sort(key=lambda k: k.get("skor", 0), reverse=True)
    return (prioritas + lainnya)[:jumlah]
