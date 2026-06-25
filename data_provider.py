"""
data_provider.py — Unified OHLCV accessor for Yahoo Finance cache files.

All functions return clean lists (None values removed unless the raw
variant is explicitly requested).  All indices are aligned: index i
corresponds to the same calendar date across every array returned by
get_ohlcv().
"""

import json
import os
from typing import Any, Dict, List, Optional

CACHE_DIR = "cache"


# ─────────────────────────────────────────────────────────────────────
# INTERNAL HELPERS
# ─────────────────────────────────────────────────────────────────────

def get_stock_data(symbol: str) -> Optional[Dict[str, Any]]:
    filename = os.path.join(CACHE_DIR, f"{symbol}.json")
    if not os.path.exists(filename):
        return None
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception:
        return None


def _quote(symbol: str) -> Optional[Dict[str, Any]]:
    """Return the raw quote dict from the cache, or None."""
    data = get_stock_data(symbol)
    if not data:
        return None
    try:
        return data["chart"]["result"][0]["indicators"]["quote"][0]
    except (KeyError, IndexError, TypeError):
        return None


def _clean(lst: List) -> List:
    """Strip None values from a list."""
    return [x for x in lst if x is not None]


# ─────────────────────────────────────────────────────────────────────
# SINGLE-FIELD ACCESSORS  (backward-compatible)
# ─────────────────────────────────────────────────────────────────────

def get_closes(symbol: str) -> List[float]:
    q = _quote(symbol)
    return _clean(q.get("close", [])) if q else []


def get_opens(symbol: str) -> List[float]:
    q = _quote(symbol)
    return _clean(q.get("open", [])) if q else []


def get_highs(symbol: str) -> List[float]:
    q = _quote(symbol)
    return _clean(q.get("high", [])) if q else []


def get_lows(symbol: str) -> List[float]:
    q = _quote(symbol)
    return _clean(q.get("low", [])) if q else []


def get_volumes(symbol: str) -> List[float]:
    q = _quote(symbol)
    return _clean(q.get("volume", [])) if q else []


def get_timestamps(symbol: str) -> List[int]:
    data = get_stock_data(symbol)
    if not data:
        return []
    try:
        ts = data["chart"]["result"][0].get("timestamp", [])
        return [t for t in ts if t is not None]
    except (KeyError, IndexError, TypeError):
        return []


# ─────────────────────────────────────────────────────────────────────
# ALIGNED OHLCV  (all arrays same length, same index = same date)
# ─────────────────────────────────────────────────────────────────────

def get_ohlcv(symbol: str) -> Dict[str, List]:
    """
    Return a dict with keys: timestamps, opens, highs, lows, closes, volumes.
    Rows where close is None are dropped.  All other fields fall back to the
    close value (opens/highs/lows) or 0 (volumes) when the cache is missing
    that field — this keeps every array the same length.

    Returns an empty dict when the symbol is not cached.
    """
    data = get_stock_data(symbol)
    if not data:
        return {}

    try:
        result    = data["chart"]["result"][0]
        quote     = result["indicators"]["quote"][0]
        ts_raw    = result.get("timestamp", [])
        c_raw     = quote.get("close",  [])
        o_raw     = quote.get("open",   [])
        h_raw     = quote.get("high",   [])
        l_raw     = quote.get("low",    [])
        v_raw     = quote.get("volume", [])
    except (KeyError, IndexError, TypeError):
        return {}

    n = len(c_raw)

    def _pad(lst: List, length: int) -> List:
        lst = list(lst)
        if len(lst) < length:
            lst.extend([None] * (length - len(lst)))
        return lst[:length]

    c_raw = _pad(c_raw, n)
    o_raw = _pad(o_raw, n)
    h_raw = _pad(h_raw, n)
    l_raw = _pad(l_raw, n)
    v_raw = _pad(v_raw, n)
    ts_raw = _pad(ts_raw, n)

    # Keep only rows where close is valid
    rows = [i for i in range(n) if c_raw[i] is not None]
    if not rows:
        return {}

    def _fc(lst, i, fallback):
        v = lst[i]
        return v if v is not None else fallback

    closes  = [c_raw[i]               for i in rows]
    opens   = [_fc(o_raw, i, closes[k]) for k, i in enumerate(rows)]
    highs   = [_fc(h_raw, i, closes[k]) for k, i in enumerate(rows)]
    lows    = [_fc(l_raw, i, closes[k]) for k, i in enumerate(rows)]
    volumes = [_fc(v_raw, i, 0)          for i in rows]
    times   = [ts_raw[i]               for i in rows]

    return {
        "timestamps": times,
        "closes":     closes,
        "opens":      opens,
        "highs":      highs,
        "lows":       lows,
        "volumes":    volumes,
    }
