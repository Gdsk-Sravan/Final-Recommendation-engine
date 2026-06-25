# Swing Trading Intelligence Platform — Project Review, Changes, Pending Work, and GitHub Checklist

## 1) What this project is now

This project has been upgraded from a basic scanner/ranker into a much more complete **quantitative swing-trading decision engine**.

It now contains dedicated layers for:

- historical expectancy-based scoring
- market regime detection
- news decay and event classification
- AI news risk analysis with black swan detection
- confidence scoring
- entry quality scoring
- relative strength analysis
- sector rotation analysis
- dynamic position sizing
- upgraded recommendation selection
- upgraded exit monitoring
- upgraded Telegram reporting

---

## 2) Main architecture now

Current primary pipeline:

1. `cache_manager.py`
2. `universe_filter.py`
3. `volatility_filter.py`
4. `elite_backtest_v3.py`
5. `news_fetcher_v2.py`
6. `news_engine_v2.py`
7. `ai_news_engine.py`
8. `market_regime.py`
9. `relative_strength.py`
10. `sector_rotation.py`
11. `fusion_scanner_v7.py`
12. `recommendation_engine_v6.py`
13. `position_sizer.py`
14. `portfolio_monitor.py`
15. `telegram_notify.py`

---

## 3) Files added or materially upgraded

### Core upgraded files
- `config.py`
- `elite_backtest_v3.py`
- `news_fetcher_v2.py`
- `news_engine_v2.py`
- `fusion_scanner_v7.py`
- `recommendation_engine_v6.py`
- `portfolio_monitor.py`
- `position_sizer.py`
- `telegram_notify.py`

### New engine files
- `market_regime.py`
- `ai_news_engine.py`
- `confidence_engine.py`
- `entry_quality.py`
- `relative_strength.py`
- `sector_rotation.py`

### Foundation/data improvements
- `data_provider.py`

---

## 4) What changed in each major engine

### A. Historical intelligence upgrade
Implemented in `elite_backtest_v3.py`.

Old state:
- mostly raw win-rate driven

New state:
- expectancy
- profit factor
- average winner
- average loser
- risk reward ratio
- maximum drawdown
- average drawdown
- recovery time proxy
- consecutive wins
- consecutive losses

### B. Regime detection
Implemented in `market_regime.py`.

Now detects:
- BULL
- BEAR
- SIDEWAYS

Using:
- NIFTY trend
- EMA structure
- breadth
- momentum
- volatility

### C. News intelligence
Implemented in `news_fetcher_v2.py`, `news_engine_v2.py`, `ai_news_engine.py`.

Now supports:
- timestamp capture
- news decay
- event classification
- severity scoring
- AI sentiment / event type / swing impact
- black swan flagging

### D. Confidence engine
Implemented in `confidence_engine.py` and used by `fusion_scanner_v7.py`.

Confidence now blends:
- technical score
- elite historical score
- entry score
- news score
- relative strength
- sector score
- regime score
- AI severity and black swan penalties

### E. Entry quality engine
Implemented in `entry_quality.py`.

Now evaluates:
- EMA alignment
- breakout quality
- volume quality
- support/risk-reward profile
- momentum quality

### F. Relative strength engine
Implemented in `relative_strength.py`.

Now measures:
- performance vs NIFTY
- RS momentum acceleration / deceleration
- RS rank score

### G. Sector rotation engine
Implemented in `sector_rotation.py`.

Now measures:
- sector momentum
- sector leadership / lagging classification
- sector-based confidence adjustment

### H. Portfolio intelligence / exit logic
Implemented in `portfolio_monitor.py`.

Now supports:
- HOLD
- REDUCE
- BOOK_PROFIT
- SELL

Using:
- stop loss
- EMA trend breakdown
- trailing stop logic
- volatility stop
- time-based exit
- sector exposure summary
- portfolio risk score

### I. Position sizing
Implemented in `position_sizer.py`.

Now uses:
- confidence
- expectancy
- profit factor
- drawdown profile
- sector concentration caps

### J. Telegram reporting
Implemented in `telegram_notify.py`.

Now includes:
- market regime context
- confidence score
- entry score
- expectancy
- profit factor
- drawdown
- AI severity
- risk flag
- sector strength
- relative strength
- suggested allocation
- portfolio action summary
- black swan alert section

---

## 5) Important design decisions

### Deterministic trade decisions
Buy/sell logic is still deterministic.
AI is used only where it adds value:
- news interpretation
- event classification
- severity estimation
- black swan risk detection

### Confidence replaces raw scanner score
This is the biggest improvement.
The system no longer treats raw win-rate or raw technical ranking as sufficient.

### Black swan hard gating
Any black swan risk can cap confidence or exclude the stock.
This is important for Indian mid/small-cap swing systems.

### File-based modular architecture retained
The existing architecture was reused instead of fully re-platforming the codebase.
This keeps daily runtime lightweight and practical.

---

## 6) Current quality rating

## Investment-engine quality rating: **7.8 / 10**

### Breakdown
- **Technical architecture:** 8.2/10
- **Research / factor quality:** 8.0/10
- **Risk controls:** 7.6/10
- **Production readiness:** 7.2/10
- **Autonomous deploy-with-real-money readiness:** 6.3/10

