"""
sector_utils.py - Safe sector resolution helpers.

Full NSE scanning means many symbols are not covered by the static SECTOR_MAP.
These helpers prevent every unknown stock from being grouped into one fake
"Unknown" sector, which caused misleading sector concentration/correlation text.
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import Dict, Optional

from config import SECTOR_MAP, SECTOR_MASTER_FILE, SECTOR_OVERRIDES, UNMAPPED_SECTOR_LABEL


def normalize_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s:
        return ""
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


@lru_cache(maxsize=1)
def _sector_master() -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not os.path.exists(SECTOR_MASTER_FILE):
        return out
    try:
        with open(SECTOR_MASTER_FILE, "r", newline="", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for row in reader:
                sym = normalize_symbol(row.get("symbol") or row.get("SYMBOL") or row.get("ticker") or "")
                sector = (row.get("sector") or row.get("SECTOR") or row.get("industry") or row.get("INDUSTRY") or "").strip()
                if sym and sector:
                    out[sym] = sector
    except Exception:
        return {}
    return out


@lru_cache(maxsize=1)
def _reverse_sector_map() -> Dict[str, str]:
    out: Dict[str, str] = {}
    for sector, symbols in SECTOR_MAP.items():
        for sym in symbols:
            out[normalize_symbol(sym)] = sector
    return out


def resolve_sector(symbol: str, existing: Optional[str] = None) -> str:
    """Return a trustworthy sector label, or UNMAPPED if unknown."""
    cur = (existing or "").strip()
    if cur and cur.upper() not in ("UNKNOWN", "UNMAPPED", "NONE", "NAN", "NULL", "-"):
        return cur
    sym = normalize_symbol(symbol)
    if not sym:
        return UNMAPPED_SECTOR_LABEL
    if sym in SECTOR_OVERRIDES:
        return SECTOR_OVERRIDES[sym]
    master = _sector_master()
    if sym in master:
        return master[sym]
    rev = _reverse_sector_map()
    if sym in rev:
        return rev[sym]
    return UNMAPPED_SECTOR_LABEL


def is_unmapped_sector(sector: str) -> bool:
    return (sector or "").strip().upper() in ("", "UNKNOWN", "UNMAPPED", UNMAPPED_SECTOR_LABEL.upper())
