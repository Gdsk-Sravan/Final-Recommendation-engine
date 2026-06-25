"""
cache_policy.py - Central refresh policy helpers.

Refresh plan
------------
Daily:
  - refresh indices
  - refresh active holdings
  - refresh previously tradable universe
  - refresh high-quality candidates
  - fetch news through staged news modules

Weekly:
  - refresh full NSE symbol list
  - run a full NSE_ALL OHLCV coverage sweep
  - optional sector/fundamental refresh

Smart cache rule
----------------
A GitHub/manual rerun on the same day should not redownload every symbol.
The cache manager now checks the latest candle date inside each Yahoo chart JSON.
If the latest cached candle is already the expected latest completed trading day,
the symbol is skipped even if the workflow is run multiple times.
"""

from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python <3.9 fallback not expected in Actions.
    ZoneInfo = None  # type: ignore

from config import (
    CACHE_DIR,
    CACHE_META_FILE,
    CACHE_REDOWNLOAD_IF_LAST_CANDLE_OLDER_THAN_DAYS,
    CACHE_STALE_CANDLE_RETRY_HOURS,
    CACHE_USE_LATEST_CANDLE_CHECK,
    CONFIDENCE_SCORES_FILE,
    FORCE_FULL_CACHE_REFRESH,
    FORCE_PRICE_REFRESH,
    FORCE_UNIVERSE_REFRESH,
    FULL_CACHE_REFRESH_DAYS,
    FULL_CACHE_REFRESH_WEEKDAY,
    MANUAL_PORTFOLIO_JSON,
    MARKET_DATA_READY_TIME_IST,
    PORTFOLIO_SOURCE,
    NSE_ALL_SYMBOLS_FILE,
    NSE_TRADING_HOLIDAYS_FILE,
    PORTFOLIO_FILE,
    PORTFOLIO_STATE_FILE,
    QUALIFIED_FILE,
    RECOMMENDATIONS_FILE,
    RUN_WEEKLY_JOBS_FORCE,
    STOCKS_FILE,
    TRADABLE_UNIVERSE_FILE,
    UNIVERSE_META_FILE,
    UNIVERSE_REFRESH_DAYS,
    WATCHLIST_FILE,
    WEEKLY_JOB_META_FILE,
    WEEKLY_JOB_REFRESH_DAYS,
)

IST_ZONE = ZoneInfo("Asia/Kolkata") if ZoneInfo else timezone.utc


def now_ist() -> datetime:
    return datetime.now(IST_ZONE)


def today_ist_str() -> str:
    return now_ist().date().isoformat()