### Interpretation
This is now a **strong decision-support engine**, but it is **not yet a fully validated institutional live-trading system**.

### Why not higher yet
Because these still need completion or verification:
- walk-forward validation across regimes
- transaction cost / slippage modelling in backtests
- correlation analysis at portfolio level
- broader sector map coverage
- live pipeline orchestration / scheduling
- test coverage
- live operational monitoring and alerting

### Practical view
- good enough for **paper trading + supervised capital deployment**
- not yet ideal for **fully blind large-capital autonomous execution**

---

## 7) What is still pending

## High-priority pending

### 1. End-to-end orchestration script
There is still no single master runner that executes the full daily pipeline in order.

Recommended:
- add a `daily_pipeline.py` or update `master_scanner.py` to run the new order automatically

### 2. Existing portfolio files need new format going forward
`recommendation_engine_v6.py` now writes:
- `SYMBOL,BUY_PRICE,CONFIDENCE,SECTOR,POSITION_PCT,ENTRY_DATE`

If you already have an older `portfolio.txt`, regenerate it once using the new recommendation engine.

### 3. GitHub Actions / scheduler integration
The logic is upgraded, but the repository still needs workflow updates so the new files run in the correct sequence.

### 4. Sector map expansion
`config.py` currently includes a practical static `SECTOR_MAP`, but it should be expanded to cover your real tradable universe more completely.

### 5. Transaction cost realism in backtests
Current historical engine is much better now, but still does not fully model:
- slippage
- brokerage
- taxes
- liquidity impact

### 6. Portfolio correlation analysis
Current portfolio logic includes sector concentration and portfolio risk score, but not a full rolling return-correlation matrix yet.

### 7. Unit/integration tests
No test suite was added yet.
This is one of the biggest remaining production gaps.

---

## 8) What you need to do in GitHub after this

## A. Add repository secrets
Go to:
- GitHub repository
- Settings
- Secrets and variables
- Actions

Add these secrets:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GROQ_API_KEY`

Optional variable if you want dynamic capital from GitHub environment:
- `TOTAL_CAPITAL`

---

## B. Update your workflow order
If you use GitHub Actions, make sure the daily workflow runs in this order:

1. `cache_manager.py`
2. `universe_filter.py`
3. `volatility_filter.py`
4. `elite_backtest_v3.py`
5. `news_fetcher_v2.py`
6. `news_engine_v2.py`
7. `ai_news_engine.py`
8. `market_regime.py`
9. `relative_strength.py`
10. `sector_rotation.py`
11. `fusion_scanner_v7.py`
12. `recommendation_engine_v6.py`
13. `position_sizer.py`
14. `portfolio_monitor.py`
15. `telegram_notify.py`

---

## C. Commit the new files
At minimum, commit these:

- `config.py`
- `relative_strength.py`
- `sector_rotation.py`
- `fusion_scanner_v7.py`
- `recommendation_engine_v6.py`
- `portfolio_monitor.py`
- `position_sizer.py`
- `telegram_notify.py`
- `market_regime.py`
- `ai_news_engine.py`
- `confidence_engine.py`
- `entry_quality.py`
- `PROJECT_ENGINE_REVIEW_AND_NEXT_STEPS.md`
- `SYSTEM_FLOW_EXAMPLE.md`

---

## D. Regenerate output artifacts locally once
Run the full pipeline once so GitHub has fresh outputs and you can verify:
- `market_regime.txt`
- `confidence_scores.txt`
- `position_sizes.txt`
- `portfolio_status.txt`

---

## E. Validate Telegram output before cron automation
Before enabling automatic runs:
- test one full daily cycle manually
- confirm Telegram formatting is correct
- confirm no secrets are hard-coded
- confirm black swan alerts behave as expected

---

## 9) Recommended next implementation roadmap

### Phase P1
- create unified `daily_pipeline.py`
- add workflow / scheduler update
- expand `SECTOR_MAP`
- run full dry test

### Phase P2
- add transaction cost and slippage model to `elite_backtest_v3.py`
- add rolling correlation matrix in portfolio layer
- add correlation-based allocation cap

### Phase P3
- add unit tests and regression checks
- add health checks for missing files / stale cache / API failure
- add walk-forward evaluation report

---

## 10) Current operational notes

### Important
- AI news is optional and gracefully falls back if `GROQ_API_KEY` is missing.
- Portfolio time-based exits now depend on `ENTRY_DATE`; old legacy holdings should be regenerated once.
- `portfolio.txt` should be produced by `recommendation_engine_v6.py`, not maintained manually.

---

## 11) Final summary

This engine is now materially stronger than the original version.

### Biggest upgrades
- win-rate dependence reduced
- expectancy / profit factor prioritised
- regime-aware ranking
- AI black swan risk layer
- confidence-driven selection
- dynamic sizing
- much better reporting

### Bottom line
This is now a **serious swing-trading research and decision engine**.
It still needs **validation, orchestration, and testing** before it should be trusted as a fully autonomous live capital allocator.
