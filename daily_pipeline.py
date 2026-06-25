"""
daily_pipeline.py - Staged, cache-aware orchestration for the stock reviewer.

Performance design
------------------
Do NOT fetch news for the full NSE universe.

Stage 0: load manual portfolio from MANUAL_PORTFOLIO_JSON.
Stage 1: deterministic market-data scan across broad universe.
Stage 2: build a small news universe from top deterministic candidates.
Stage 3: fetch news + AI only for that small set.
Stage 4: rerun fusion with fresh news and create final decisions.

Daily:
  - indices, active holdings, tradable universe, high-quality names are refreshed
  - news is fetched only for top deterministic candidates + active holdings

Weekly:
  - full NSE symbol list refresh
  - full NSE_ALL OHLCV refresh
  - optional fundamentals/sector-map refresh if scripts exist
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from cache_policy import mark_weekly_job_success, should_run_weekly_job
from config import (
    AI_VALIDATION_REPORT_FILE,
    CONFIDENCE_SCORES_FILE,
    ERROR_LOG_FILE,
    MARKET_REGIME_FILE,
    NEWS_FETCH_UNIVERSE_FILE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_STATUS_FILE,
    PRE_NEWS_CANDIDATES_FILE,
    RECOMMENDATIONS_FILE,
    RUN_SUMMARY_FILE,
    SECTOR_SCORES_FILE,
    TRADABLE_UNIVERSE_FILE,
    WATCHLIST_FILE,
)

# Tuple: label, script, optional, extra_env
DAILY_STEPS: List[Tuple[str, str, bool, Optional[Dict[str, str]]]] = [
    ("Build raw universe", "universe_builder.py", False, None),
    ("Load manual portfolio", "manual_portfolio_loader.py", False, None),
    ("Refresh OHLCV cache", "cache_manager.py", False, None),
    ("Validate data quality", "data_quality.py", False, None),
    ("Filter tradable universe", "universe_filter.py", False, None),
    ("Filter volatility", "volatility_filter.py", False, None),
    ("Historical edge", "elite_backtest_v3.py", False, None),
    ("Market regime", "market_regime.py", False, None),
    ("Relative strength", "relative_strength.py", True, None),
    ("Sector rotation", "sector_rotation.py", False, None),
    ("Entry quality", "entry_quality.py", False, None),

    # First fusion pass. This creates confidence_scores.csv using market data.
    # pre_news_selector.py then ignores the news component and ranks by deterministic components.
    ("First-pass deterministic fusion", "fusion_scanner_v7.py", False, {"PIPELINE_STAGE": "PRE_NEWS"}),
    ("Select small news universe", "pre_news_selector.py", False, None),

    # Slow I/O only after universe has been reduced.
    ("Fetch news for selected names", "news_fetcher_v2.py", True, None),
    ("Score keyword news", "news_engine_v2.py", True, None),
    ("AI news risk review", "ai_news_engine.py", True, None),

    # Final fusion pass uses fresh news scores for selected candidates and neutral/default news elsewhere.
    ("Final fusion with news", "fusion_scanner_v7.py", False, {"PIPELINE_STAGE": "FINAL_WITH_NEWS"}),
    ("Recommendation buckets", "recommendation_engine_v6.py", False, None),
    ("Position sizing", "position_sizer.py", True, None),
    ("Portfolio monitor", "portfolio_monitor.py", False, None),
    ("Correlation report", "correlation_engine.py", True, None),
    ("AI second-pass brief", "ai_second_pass.py", True, None),
    ("Telegram report", "telegram_notify.py", True, None),
]

# Optional weekly jobs. Missing files are skipped safely.
WEEKLY_STEPS: List[Tuple[str, bool, str]] = [
    ("sector_map_refresher.py", True, "sector_map_refresh"),
    ("fundamentals_fetcher.py", True, "fundamentals_fetch"),
    ("yahoo_fundamentals_fetcher.py", True, "yahoo_fundamentals_fetch"),
    ("fundamental_score_generator_v2.py", True, "fundamental_score_generation"),
]

CRITICAL_OUTPUTS = [
    TRADABLE_UNIVERSE_FILE,
    MARKET_REGIME_FILE,
    SECTOR_SCORES_FILE,
    CONFIDENCE_SCORES_FILE,
    RECOMMENDATIONS_FILE,
    WATCHLIST_FILE,
    PORTFOLIO_STATE_FILE,
    PORTFOLIO_STATUS_FILE,
]

PRE_TELEGRAM_OUTPUTS = [
    PRE_NEWS_CANDIDATES_FILE,
    NEWS_FETCH_UNIVERSE_FILE,
]


def _run_step(script: str, optional: bool, extra_env: Optional[Dict[str, str]] = None) -> Tuple[bool, str]:
    if not os.path.exists(script):
        msg = f"MISSING {script}"
        return (optional, msg)

    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)

    proc = subprocess.run(
        [sys.executable, script],
        text=True,
        capture_output=True,
        env=env,
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    ok = proc.returncode == 0

    if not ok and optional:
        return True, "OPTIONAL STEP FAILED BUT PIPELINE CONTINUED\n" + output
    return ok, output


def _missing_critical() -> List[str]:
    missing = []
    for path in CRITICAL_OUTPUTS:
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            missing.append(path)
    return missing


def _run_weekly_steps(summary_lines: List[str], error_lines: List[str]) -> None:
    for script, optional, job_name in WEEKLY_STEPS:
        if not should_run_weekly_job(job_name):
            summary_lines.append(f"{script}: SKIP weekly policy not due")
            continue

        print(f"Running weekly job {script} ...")
        ok, output = _run_step(script, optional)
        status = "OK" if ok else "FAIL"
        summary_lines.append(f"{script}: {status} (weekly optional)")
        if output:
            summary_lines.append(output[-4000:])
        if ok:
            mark_weekly_job_success(job_name)
        elif not optional:
            error_lines.append(f"Weekly job {script} failed\n{output}")
            break


def main() -> int:
    started = datetime.now()
    summary_lines = [f"Daily pipeline started: {started:%Y-%m-%d %H:%M:%S}"]
    error_lines: List[str] = []

    print("\nDAILY PIPELINE - STAGED NEWS OPTIMIZED")
    print("=" * 80)

    _run_weekly_steps(summary_lines, error_lines)

    for label, script, optional, extra_env in DAILY_STEPS:
        if script == "telegram_notify.py":
            early_missing = _missing_critical()
            if early_missing:
                msg = "Skipping telegram_notify.py because critical outputs are missing: " + ", ".join(early_missing)
                print(msg)
                summary_lines.append(msg)
                error_lines.append(msg)
                break

        print(f"Running {label}: {script} ...")
        ok, output = _run_step(script, optional, extra_env=extra_env)
        status = "OK" if ok else "FAIL"
        summary_lines.append(f"{label} [{script}]: {status}{' (optional)' if optional else ''}")
        if output:
            summary_lines.append(output[-4000:])
        if not ok:
            error_lines.append(f"{label} [{script}] failed\n{output}")
            print(f"  FAIL: {script}")
            break
        print(f"  {status}")

    missing = _missing_critical()
    if missing:
        msg = "Missing critical outputs: " + ", ".join(missing)
        summary_lines.append(msg)
        error_lines.append(msg)

    for path in PRE_TELEGRAM_OUTPUTS:
        if os.path.exists(path):
            summary_lines.append(f"Generated: {path}")

    if os.path.exists(AI_VALIDATION_REPORT_FILE):
        summary_lines.append(f"AI validation: {AI_VALIDATION_REPORT_FILE}")

    finished = datetime.now()
    summary_lines.append(f"Daily pipeline finished: {finished:%Y-%m-%d %H:%M:%S}")
    summary_lines.append(f"Elapsed seconds: {(finished - started).total_seconds():.1f}")

    with open(RUN_SUMMARY_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines) + "\n")
    with open(ERROR_LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n\n".join(error_lines) if error_lines else "No critical errors.\n")

    print(f"Saved: {RUN_SUMMARY_FILE}, {ERROR_LOG_FILE}")
    return 1 if error_lines else 0


if __name__ == "__main__":
    raise SystemExit(main())
