# Swing Trading Intelligence Platform — Complete Flow Explanation with Example

## 1) Big-picture flow

The engine works like a **multi-layer filter + scoring + risk-control pipeline**.

It does **not** use one score or one signal.
Instead, it combines:

- price trend quality
- historical edge quality
- market regime
- news risk
- AI event severity
- entry timing
- relative strength
- sector leadership
- portfolio risk discipline

---

## 2) Full daily flow

### Step 1 — Cache market data
File:
- `cache_manager.py`

Purpose:
- downloads and updates OHLCV data from Yahoo Finance
- saves local cache files for all stocks and indexes

Output:
- `cache/*.json`

---

### Step 2 — Filter the tradable universe
Files:
- `universe_filter.py`
- `volatility_filter.py`

Purpose:
- removes weak/unqualified names
- focuses only on stocks already showing acceptable structure

Outputs:
- `qualified_stocks.txt`
- `low_volatility_stocks.txt`

---

### Step 3 — Historical intelligence layer
File:
- `elite_backtest_v3.py`

Purpose:
- simulates historical swing trades stock-by-stock
- measures whether the stock has historically produced good swing-trading outcomes

Main metrics produced:
- `ELITE_SCORE`
- `WIN_RATE`
- `EXPECTANCY`
- `PROFIT_FACTOR`
- `AVG_WIN`
- `AVG_LOSS`
- `RISK_REWARD`
- `MAX_DRAWDOWN`
- `AVG_DRAWDOWN`
- `MAX_CONSEC_WINS`
- `MAX_CONSEC_LOSSES`

Outputs:
- `elite_scores_v3.txt`
- `elite_stocks_v3.txt`

---

### Step 4 — News collection and scoring
Files:
- `news_fetcher_v2.py`
- `news_engine_v2.py`
- `ai_news_engine.py`

Purpose:
- collect recent headlines
- apply time decay
- classify event type
- estimate severity
- detect black swan risk

Examples of risks detected:
- SEBI action
- USFDA issue
- fraud allegation
- promoter risk
- debt stress
- management exits

Outputs:
- `news_headlines.csv`
- `news_scores.txt`
- `ai_news_scores.txt`

---

### Step 5 — Market regime detection
File:
- `market_regime.py`

Purpose:
- classify the entire market as:
  - `BULL`
  - `BEAR`
  - `SIDEWAYS`

Uses:
- NIFTY trend
- EMA structure
- breadth
- momentum
- volatility

Output:
- `market_regime.txt`

---

### Step 6 — Relative strength layer
File:
- `relative_strength.py`

Purpose:
- checks whether a stock is outperforming or underperforming NIFTY
- also tracks RS momentum improvement or deterioration

Output:
- `relative_strength_scores.txt`

---

### Step 7 — Sector rotation layer
File:
- `sector_rotation.py`

Purpose:
- measures which sectors are leading and which are lagging
- boosts stocks inside strong sectors
- penalises stocks inside weak sectors

Output:
- `sector_scores.txt`

---

### Step 8 — Entry quality layer
File:
- `entry_quality.py`

Purpose:
- checks whether this is a good entry point now

Uses:
- EMA alignment
- breakout quality
- volume quality
- support/risk-reward profile
- momentum quality

Output:
- entry score used inside fusion/confidence layer

---

### Step 9 — Fusion + confidence decision layer
File:
- `fusion_scanner_v7.py`

Purpose:
- central engine that combines all factor layers into final stock-level ranking

Combines:
- technical score
- elite score
- entry score
- news score
- relative strength
- sector score
- regime score
- AI severity penalty
- black swan cap

Outputs:
- `fusion_scores_v7.txt`
- `confidence_scores.txt`

Important:
- `confidence_scores.txt` is now the main intelligence output
- confidence is the primary ranking metric

---

### Step 10 — Recommendation selection
File:
- `recommendation_engine_v6.py`

Purpose:
- removes black swan names
- applies regime confidence gate
- avoids too many names from one sector
- selects top recommendations
- writes fresh portfolio file

Output:
- `portfolio.txt`

Portfolio file now stores:
- symbol
- buy price
- confidence
- sector
- position size %
- entry date

---

### Step 11 — Position sizing
File:
- `position_sizer.py`

Purpose:
- decides how much capital each stock should receive
- not every stock gets equal allocation

Uses:
- confidence
- expectancy
- profit factor
- drawdown profile
- sector concentration cap

Output:
- `position_sizes.txt`

---

### Step 12 — Exit engine / portfolio monitor
File:
- `portfolio_monitor.py`

Purpose:
- tracks current portfolio and produces action labels

Possible actions:
- `BUY` is implied by recommendation layer
- `HOLD`
- `REDUCE`
- `BOOK_PROFIT`
- `SELL`

Uses:
- stop loss
- EMA20 breakdown
- trailing stop
- volatility stop
- time-based exit
- portfolio risk summary

Output:
- `portfolio_status.txt`

---

### Step 13 — Telegram report
File:
- `telegram_notify.py`

Purpose:
- sends final human-readable report to Telegram

