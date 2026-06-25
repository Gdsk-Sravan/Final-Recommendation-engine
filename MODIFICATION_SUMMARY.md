# Decision-Quality Upgrade Summary

This version upgrades the engine from a scanner-style report into a more selective, portfolio-aware daily trading brief.

## Main behavior changes

- Default universe mode is now `NSE_ALL`, with support for `NIFTY_500` and `CUSTOM_LIST`.
- The first stage builds a raw NSE equity universe, then filters by data quality, tradability, and technical eligibility before scoring.
- The engine no longer forces daily picks. If no setup passes, the BUY section says `None` and shows the best WATCHLIST names when valid near-misses exist.
- Candidates are now separated into four buckets: `BUY`, `WATCHLIST`, `HOLD / MANAGE`, and `EXIT / SELL`.
- Ranking is based on `TRADE_QUALITY_SCORE`, not only confidence.
- Final confidence is component-based and includes trend, momentum, volume, regime alignment, sector strength, relative strength, historical edge, liquidity/tradability, news risk, correlation penalty, portfolio fit, and reward/risk.
- Regime-specific acceptance rules now cover `STRONG_BULL`, `BULL`, `SIDEWAYS`, `WEAK_SIDEWAYS`, `BEAR`, `STRONG_BEAR`, `HIGH_VOLATILITY`, and `TRANSITION`.
- Portfolio fit, available capacity, same-sector concentration, and correlation with active positions are now explicit decision factors.
- Rejected high-rank names are logged with specific reasons, category, failed gates, watchlist eligibility, and next condition needed.
- Holdings are managed with explicit lifecycle actions: `HOLD`, `HOLD_CAUTION`, `REDUCE`, `BOOK_PROFIT`, `SELL`, `STOP_LOSS_EXIT`, `TRAILING_STOP_EXIT`, `TIME_EXIT`, `NEWS_RISK_EXIT`, `SECTOR_WEAKNESS_EXIT`, and `MARKET_REGIME_EXIT`.
- Severe event/news risk is non-negotiable: BUY is blocked and active positions are downgraded or exited depending on severity.
- Optional AI second pass has been added using `GROK_API_KEY`, with fallback support for `GROQ_API_KEY`. AI cannot create trades, invent market data, change stops/targets, or override hard deterministic rules.

## New or materially changed files

- `config.py`
- `universe_builder.py`
- `data_quality.py`
- `universe_filter.py`
- `volatility_filter.py`
- `cache_manager.py`
- `market_regime.py`
- `sector_rotation.py`
- `entry_quality.py`
- `confidence_engine.py`
- `fusion_scanner_v7.py`
- `elite_backtest_v3.py`
- `news_engine_v2.py`
- `ai_news_engine.py`
- `recommendation_engine_v6.py`
- `position_sizer.py`
- `portfolio_monitor.py`
- `correlation_engine.py`
- `ai_service.py`
- `ai_second_pass.py`
- `telegram_notify.py`
- `daily_pipeline.py`
- `validation_checks.py`
- `.github/workflows/stock-reviewer.yml`
- `tests/test_lifecycle_rules.py`

## Key output files

- `nse_all_symbols.csv`
- `rejected_universe.csv`
- `tradable_universe.csv`
- `data_quality_report.csv`
- `qualified_stocks.csv`
- `market_regime.txt`
- `regime_settings_used.json`
- `sector_scores.csv`
- `sector_rotation_summary.txt`
- `relative_strength_scores.csv`
- `entry_quality_scores.csv`
- `elite_scores_v3.csv`
- `setup_performance.csv`
- `regime_performance.csv`
- `news_scores.csv`
- `ai_news_scores.csv`
- `confidence_scores.csv`
- `recommendations.csv`
- `watchlist.csv`
- `rejected_candidates.csv`
- `portfolio_state.csv`
- `portfolio_status.csv`
- `portfolio_exposure_summary.csv`
- `position_sizes.csv`
- `correlation_report.csv`
- `ai_input_snapshot.json`
- `ai_output_snapshot.json`
- `ai_validation_report.json`
- `run_summary.txt`
- `telegram_report.txt`

## How to run

```bash
python daily_pipeline.py
```

Then run validation:

```bash
python validation_checks.py
```

## GitHub secrets / variables

Recommended secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GROK_API_KEY`
- optional legacy fallback: `GROQ_API_KEY`

Recommended variable:

- `TOTAL_CAPITAL`

## Important assumptions

- `NSE_ALL` uses NSE's equity list when available, then falls back to local symbols/cache/static sector map if the NSE list cannot be fetched.
- Yahoo Finance cache remains the OHLCV source, so symbols must be convertible to Yahoo-style `.NS` tickers.
- If a metric is unavailable, the engine marks it missing, penalizes the candidate, or rejects it; it does not fabricate values.
- The optional AI layer is an enrichment layer only. Deterministic hard gates and portfolio rules always win.
- Full NSE universe refresh can take longer than Nifty 500 because it may include thousands of symbols.

## Verification completed here

- Python compile check passed for the full repository with `python3 -m compileall .`.
- The full live pipeline was not executed here because it requires external market data refresh, optional AI/API access, and Telegram secrets in your environment.