def iso_week_key(dt: Optional[datetime] = None) -> str:
    d = dt or now_ist()
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def read_json(path: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if default is None:
        default = {}
    if not os.path.exists(path):
        return dict(default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else dict(default)
    except Exception:
        return dict(default)


def write_json(path: str, payload: Dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST_ZONE)
    except Exception:
        return None


def file_age_hours(path: str) -> Optional[float]:
    if not os.path.exists(path):
        return None
    try:
        age_seconds = datetime.now(timezone.utc).timestamp() - os.path.getmtime(path)
        return age_seconds / 3600.0
    except Exception:
        return None


def file_age_days(path: str) -> Optional[float]:
    hours = file_age_hours(path)
    return None if hours is None else hours / 24.0


def should_refresh_by_age(path: str, max_age_hours: float, force: bool = False) -> bool:
    if force:
        return True
    age = file_age_hours(path)
    return age is None or age > max_age_hours


def normalize_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        return ""
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def dedupe_symbols(symbols: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen: Set[str] = set()
    for raw in symbols:
        sym = normalize_symbol(str(raw))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def read_symbols_from_text(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    symbols: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(line.split(",")[0].strip())
    return dedupe_symbols(symbols)


def read_symbols_from_csv(
    path: str,
    columns: Sequence[str] = ("symbol", "SYMBOL", "ticker", "Ticker"),
) -> List[str]:
    if not os.path.exists(path):
        return []
    symbols: List[str] = []
    try:
        with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
            sample = f.read(2048)
            f.seek(0)
            if "," not in sample:
                return read_symbols_from_text(path)
            reader = csv.DictReader(f)
            for row in reader:
                for col in columns:
                    value = row.get(col)
                    if value:
                        symbols.append(value)
                        break
    except Exception:
        return []
    return dedupe_symbols(symbols)


def read_symbols_auto(path: str) -> List[str]:
    if not os.path.exists(path):
        return []
    if path.lower().endswith(".csv"):
        return read_symbols_from_csv(path)
    return read_symbols_from_text(path)


def read_ranked_symbols(path: str, limit: int = 250) -> List[str]:
    """Read high-quality symbols from CSV or legacy text score files."""
    if not os.path.exists(path):
        return []

    rows: List[Dict[str, Any]] = []

    try:
        with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
            sample = f.read(4096)
            f.seek(0)

            if "," in sample and any(k in sample.lower() for k in ("symbol", "confidence", "score", "trade_quality")):
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = row.get("symbol") or row.get("SYMBOL") or row.get("ticker") or row.get("Ticker")
                    if not symbol:
                        continue

                    score = 0.0
                    for key in (
                        "trade_quality_score",
                        "final_score",
                        "final_confidence",
                        "confidence",
                        "score",
                        "FUSION_SCORE",
                    ):
                        try:
                            if row.get(key) not in (None, ""):
                                score = float(row.get(key, 0) or 0)
                                break
                        except Exception:
                            pass

                    rows.append({"symbol": symbol, "score": score})

            else:
                for line in f:
                    parts = [p.strip() for p in line.strip().split(",")]
                    if not parts or not parts[0]:
                        continue

                    score = 0.0
                    if len(parts) > 1:
                        try:
                            score = float(parts[1])
                        except Exception:
                            score = 0.0

                    rows.append({"symbol": parts[0], "score": score})

    except Exception:
        return []

    rows.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
    return dedupe_symbols([str(r["symbol"]) for r in rows[:limit]])


def cache_file(symbol: str) -> str:
    return os.path.join(CACHE_DIR, f"{symbol}.json")


# -------------------------------------------------------------------
# Trading calendar + latest-candle cache intelligence
# -------------------------------------------------------------------


def _parse_time_hhmm(value: str, default: time = time(16, 15)) -> time:
    try:
        hour_s, minute_s = str(value).strip().split(":")[:2]
        return time(int(hour_s), int(minute_s))
    except Exception:
        return default


def _parse_date_any(value: str) -> Optional[date]:
    text = (value or "").strip()
    if not text:
        return None
    # Strip common CSV clutter.
    text = text.split(",")[0].strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d-%B-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except Exception:
            continue
    return None


def read_trading_holidays() -> Set[date]:
    """Read optional holiday dates from NSE_TRADING_HOLIDAYS_FILE.

    Accepted formats per line/first CSV column:
    YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-Mon-YYYY.
    If the file is absent, weekends are still handled and holidays are simply unknown.
    """
    holidays: Set[date] = set()
    path = NSE_TRADING_HOLIDAYS_FILE
    if not path or not os.path.exists(path):
        return holidays
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parsed = _parse_date_any(line)
                if parsed:
                    holidays.add(parsed)
    except Exception:
        return set()
    return holidays


def is_trading_day(day: date, holidays: Optional[Set[date]] = None) -> bool:
    if day.weekday() >= 5:
        return False
    if holidays is None:
        holidays = read_trading_holidays()
    return day not in holidays


def previous_trading_day(day: date, holidays: Optional[Set[date]] = None) -> date:
    if holidays is None:
        holidays = read_trading_holidays()
    cursor = day - timedelta(days=1)
    safety = 0
    while not is_trading_day(cursor, holidays):
        cursor -= timedelta(days=1)
        safety += 1
        if safety > 14:
            break
    return cursor


def expected_latest_trading_date(now: Optional[datetime] = None) -> date:
    """Return the latest completed daily candle date expected to be available.

    Before MARKET_DATA_READY_TIME_IST on a trading day, the expected candle is
    the previous trading day. After that time, it is today.
    On weekends/holidays, it is the previous trading day.
    """
    dt = now or now_ist()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_ZONE)
    dt = dt.astimezone(IST_ZONE)
    holidays = read_trading_holidays()
    ready_at = _parse_time_hhmm(MARKET_DATA_READY_TIME_IST)
    current_day = dt.date()

    if is_trading_day(current_day, holidays) and dt.time() >= ready_at:
        return current_day
    return previous_trading_day(current_day, holidays)


def _extract_chart_payload(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        result = data.get("chart", {}).get("result") or []
        if not result:
            return None
        return result[0]
    except Exception:
        return None


def extract_latest_candle_info_from_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return latest non-null candle information from Yahoo chart JSON."""
    payload = _extract_chart_payload(data)
    if not payload:
        return {"valid": False, "latest_timestamp": "", "latest_candle_date": "", "bar_count": 0}

    timestamps = payload.get("timestamp") or []
    quote = payload.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close") or []

    if not timestamps or not closes:
        return {"valid": False, "latest_timestamp": "", "latest_candle_date": "", "bar_count": 0}

    latest_ts = ""
    latest_day = ""

    for ts, close in zip(reversed(timestamps), reversed(closes)):
        if ts is None or close is None:
            continue
        try:
            latest_ts = int(ts)
            latest_day = datetime.fromtimestamp(latest_ts, tz=timezone.utc).astimezone(IST_ZONE).date().isoformat()
            break
        except Exception:
            continue

    return {
        "valid": bool(latest_day),
        "latest_timestamp": latest_ts,
        "latest_candle_date": latest_day,
        "bar_count": len([x for x in closes if x is not None]),
    }


def extract_latest_cache_candle_info(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {
            "exists": False,
            "valid": False,
            "latest_timestamp": "",
            "latest_candle_date": "",
            "bar_count": 0,
            "age_hours": None,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        info = extract_latest_candle_info_from_data(data)
        info["exists"] = True
        info["age_hours"] = file_age_hours(path)
        return info
    except Exception:
        return {
            "exists": True,
            "valid": False,
            "latest_timestamp": "",
            "latest_candle_date": "",
            "bar_count": 0,
            "age_hours": file_age_hours(path),
        }


def should_refresh_price_cache(
    path: str,
    max_age_hours: float,
    force: bool = False,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Return a structured cache decision for one OHLCV file.

    Deterministic priority:
    1. Force refresh wins.
    2. Missing/invalid cache is refreshed.
    3. If latest-candle check is enabled and cache is current for the expected
       latest trading day, skip even across repeated manual runs.
    4. If cache is stale by candle date, refresh. If it was just downloaded and
       Yahoo still did not publish the expected candle, wait for
       CACHE_STALE_CANDLE_RETRY_HOURS before trying again.
    5. Fallback to file-age TTL.
    """
    info = extract_latest_cache_candle_info(path)
    age = info.get("age_hours")
    expected_day = expected_latest_trading_date(now).isoformat()
    info["expected_candle_date"] = expected_day

    if force or FORCE_PRICE_REFRESH:
        info.update({"refresh": True, "reason": "force_refresh"})
        return info

    if not info.get("exists"):
        info.update({"refresh": True, "reason": "missing_cache"})
        return info

    if not info.get("valid"):
        info.update({"refresh": True, "reason": "invalid_cache"})
        return info

    latest_day = str(info.get("latest_candle_date") or "")

    if CACHE_USE_LATEST_CANDLE_CHECK:
        if latest_day >= expected_day:
            info.update({"refresh": False, "reason": f"current_candle_{latest_day}"})
            return info

        # If a just-downloaded cache is still behind the expected candle, do not
        # hammer Yahoo on every manual rerun. Try again after a short backoff.
        try:
            latest_dt = datetime.fromisoformat(latest_day).date()
            expected_dt = datetime.fromisoformat(expected_day).date()
            lag_days = (expected_dt - latest_dt).days
        except Exception:
            lag_days = 0

        if age is not None and age < CACHE_STALE_CANDLE_RETRY_HOURS and lag_days <= 1:
            info.update({"refresh": False, "reason": f"stale_candle_retry_backoff_latest_{latest_day}_expected_{expected_day}"})
            return info

        if lag_days >= CACHE_REDOWNLOAD_IF_LAST_CANDLE_OLDER_THAN_DAYS or latest_day < expected_day:
            info.update({"refresh": True, "reason": f"stale_candle_latest_{latest_day}_expected_{expected_day}"})
            return info

    if age is None:
        info.update({"refresh": True, "reason": "unknown_file_age"})
        return info

    if age > max_age_hours:
        info.update({"refresh": True, "reason": f"ttl_expired_{age:.2f}h_gt_{max_age_hours}h"})
        return info

    info.update({"refresh": False, "reason": f"fresh_within_{max_age_hours}h"})
    return info


# -------------------------------------------------------------------
# Manifest / universe / weekly policy
# -------------------------------------------------------------------


def load_cache_manifest() -> Dict[str, Any]:
    return read_json(CACHE_META_FILE, {"symbols": {}, "runs": []})


def save_cache_manifest(manifest: Dict[str, Any]) -> None:
    manifest.setdefault("symbols", {})
    manifest["updated_at"] = now_ist().isoformat()
    write_json(CACHE_META_FILE, manifest)


def mark_symbol_cached(
    manifest: Dict[str, Any],
    symbol: str,
    group: str,
    latest_timestamp: Any = None,
    latest_candle_date: Any = None,
    expected_candle_date: Any = None,
    ok: bool = True,
    error: str = "",
) -> None:
    manifest.setdefault("symbols", {})
    manifest["symbols"][symbol] = {
        "last_attempt_at": now_ist().isoformat(),
        "last_success_at": now_ist().isoformat()
        if ok
        else manifest.get("symbols", {}).get(symbol, {}).get("last_success_at", ""),
        "latest_timestamp": latest_timestamp or "",
        "latest_candle_date": latest_candle_date or "",
        "expected_candle_date": expected_candle_date or "",
        "group": group,
        "ok": bool(ok),
        "error": error,
    }


def should_refresh_universe() -> bool:
    if FORCE_UNIVERSE_REFRESH:
        return True
    if not os.path.exists(NSE_ALL_SYMBOLS_FILE) or os.path.getsize(NSE_ALL_SYMBOLS_FILE) == 0:
        return True
    meta = read_json(UNIVERSE_META_FILE, {})
    last = parse_dt(meta.get("last_success_at"))
    if not last:
        age_days = file_age_days(NSE_ALL_SYMBOLS_FILE)
        return age_days is None or age_days >= UNIVERSE_REFRESH_DAYS
    return (now_ist() - last).total_seconds() / 86400.0 >= UNIVERSE_REFRESH_DAYS


def mark_universe_refreshed(count: int, source: str) -> None:
    meta = read_json(UNIVERSE_META_FILE, {})
    meta.update(
        {
            "last_success_at": now_ist().isoformat(),
            "last_success_date": today_ist_str(),
            "last_success_week": iso_week_key(),
            "count": int(count),
            "source": source,
        }
    )
    write_json(UNIVERSE_META_FILE, meta)


def should_run_full_cache_refresh() -> bool:
    if FORCE_FULL_CACHE_REFRESH:
        return True
    manifest = load_cache_manifest()
    last = parse_dt(manifest.get("last_full_refresh_at"))
    today = now_ist()
    if not last:
        if not os.path.isdir(CACHE_DIR):
            return True
        json_count = len([x for x in os.listdir(CACHE_DIR) if x.endswith(".json")])
        if json_count < 50:
            return True
        return today.weekday() == FULL_CACHE_REFRESH_WEEKDAY
    age_days = (today - last).total_seconds() / 86400.0
    if age_days >= FULL_CACHE_REFRESH_DAYS and today.weekday() == FULL_CACHE_REFRESH_WEEKDAY:
        return True
    return age_days >= (FULL_CACHE_REFRESH_DAYS + 2)


def mark_full_cache_refresh(manifest: Dict[str, Any], symbol_count: int) -> None:
    manifest["last_full_refresh_at"] = now_ist().isoformat()
    manifest["last_full_refresh_date"] = today_ist_str()
    manifest["last_full_refresh_week"] = iso_week_key()
    manifest["last_full_refresh_symbol_count"] = int(symbol_count)


def should_run_weekly_job(job_name: str) -> bool:
    if RUN_WEEKLY_JOBS_FORCE or FORCE_FULL_CACHE_REFRESH:
        return True
    meta = read_json(WEEKLY_JOB_META_FILE, {})
    last = parse_dt(meta.get(job_name, {}).get("last_success_at"))
    today = now_ist()
    if not last:
        return today.weekday() == FULL_CACHE_REFRESH_WEEKDAY
    age_days = (today - last).total_seconds() / 86400.0
    if age_days >= WEEKLY_JOB_REFRESH_DAYS and today.weekday() == FULL_CACHE_REFRESH_WEEKDAY:
        return True
    return age_days >= (WEEKLY_JOB_REFRESH_DAYS + 2)


def mark_weekly_job_success(job_name: str) -> None:
    meta = read_json(WEEKLY_JOB_META_FILE, {})
    meta[job_name] = {
        "last_success_at": now_ist().isoformat(),
        "last_success_date": today_ist_str(),
        "last_success_week": iso_week_key(),
    }
    write_json(WEEKLY_JOB_META_FILE, meta)


def read_active_holdings() -> List[str]:
    symbols: List[str] = []

    # Primary source: real manual holdings from GitHub secret / environment.
    # This avoids refreshing or managing virtual BUY recommendations as if they
    # were real trades.
    if MANUAL_PORTFOLIO_JSON:
        try:
            payload = json.loads(MANUAL_PORTFOLIO_JSON)
            if isinstance(payload, list):
                for row in payload:
                    if isinstance(row, dict):
                        symbol = row.get("symbol") or row.get("SYMBOL")
                        if symbol:
                            symbols.append(str(symbol))
        except Exception:
            pass

    # Fallback after manual_portfolio_loader.py has written portfolio_state.csv.
    if os.path.exists(PORTFOLIO_STATE_FILE):
        try:
            with open(PORTFOLIO_STATE_FILE, "r", newline="", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    status = (row.get("status") or row.get("Status") or "ACTIVE").strip().upper()
                    symbol = row.get("symbol") or row.get("SYMBOL") or row.get("Symbol")
                    if symbol and status in ("ACTIVE", "HOLD", "OPEN", ""):
                        symbols.append(symbol)
        except Exception:
            pass

    # Legacy fallback only when not running in manual-source mode. In MANUAL_ENV,
    # portfolio.txt is ignored to prevent stale virtual recommendations from
    # becoming active holdings again.
    if not PORTFOLIO_SOURCE.upper().startswith("MANUAL") and os.path.exists(PORTFOLIO_FILE):
        symbols.extend(read_symbols_from_text(PORTFOLIO_FILE))

    return dedupe_symbols(symbols)


def read_previously_tradable_symbols(limit: Optional[int] = None) -> List[str]:
    symbols: List[str] = []
    for path in (TRADABLE_UNIVERSE_FILE, QUALIFIED_FILE, STOCKS_FILE):
        symbols.extend(read_symbols_auto(path))
    symbols = dedupe_symbols(symbols)
    return symbols[:limit] if limit else symbols


def read_high_quality_symbols(limit: int = 250) -> List[str]:
    symbols: List[str] = []
    for path in (RECOMMENDATIONS_FILE, WATCHLIST_FILE, CONFIDENCE_SCORES_FILE):
        symbols.extend(read_ranked_symbols(path, limit=limit))
    return dedupe_symbols(symbols)[:limit]