Includes:
- regime summary
- top picks
- confidence
- expectancy
- PF
- drawdown
- news severity
- black swan alerts
- suggested allocation
- portfolio actions

---

## 3) Worked example — how one stock flows through the engine

Example stock:
- `KIRLOSENG.NS`

### Stage A — universe filters
Suppose:
- price above EMA20 and EMA50
- near 52-week high
- decent liquidity
- acceptable volatility

It survives and enters `low_volatility_stocks.txt`.

---

### Stage B — historical backtest
Suppose historical backtest metrics become:

- Win Rate = 58%
- Expectancy = 2.4%
- Profit Factor = 1.95
- Avg Winner = 8.1%
- Avg Loser = -4.3%
- Max Drawdown = 12.8%

Interpretation:
- win rate is good but not extraordinary
- expectancy is strong
- PF is strong
- drawdown is acceptable

This gives it a strong `ELITE_SCORE`.

---

### Stage C — news layer
Suppose recent headlines say:
- company wins new industrial contract
- capacity expansion announced
- no major legal/regulatory issues

Keyword/AI outputs may become:
- sentiment = Positive
- severity = 38
- event_type = `OrderWin`
- swing_impact = `Medium`
- black_swan = `False`

Interpretation:
- supportive catalyst
- not catastrophic risk

---

### Stage D — market regime
Suppose market regime is:
- `BULL`

Interpretation:
- trend-following names are allowed to receive higher confidence
- strong cyclical / capital goods names may receive boost

---

### Stage E — relative strength
Suppose:
- stock return over lookback = +24%
- NIFTY return = +8%

Then RS is strong.

Interpretation:
- stock is outperforming the benchmark
- this is a favorable sign for swing ranking

---

### Stage F — sector rotation
Suppose `Capital Goods` sector is currently leading.

Interpretation:
- stock receives additional positive sector support

---

### Stage G — entry quality
Suppose current chart has:
- good EMA stacking
- strong relative volume
- near breakout zone
- good support distance
- healthy RSI

Entry Score may become:
- `78`

Interpretation:
- this is not only a good stock, but a good entry location

---

### Stage H — confidence engine
Now all layers combine.

Example inputs:
- Technical Score = 82
- Elite Score = 79
- Entry Score = 78
- News Score = 69
- RS Score = 76
- Sector Score = 72
- Regime = BULL
- AI Severity = 38
- Black Swan = False

Possible output:
- Confidence = `88`
- Grade = `A+`

Interpretation:
- high-conviction swing candidate
- historical edge exists
- market context supportive
- no serious news risk

---

### Stage I — recommendation engine
Then recommendation layer checks:
- not a black swan
- above confidence threshold
- sector concentration acceptable

If yes, it becomes a final portfolio pick.

Example final recommendation row:
- `KIRLOSENG.NS, 1532.20, 88.0, Capital Goods, 17.5, 2026-06-23`

---

### Stage J — position sizing
Now sizing layer may decide:
- base allocation from confidence = 16.5%
- historical quality bonus = +1.0%
- drawdown penalty = 0%
- final suggested allocation = `17.5%`

Interpretation:
- this name gets more capital than a lower-confidence name

---

### Stage K — portfolio monitoring later
After entry, suppose price rises 14%, then pulls back 6% from peak.

Exit engine may return:
- `REDUCE`

Reason:
- profitable trade
- trailing stop activated
- protect gains without full exit

If price later breaks below EMA20:
- `SELL`

---

## 4) Example of final report logic

A final report line for the same stock may look conceptually like this:

**KIRLOSENG.NS ranks #1 because:**
- strong trend structure
- positive historical expectancy
- strong sector rotation
- constructive catalyst flow
- no major risk headlines

**Confidence:** 88%

**Entry Score:** 78

**Expectancy:** 2.4%

**Profit Factor:** 1.95

**Max Drawdown:** 12.8%

**Sector:** Capital Goods

**Suggested Allocation:** 17.5%

---

## 5) Why this flow is much stronger than the old flow

Old style engines usually fail because they over-rely on one of these:
- win rate only
- technicals only
- news keywords only
- equal weighting only

This upgraded engine is stronger because it checks:

- is the stock technically strong?
- is the stock historically profitable for swing setups?
- is the market supportive?
- is the sector supportive?
- is the stock outperforming NIFTY?
- is news helping or hurting?
- is there hidden catastrophic risk?
- is this a good entry point right now?
- how much capital should be allocated?
- when should profits be reduced or exited?

---

## 6) Operational run order example

For a daily scheduled run:

1. refresh cache
2. filter universe
3. backtest history layer
4. fetch news
5. keyword news engine
6. AI news engine
7. detect regime
8. compute relative strength
9. compute sector rotation
10. run fusion/confidence engine
11. generate recommendations
12. generate position sizes
13. monitor portfolio
14. send Telegram report

---

## 7) Final takeaway

This engine works like a **decision stack**, not a single stock screener.

It is now designed to answer four institutional-style questions every day:

1. **Which stocks are statistically attractive?**
2. **Which ones are safe enough to consider right now?**
3. **How much capital should each get?**
4. **What action should be taken on current holdings?**

That is the core logic of the upgraded platform.
