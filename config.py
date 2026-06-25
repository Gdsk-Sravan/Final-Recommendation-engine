"""
config.py — Central configuration for the Swing Trading Intelligence Platform.
All tunable parameters live here.  No other file should hard-code business
thresholds — import from here instead.
"""

import os

# ═══════════════════════════════════════════════════════════════════
# CAPITAL  — edit this to match your current deployed capital
# ═══════════════════════════════════════════════════════════════════
TOTAL_CAPITAL           = float(os.getenv("TOTAL_CAPITAL") or "200000")   # ₹2L default

# ═══════════════════════════════════════════════════════════════════
# UNIVERSE FILES
# ═══════════════════════════════════════════════════════════════════
STOCKS_FILE             = "stocks.txt"
QUALIFIED_FILE          = "qualified_stocks.txt"
LOW_VOL_FILE            = "low_volatility_stocks.txt"
PORTFOLIO_FILE          = "portfolio.txt"
PORTFOLIO_STATUS_FILE   = "portfolio_status.txt"
FUSION_INPUT_FILE       = "low_volatility_stocks.txt"   # change to QUALIFIED_FILE to widen funnel

# ═══════════════════════════════════════════════════════════════════
# OUTPUT FILES
# ═══════════════════════════════════════════════════════════════════
ELITE_SCORES_FILE       = "elite_scores_v3.txt"
ELITE_STOCKS_FILE       = "elite_stocks_v3.txt"
FUSION_SCORES_FILE      = "fusion_scores_v7.txt"
NEWS_HEADLINES_FILE     = "news_headlines.csv"
NEWS_SCORES_FILE        = "news_scores.txt"
AI_NEWS_SCORES_FILE     = "ai_news_scores.txt"
MARKET_REGIME_FILE      = "market_regime.txt"
CONFIDENCE_SCORES_FILE  = "confidence_scores.txt"
SECTOR_SCORES_FILE      = "sector_scores.txt"
YESTERDAY_TOP10_FILE    = "yesterday_top10.json"

# ═══════════════════════════════════════════════════════════════════
# BACKTEST PARAMETERS  (elite_backtest_v3.py)
# ═══════════════════════════════════════════════════════════════════
BACKTEST_TARGET_PCT     = 10.0   # % profit target per trade
BACKTEST_STOP_PCT       = 6.0    # % stop-loss per trade (positive number)
BACKTEST_MAX_HOLD       = 20     # max holding period in bars
BACKTEST_MIN_BARS       = 120    # minimum price history required
BACKTEST_WARMUP         = 60     # bars to skip at start of history
BACKTEST_MIN_TRADES     = 10     # discard stocks with fewer simulated trades

# ═══════════════════════════════════════════════════════════════════
# CONFIDENCE ENGINE WEIGHTS  (must sum to 1.0)
# ═══════════════════════════════════════════════════════════════════
CONF_W_TECHNICAL        = 0.25   # EMA alignment, trend, volume
CONF_W_ELITE            = 0.20   # expectancy-based historical score
CONF_W_ENTRY            = 0.15   # entry quality (breakout, RSI, support proximity)
CONF_W_NEWS             = 0.12   # news sentiment (keyword + AI)
CONF_W_RS               = 0.10   # relative strength vs NIFTY
CONF_W_SECTOR           = 0.08   # sector rotation strength
CONF_W_REGIME           = 0.10   # market regime score

# ═══════════════════════════════════════════════════════════════════
# FUSION SCANNER WEIGHTS  (fusion_scanner_v7.py)
# ═══════════════════════════════════════════════════════════════════
FUSION_W_TREND          = 0.30
FUSION_W_RS             = 0.20
FUSION_W_HIGH           = 0.10
FUSION_W_VOLUME         = 0.10
FUSION_W_HISTORY        = 0.20
FUSION_W_NEWS           = 0.10

# ═══════════════════════════════════════════════════════════════════
# MARKET REGIME  (market_regime.py)
# ═══════════════════════════════════════════════════════════════════
REGIME_BULL_THRESHOLD   = 45
REGIME_BEAR_THRESHOLD   = -30

REGIME_MULTIPLIER = {
    "BULL":     1.15,
    "SIDEWAYS": 0.90,
    "BEAR":     0.70,
}

REGIME_SCORE = {
    "BULL":     85,
    "SIDEWAYS": 50,
    "BEAR":     20,
}

REGIME_SECTOR_PREFERENCES = {
    "BULL": {
        "boost":   ["Capital Goods", "Defence", "Realty", "Auto", "Metals", "IT"],
        "penalize": ["FMCG", "Pharma", "Utilities"],
    },
    "BEAR": {
        "boost":   ["FMCG", "Pharma", "Utilities", "IT"],
        "penalize": ["Realty", "Metals", "Capital Goods", "Auto"],
    },
    "SIDEWAYS": {
        "boost":   ["IT", "Pharma", "FMCG"],
        "penalize": ["Realty", "Metals"],
    },
}

# ═══════════════════════════════════════════════════════════════════
# NEWS DECAY  (news_engine_v2.py)
# ═══════════════════════════════════════════════════════════════════
NEWS_DECAY_TABLE = [
    (1,  1.00),   # 0–1 days old → full weight
    (3,  0.80),   # 2–3 days     → 80%
    (7,  0.60),   # 4–7 days     → 60%
    (14, 0.30),   # 8–14 days    → 30%
]
NEWS_DECAY_FLOOR = 0.10   # articles older than 14 days → minimal weight

# ═══════════════════════════════════════════════════════════════════
# PORTFOLIO MONITOR / EXIT ENGINE  (portfolio_monitor.py)
# ═══════════════════════════════════════════════════════════════════
BOOK_PROFIT_PCT         = 20.0   # PnL >= +20%        → BOOK_PROFIT
STOP_LOSS_PCT           = -8.0   # PnL <= -8%         → SELL (stop triggered)
TRAILING_STOP_PCT       = 5.0    # drawdown from peak → REDUCE then SELL
REDUCE_PROFIT_PCT       = 12.0   # PnL >= 12% + trail triggered → REDUCE
TIME_EXIT_BARS          = 25     # max bars before time-based exit
EMA_PERIOD_MONITOR      = 20     # EMA period for trend-breakdown signal

# ═══════════════════════════════════════════════════════════════════
# POSITION SIZING  (position_sizer.py)
# ═══════════════════════════════════════════════════════════════════
# Tiers: (confidence_min, confidence_max, alloc_pct_min, alloc_pct_max)
POSITION_TIERS = [
    (80, 100, 15, 20),
    (65,  79, 10, 14),
    (50,  64,  5,  9),
    (0,   49,  0,  0),   # below 50 → no position
]
MAX_POSITION_PCT        = 20.0
MAX_SECTOR_EXPOSURE_PCT = 40.0
MAX_CORRELATED_PICKS    = 3

# ═══════════════════════════════════════════════════════════════════
# RECOMMENDATION ENGINE  (recommendation_engine_v6.py)
# ═══════════════════════════════════════════════════════════════════
TOP_PICKS_COUNT         = 10
WATCHLIST_COUNT         = 5
HIGH_CONVICTION_MIN     = 70     # confidence score threshold
MIN_CONFIDENCE_TO_BUY   = 50
BEAR_MIN_CONFIDENCE     = 65     # stricter entry gate in BEAR regime
SIDEWAYS_MIN_CONFIDENCE = 55

# ═══════════════════════════════════════════════════════════════════
# RELATIVE STRENGTH  (relative_strength.py)
# ═══════════════════════════════════════════════════════════════════
NIFTY_SYMBOL            = "^NSEI"
RS_LOOKBACK_DAYS        = 63     # ~3 months
RS_SHORT_LOOKBACK       = 21     # ~1 month

# ═══════════════════════════════════════════════════════════════════
# SECTOR ROTATION  (sector_rotation.py)
# ═══════════════════════════════════════════════════════════════════
SECTOR_RS_LOOKBACK      = 63
SECTOR_BOOST_PTS        = 8.0
SECTOR_PENALTY_PTS      = 5.0

# Sector → representative stocks for momentum measurement
SECTOR_MAP = {
    "Defence":       ["HAL.NS", "BEL.NS", "COCHINSHIP.NS", "MIDHANI.NS",
                      "GRSE.NS", "BEML.NS", "MAZDOCK.NS"],
    "Pharma":        ["SUNPHARMA.NS", "DIVISLAB.NS", "CIPLA.NS", "DRREDDY.NS",
                      "LAURUSLABS.NS", "AUROPHARMA.NS", "ALKEM.NS", "IPCALAB.NS"],
    "Capital Goods": ["KIRLOSENG.NS", "ABB.NS", "SIEMENS.NS", "BHEL.NS",
                      "THERMAX.NS", "CUMMINSIND.NS", "GRINDWELL.NS", "KSB.NS"],
    "IT":            ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS",
                      "LTIM.NS", "TECHM.NS", "PERSISTENT.NS", "COFORGE.NS"],
    "Banking":       ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS",
                      "KOTAKBANK.NS", "INDUSINDBK.NS", "FEDERALBNK.NS"],
    "FMCG":          ["HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS",
                      "DABUR.NS", "MARICO.NS", "GODREJCP.NS"],
    "Auto":          ["MARUTI.NS", "EICHERMOT.NS", "BAJAJ-AUTO.NS", "TATAMOTORS.NS",
                      "M&M.NS", "HEROMOTOCO.NS", "BALKRISIND.NS"],
    "Realty":        ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PRESTIGE.NS",
                      "BRIGADE.NS"],
    "Metals":        ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS",
                      "SAIL.NS", "NMDC.NS"],
    "Finance":       ["ABSLAMC.NS", "HDFCAMC.NS", "NIPPONLIFE.NS",
                      "BAJFINANCE.NS", "CHOLAFIN.NS", "SBILIFE.NS"],
}

# ═══════════════════════════════════════════════════════════════════
# TELEGRAM REPORT  (telegram_notify.py)
# ═══════════════════════════════════════════════════════════════════
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID", "")
MESSAGE_CHAR_LIMIT      = 4000
DELAY_BETWEEN_MSGS      = 1.5

# ═══════════════════════════════════════════════════════════════════
# GROQ AI  (ai_news_engine.py)
# ═══════════════════════════════════════════════════════════════════
GROQ_API_KEY            = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL              = "llama-3.1-8b-instant"
GROQ_TIMEOUT            = 20
GROQ_MAX_RETRY          = 2
GROQ_RPM_DELAY          = 0.5

# ═══════════════════════════════════════════════════════════════════
# LEGACY ALIASES  (backward compatibility)
# ═══════════════════════════════════════════════════════════════════
MIN_PRICE               = 100
MIN_RSI                 = 45
MAX_RSI                 = 75
MIN_HISTORY_SCORE       = 40
TECH_WEIGHT             = CONF_W_TECHNICAL
HISTORY_WEIGHT          = CONF_W_ELITE
FUNDAMENTAL_WEIGHT      = 0.0
NEWS_WEIGHT             = CONF_W_NEWS
TOP_BUYS                = TOP_PICKS_COUNT
WATCHLIST_SIZE          = WATCHLIST_COUNT
RISK_PER_TRADE_PERCENT  = 1
MAX_POSITION_PERCENT    = MAX_POSITION_PCT
ATR_PERIOD              = 14
ATR_MULTIPLIER          = 2

# ===================================================================
# STRICT TRADE LIFECYCLE UPGRADE CONFIG
# ===================================================================
# These values are used by the stricter data-first recommendation flow.
# Keep them in config.py so engine files do not hard-code business rules.

PORTFOLIO_STATE_FILE = "portfolio_state.csv"
RECOMMENDATIONS_FILE = "recommendations.csv"
REJECTED_CANDIDATES_FILE = "rejected_candidates.csv"
ENTRY_QUALITY_SCORES_FILE = "entry_quality_scores.txt"
CORRELATION_REPORT_FILE = "correlation_report.txt"
DATA_QUALITY_REPORT_FILE = "data_quality_report.txt"
RUN_SUMMARY_FILE = "run_summary.txt"
ERROR_LOG_FILE = "error_log.txt"
TELEGRAM_REPORT_FILE = "telegram_report.txt"
TRADE_JOURNAL_FILE = "trade_journal.csv"

# Risk-first trade selection thresholds.
MIN_REWARD_RISK = float(os.getenv("MIN_REWARD_RISK", "1.8"))
MIN_ENTRY_SCORE = float(os.getenv("MIN_ENTRY_SCORE", "60"))
MIN_RS_SCORE = float(os.getenv("MIN_RS_SCORE", "58"))
MIN_TECH_SCORE = float(os.getenv("MIN_TECH_SCORE", "55"))
MIN_LIQUIDITY_AVG_VOLUME = float(os.getenv("MIN_LIQUIDITY_AVG_VOLUME", "100000"))
MAX_EXTENSION_FROM_EMA20_PCT = float(os.getenv("MAX_EXTENSION_FROM_EMA20_PCT", "12"))
MAX_NEWS_SEVERITY_TO_BUY = int(os.getenv("MAX_NEWS_SEVERITY_TO_BUY", "74"))
MAX_AI_SEVERITY_TO_HOLD = int(os.getenv("MAX_AI_SEVERITY_TO_HOLD", "84"))

# Risk sizing.
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
MAX_PORTFOLIO_HEAT = float(os.getenv("MAX_PORTFOLIO_HEAT", "6.0"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "8"))
TRAILING_STOP_ATR_MULTIPLIER = float(os.getenv("TRAILING_STOP_ATR_MULTIPLIER", "2.0"))
INITIAL_STOP_ATR_MULTIPLIER = float(os.getenv("INITIAL_STOP_ATR_MULTIPLIER", "1.5"))
TARGET1_R_MULTIPLE = float(os.getenv("TARGET1_R_MULTIPLE", "1.5"))
TARGET2_R_MULTIPLE = float(os.getenv("TARGET2_R_MULTIPLE", "2.8"))
TIME_EXIT_DAYS = int(os.getenv("TIME_EXIT_DAYS", "10"))
CORRELATION_LIMIT = float(os.getenv("CORRELATION_LIMIT", "0.78"))
MAX_SAME_SECTOR_ACTIVE = int(os.getenv("MAX_SAME_SECTOR_ACTIVE", "2"))

REGIME_SETTINGS = {
    "STRONG_BULL": {
        "fresh_buying_allowed": True,
        "max_new_buys": 5,
        "min_buy_confidence": 78,
        "max_total_exposure": 90.0,
        "max_position_size": 18.0,
        "score_multiplier": 1.12,
    },
    "BULL": {
        "fresh_buying_allowed": True,
        "max_new_buys": 3,
        "min_buy_confidence": 82,
        "max_total_exposure": 75.0,
        "max_position_size": 15.0,
        "score_multiplier": 1.05,
    },
    "SIDEWAYS": {
        "fresh_buying_allowed": True,
        "max_new_buys": 2,
        "min_buy_confidence": 88,
        "max_total_exposure": 50.0,
        "max_position_size": 10.0,
        "score_multiplier": 0.92,
    },
    "WEAK_SIDEWAYS": {
        "fresh_buying_allowed": True,
        "max_new_buys": 1,
        "min_buy_confidence": 92,
        "max_total_exposure": 35.0,
        "max_position_size": 7.0,
        "score_multiplier": 0.85,
    },
    "BEAR": {
        "fresh_buying_allowed": True,
        "max_new_buys": 1,
        "min_buy_confidence": 95,
        "max_total_exposure": 20.0,
        "max_position_size": 5.0,
        "score_multiplier": 0.72,
    },
    "STRONG_BEAR": {
        "fresh_buying_allowed": False,
        "max_new_buys": 0,
        "min_buy_confidence": 999,
        "max_total_exposure": 5.0,
        "max_position_size": 0.0,
        "score_multiplier": 0.50,
    },
}

MAX_BUYS_BY_REGIME = {k: v["max_new_buys"] for k, v in REGIME_SETTINGS.items()}
MIN_CONFIDENCE_BY_REGIME = {k: v["min_buy_confidence"] for k, v in REGIME_SETTINGS.items()}

# ===================================================================
# DECISION QUALITY UPGRADE V2 CONFIG
# ===================================================================
# Appended settings intentionally override earlier defaults while preserving
# backward compatibility for older modules.

# Universe discovery and staged filtering.
UNIVERSE_MODE = os.getenv("UNIVERSE_MODE", "NSE_ALL").strip().upper()
CUSTOM_UNIVERSE_FILE = os.getenv("CUSTOM_UNIVERSE_FILE", "custom_universe.txt")
NIFTY_500_FILE = os.getenv("NIFTY_500_FILE", STOCKS_FILE)
NSE_ALL_SYMBOLS_FILE = os.getenv("NSE_ALL_SYMBOLS_FILE", "nse_all_symbols.csv")
TRADABLE_UNIVERSE_FILE = os.getenv("TRADABLE_UNIVERSE_FILE", "tradable_universe.csv")
REJECTED_UNIVERSE_FILE = os.getenv("REJECTED_UNIVERSE_FILE", "rejected_universe.csv")
QUALIFIED_STOCKS_CSV_FILE = os.getenv("QUALIFIED_STOCKS_CSV_FILE", "qualified_stocks.csv")
DATA_QUALITY_REPORT_FILE = os.getenv("DATA_QUALITY_REPORT_FILE", "data_quality_report.csv")
CACHE_DIR = os.getenv("CACHE_DIR", "cache")
NSE_EQUITY_LIST_URL = os.getenv("NSE_EQUITY_LIST_URL", "https://archives.nseindia.com/content/equities/EQUITY_L.csv")
EXCLUDED_SYMBOL_KEYWORDS = ["ETF", "BEES", "NIFTY", "SENSEX", "GOLD", "SILVER", "LIQUID", "DEBT", "BOND", "SDL", "GSEC"]
EXCLUDED_NAME_KEYWORDS = ["ETF", "EXCHANGE TRADED", "GOLD", "SILVER", "BOND", "DEBENTURE", "PREFERENCE", "WARRANT"]
ALLOWED_NSE_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}
MIN_HISTORY_DAYS = int(os.getenv("MIN_HISTORY_DAYS", "220"))
MIN_INDICATOR_HISTORY_DAYS = int(os.getenv("MIN_INDICATOR_HISTORY_DAYS", "200"))
MAX_MISSING_CANDLE_RATIO = float(os.getenv("MAX_MISSING_CANDLE_RATIO", "0.08"))
MAX_ZERO_VOLUME_DAYS_60 = int(os.getenv("MAX_ZERO_VOLUME_DAYS_60", "8"))
MIN_AVG_VOLUME = float(os.getenv("MIN_AVG_VOLUME", str(MIN_LIQUIDITY_AVG_VOLUME)))
MIN_AVG_TRADED_VALUE = float(os.getenv("MIN_AVG_TRADED_VALUE", "5000000"))
MIN_STOCK_PRICE = float(os.getenv("MIN_STOCK_PRICE", str(MIN_PRICE)))
PENNY_STOCK_PRICE = float(os.getenv("PENNY_STOCK_PRICE", "20"))
MAX_SINGLE_DAY_MOVE_PCT = float(os.getenv("MAX_SINGLE_DAY_MOVE_PCT", "35"))
MAX_AVG_DAILY_MOVE_PCT = float(os.getenv("MAX_AVG_DAILY_MOVE_PCT", "4.5"))
LOW_VOL_MAX_AVG_DAILY_MOVE_PCT = float(os.getenv("LOW_VOL_MAX_AVG_DAILY_MOVE_PCT", "3.0"))
LOW_VOL_FILE = os.getenv("LOW_VOL_FILE", LOW_VOL_FILE)
QUALIFIED_FILE = os.getenv("QUALIFIED_FILE", QUALIFIED_FILE)
FUSION_INPUT_FILE = os.getenv("FUSION_INPUT_FILE", LOW_VOL_FILE)

# Output names requested by the upgraded brief.
SECTOR_SCORES_FILE = os.getenv("SECTOR_SCORES_FILE", "sector_scores.csv")
SECTOR_ROTATION_SUMMARY_FILE = os.getenv("SECTOR_ROTATION_SUMMARY_FILE", "sector_rotation_summary.txt")
ENTRY_QUALITY_SCORES_FILE = os.getenv("ENTRY_QUALITY_SCORES_FILE", "entry_quality_scores.csv")
RELATIVE_STRENGTH_SCORES_FILE = os.getenv("RELATIVE_STRENGTH_SCORES_FILE", "relative_strength_scores.csv")
WATCHLIST_FILE = os.getenv("WATCHLIST_FILE", "watchlist.csv")
POSITION_SIZES_FILE = os.getenv("POSITION_SIZES_FILE", "position_sizes.csv")
PORTFOLIO_EXPOSURE_SUMMARY_FILE = os.getenv("PORTFOLIO_EXPOSURE_SUMMARY_FILE", "portfolio_exposure_summary.csv")
REGIME_SETTINGS_FILE = os.getenv("REGIME_SETTINGS_FILE", "regime_settings_used.json")
AI_INPUT_SNAPSHOT_FILE = os.getenv("AI_INPUT_SNAPSHOT_FILE", "ai_input_snapshot.json")
AI_OUTPUT_SNAPSHOT_FILE = os.getenv("AI_OUTPUT_SNAPSHOT_FILE", "ai_output_snapshot.json")
AI_VALIDATION_REPORT_FILE = os.getenv("AI_VALIDATION_REPORT_FILE", "ai_validation_report.json")

# AI second pass. GROK is preferred, GROQ is supported for older deployments.
ENABLE_AI_SECOND_PASS = os.getenv("ENABLE_AI_SECOND_PASS", "true").strip().lower() in ("1", "true", "yes", "y")
GROK_API_KEY_ENV_NAME = os.getenv("GROK_API_KEY_ENV_NAME", "GROK_API_KEY")
GROK_API_KEY = os.getenv(GROK_API_KEY_ENV_NAME, "") or os.getenv("GROK_API_KEY", "") or os.getenv("GROQ_API_KEY", "")
GROK_API_URL = os.getenv("GROK_API_URL", "https://api.x.ai/v1/chat/completions")
GROK_MODEL = os.getenv("GROK_MODEL", "grok-2-latest")
AI_TIMEOUT_SECONDS = int(os.getenv("AI_TIMEOUT_SECONDS", "30"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))
AI_TOP_CANDIDATE_LIMIT = int(os.getenv("AI_TOP_CANDIDATE_LIMIT", "20"))
AI_CONFIDENCE_ADJUSTMENT_LIMIT = float(os.getenv("AI_CONFIDENCE_ADJUSTMENT_LIMIT", "5"))
LOG_AI_IO = os.getenv("LOG_AI_IO", "true").strip().lower() in ("1", "true", "yes", "y")

# Regime and score calibration.
INDIA_VIX_SYMBOL = os.getenv("INDIA_VIX_SYMBOL", "^INDIAVIX")
HIGH_VOLATILITY_ATR_PCT = float(os.getenv("HIGH_VOLATILITY_ATR_PCT", "2.4"))
HIGH_VOLATILITY_VIX_LEVEL = float(os.getenv("HIGH_VOLATILITY_VIX_LEVEL", "18"))
PANIC_GAP_DOWN_PCT = float(os.getenv("PANIC_GAP_DOWN_PCT", "-1.6"))
TRANSITION_SCORE_LOW = float(os.getenv("TRANSITION_SCORE_LOW", "46"))
TRANSITION_SCORE_HIGH = float(os.getenv("TRANSITION_SCORE_HIGH", "58"))
MIN_TRADE_QUALITY_SCORE = float(os.getenv("MIN_TRADE_QUALITY_SCORE", "72"))
MAX_CORRELATION_WITH_HOLDINGS = float(os.getenv("MAX_CORRELATION_WITH_HOLDINGS", str(CORRELATION_LIMIT)))
CORRELATION_LIMIT = MAX_CORRELATION_WITH_HOLDINGS
MAX_SAME_SECTOR_POSITIONS = int(os.getenv("MAX_SAME_SECTOR_POSITIONS", str(MAX_SAME_SECTOR_ACTIVE)))
NEWS_SEVERITY_EXIT_THRESHOLD = int(os.getenv("NEWS_SEVERITY_EXIT_THRESHOLD", str(MAX_AI_SEVERITY_TO_HOLD)))
NEWS_SEVERITY_WATCHLIST_THRESHOLD = int(os.getenv("NEWS_SEVERITY_WATCHLIST_THRESHOLD", "60"))

SCORE_WEIGHTS = {
    "trend_quality_score": float(os.getenv("W_TREND_QUALITY", "0.14")),
    "momentum_quality_score": float(os.getenv("W_MOMENTUM_QUALITY", "0.12")),
    "volume_participation_score": float(os.getenv("W_VOLUME_PARTICIPATION", "0.09")),
    "regime_alignment_score": float(os.getenv("W_REGIME_ALIGNMENT", "0.10")),
    "sector_strength_score": float(os.getenv("W_SECTOR_STRENGTH", "0.14")),
    "relative_strength_score": float(os.getenv("W_RELATIVE_STRENGTH", "0.13")),
    "historical_edge_score": float(os.getenv("W_HISTORICAL_EDGE", "0.10")),
    "liquidity_tradability_score": float(os.getenv("W_LIQUIDITY_TRADABILITY", "0.07")),
    "event_news_risk_score": float(os.getenv("W_EVENT_NEWS_RISK", "0.05")),
    "portfolio_fit_score": float(os.getenv("W_PORTFOLIO_FIT", "0.03")),
    "risk_reward_score": float(os.getenv("W_RISK_REWARD", "0.03")),
}
TRADE_QUALITY_WEIGHTS = {
    "entry_quality_score": float(os.getenv("TQ_ENTRY", "0.18")),
    "risk_reward_score": float(os.getenv("TQ_RR", "0.15")),
    "sector_strength_score": float(os.getenv("TQ_SECTOR", "0.14")),
    "relative_strength_score": float(os.getenv("TQ_RS", "0.13")),
    "trend_quality_score": float(os.getenv("TQ_TREND", "0.12")),
    "liquidity_tradability_score": float(os.getenv("TQ_LIQUIDITY", "0.09")),
    "event_news_risk_score": float(os.getenv("TQ_NEWS", "0.08")),
    "historical_edge_score": float(os.getenv("TQ_HISTORY", "0.07")),
    "portfolio_fit_score": float(os.getenv("TQ_PORTFOLIO", "0.04")),
}

REGIME_SETTINGS = {
    "STRONG_BULL": {
        "fresh_buying_allowed": True, "max_new_buys": 5, "min_buy_confidence": 78,
        "min_trade_quality_score": 74, "min_reward_risk": 1.7, "max_total_exposure": 90.0,
        "max_position_size": 18.0, "max_sector_exposure": 35.0, "score_multiplier": 1.10,
        "preferred_setup_types": ["BREAKOUT", "BASE_BREAKOUT", "MOMENTUM_CONTINUATION", "RANGE_BREAKOUT"],
        "restricted_setup_types": ["REVERSAL_AVOID"],
    },
    "BULL": {
        "fresh_buying_allowed": True, "max_new_buys": 3, "min_buy_confidence": 82,
        "min_trade_quality_score": 78, "min_reward_risk": 1.8, "max_total_exposure": 75.0,
        "max_position_size": 15.0, "max_sector_exposure": 30.0, "score_multiplier": 1.03,
        "preferred_setup_types": ["BREAKOUT", "BASE_BREAKOUT", "PULLBACK_TO_EMA20", "MOMENTUM_CONTINUATION"],
        "restricted_setup_types": ["REVERSAL_AVOID"],
    },
    "SIDEWAYS": {
        "fresh_buying_allowed": True, "max_new_buys": 2, "min_buy_confidence": 88,
        "min_trade_quality_score": 84, "min_reward_risk": 2.0, "max_total_exposure": 50.0,
        "max_position_size": 10.0, "max_sector_exposure": 22.0, "score_multiplier": 0.94,
        "preferred_setup_types": ["RANGE_BREAKOUT", "PULLBACK_TO_EMA20", "PULLBACK_TO_EMA50", "MEAN_REVERSION"],
        "restricted_setup_types": ["MOMENTUM_CONTINUATION", "REVERSAL_AVOID"],
    },
    "WEAK_SIDEWAYS": {
        "fresh_buying_allowed": True, "max_new_buys": 1, "min_buy_confidence": 92,
        "min_trade_quality_score": 88, "min_reward_risk": 2.2, "max_total_exposure": 35.0,
        "max_position_size": 7.0, "max_sector_exposure": 18.0, "score_multiplier": 0.86,
        "preferred_setup_types": ["RANGE_BREAKOUT", "PULLBACK_TO_EMA20"],
        "restricted_setup_types": ["MOMENTUM_CONTINUATION", "REVERSAL_AVOID"],
    },
    "BEAR": {
        "fresh_buying_allowed": True, "max_new_buys": 1, "min_buy_confidence": 95,
        "min_trade_quality_score": 92, "min_reward_risk": 2.4, "max_total_exposure": 20.0,
        "max_position_size": 5.0, "max_sector_exposure": 12.0, "score_multiplier": 0.72,
        "preferred_setup_types": ["PULLBACK_TO_EMA20", "RANGE_BREAKOUT"],
        "restricted_setup_types": ["BREAKOUT", "MOMENTUM_CONTINUATION", "REVERSAL_AVOID"],
    },
    "STRONG_BEAR": {
        "fresh_buying_allowed": False, "max_new_buys": 0, "min_buy_confidence": 999,
        "min_trade_quality_score": 999, "min_reward_risk": 999, "max_total_exposure": 5.0,
        "max_position_size": 0.0, "max_sector_exposure": 0.0, "score_multiplier": 0.45,
        "preferred_setup_types": [], "restricted_setup_types": ["BREAKOUT", "BASE_BREAKOUT", "RANGE_BREAKOUT", "MOMENTUM_CONTINUATION", "PULLBACK_TO_EMA20", "PULLBACK_TO_EMA50", "REVERSAL_AVOID"],
    },
    "HIGH_VOLATILITY": {
        "fresh_buying_allowed": True, "max_new_buys": 1, "min_buy_confidence": 94,
        "min_trade_quality_score": 90, "min_reward_risk": 2.3, "max_total_exposure": 25.0,
        "max_position_size": 5.0, "max_sector_exposure": 12.0, "score_multiplier": 0.78,
        "preferred_setup_types": ["PULLBACK_TO_EMA20", "RANGE_BREAKOUT"],
        "restricted_setup_types": ["MOMENTUM_CONTINUATION", "REVERSAL_AVOID"],
    },
    "TRANSITION": {
        "fresh_buying_allowed": True, "max_new_buys": 1, "min_buy_confidence": 91,
        "min_trade_quality_score": 88, "min_reward_risk": 2.1, "max_total_exposure": 35.0,
        "max_position_size": 7.0, "max_sector_exposure": 18.0, "score_multiplier": 0.84,
        "preferred_setup_types": ["RANGE_BREAKOUT", "PULLBACK_TO_EMA20"],
        "restricted_setup_types": ["REVERSAL_AVOID"],
    },
}
MAX_BUYS_BY_REGIME = {k: v["max_new_buys"] for k, v in REGIME_SETTINGS.items()}
MIN_CONFIDENCE_BY_REGIME = {k: v["min_buy_confidence"] for k, v in REGIME_SETTINGS.items()}
MIN_TRADE_QUALITY_BY_REGIME = {k: v["min_trade_quality_score"] for k, v in REGIME_SETTINGS.items()}
MIN_REWARD_RISK_BY_REGIME = {k: v["min_reward_risk"] for k, v in REGIME_SETTINGS.items()}
MAX_TOTAL_EXPOSURE_BY_REGIME = {k: v["max_total_exposure"] for k, v in REGIME_SETTINGS.items()}

# Keep legacy names aligned with the regime-aware settings above.
MIN_REWARD_RISK = float(os.getenv("MIN_REWARD_RISK", "1.8"))
MAX_SECTOR_EXPOSURE_PCT = float(os.getenv("MAX_SECTOR_EXPOSURE_PCT", "30"))
MAX_ACTIVE_POSITIONS = int(os.getenv("MAX_ACTIVE_POSITIONS", "8"))
WATCHLIST_COUNT = int(os.getenv("WATCHLIST_COUNT", "8"))
TOP_PICKS_COUNT = int(os.getenv("TOP_PICKS_COUNT", "5"))
# CSV primary outputs for the upgraded engine, with legacy text files still written by modules when useful.
ELITE_SCORES_FILE = os.getenv("ELITE_SCORES_FILE", "elite_scores_v3.csv")
ELITE_STOCKS_FILE = os.getenv("ELITE_STOCKS_FILE", "elite_stocks_v3.txt")
FUSION_SCORES_FILE = os.getenv("FUSION_SCORES_FILE", "fusion_scores_v7.txt")
CONFIDENCE_SCORES_FILE = os.getenv("CONFIDENCE_SCORES_FILE", "confidence_scores.csv")
NEWS_SCORES_FILE = os.getenv("NEWS_SCORES_FILE", "news_scores.csv")
AI_NEWS_SCORES_FILE = os.getenv("AI_NEWS_SCORES_FILE", "ai_news_scores.csv")
# Backward compatibility: old ai_news_engine uses GROQ_* names.
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "") or GROK_API_KEY
GROQ_MODEL = os.getenv("GROQ_MODEL", GROQ_MODEL if 'GROQ_MODEL' in globals() else "llama-3.1-8b-instant")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", str(GROQ_TIMEOUT if 'GROQ_TIMEOUT' in globals() else 20)))
GROQ_MAX_RETRY = int(os.getenv("GROQ_MAX_RETRY", str(GROQ_MAX_RETRY if 'GROQ_MAX_RETRY' in globals() else 2)))

# Final output alignment for the decision-quality brief.
PORTFOLIO_STATUS_FILE = os.getenv("PORTFOLIO_STATUS_FILE", "portfolio_status.csv")

# ===================================================================
# CACHE / REFRESH POLICY CONFIG
# ===================================================================
# These settings implement a practical refresh plan:
# Daily: indices, active holdings, previously tradable universe, high-quality candidates, news.
# Weekly: full NSE symbol list, full NSE_ALL OHLCV rebuild, optional sector/fundamental refresh.

def _env_bool(name: str, default: str = "false") -> bool:
    return str(os.getenv(name, default)).strip().lower() in ("1", "true", "yes", "y", "on")

CACHE_META_FILE = os.getenv("CACHE_META_FILE", os.path.join(CACHE_DIR, "cache_manifest.json"))
UNIVERSE_META_FILE = os.getenv("UNIVERSE_META_FILE", "universe_cache_meta.json")
WEEKLY_JOB_META_FILE = os.getenv("WEEKLY_JOB_META_FILE", "weekly_job_meta.json")
CACHE_REFRESH_REPORT_FILE = os.getenv("CACHE_REFRESH_REPORT_FILE", "cache_refresh_report.csv")
CACHE_REFRESH_SUMMARY_FILE = os.getenv("CACHE_REFRESH_SUMMARY_FILE", "cache_refresh_summary.txt")

# 0=Monday, 1=Tuesday, ..., 6=Sunday. Monday is best for a weekly full refresh
# because the market has just reopened after the weekend.
FULL_CACHE_REFRESH_WEEKDAY = int(os.getenv("FULL_CACHE_REFRESH_WEEKDAY", "0"))
UNIVERSE_REFRESH_DAYS = int(os.getenv("UNIVERSE_REFRESH_DAYS", "7"))
NIFTY500_REFRESH_DAYS = int(os.getenv("NIFTY500_REFRESH_DAYS", "7"))
FULL_CACHE_REFRESH_DAYS = int(os.getenv("FULL_CACHE_REFRESH_DAYS", "7"))
WEEKLY_JOB_REFRESH_DAYS = int(os.getenv("WEEKLY_JOB_REFRESH_DAYS", "7"))

# A manual run on the same day should not redownload the same symbols repeatedly.
PRICE_CACHE_MAX_AGE_HOURS = float(os.getenv("PRICE_CACHE_MAX_AGE_HOURS", "18"))
INDEX_CACHE_MAX_AGE_HOURS = float(os.getenv("INDEX_CACHE_MAX_AGE_HOURS", "4"))
ACTIVE_HOLDING_CACHE_MAX_AGE_HOURS = float(os.getenv("ACTIVE_HOLDING_CACHE_MAX_AGE_HOURS", "8"))
CANDIDATE_CACHE_MAX_AGE_HOURS = float(os.getenv("CANDIDATE_CACHE_MAX_AGE_HOURS", str(PRICE_CACHE_MAX_AGE_HOURS)))

CACHE_PRICE_RANGE = os.getenv("CACHE_PRICE_RANGE", "2y")
CACHE_PRICE_INTERVAL = os.getenv("CACHE_PRICE_INTERVAL", "1d")
CACHE_REQUEST_TIMEOUT = int(os.getenv("CACHE_REQUEST_TIMEOUT", "20"))
CACHE_REQUEST_SLEEP_SECONDS = float(os.getenv("CACHE_REQUEST_SLEEP_SECONDS", "0.18"))
CACHE_MAX_FAILURES = int(os.getenv("CACHE_MAX_FAILURES", "250"))

# Safety limits prevent accidental 2,000+ symbol refreshes during every manual test.
# Weekly full refresh ignores HIGH_QUALITY limit and uses the full universe.
CACHE_HIGH_QUALITY_LIMIT = int(os.getenv("CACHE_HIGH_QUALITY_LIMIT", "250"))
CACHE_DAILY_TRADABLE_LIMIT = int(os.getenv("CACHE_DAILY_TRADABLE_LIMIT", "1500"))

FORCE_UNIVERSE_REFRESH = _env_bool("FORCE_UNIVERSE_REFRESH", "false")
FORCE_FULL_CACHE_REFRESH = _env_bool("FORCE_FULL_CACHE_REFRESH", "false")
FORCE_PRICE_REFRESH = _env_bool("FORCE_PRICE_REFRESH", "false")
RUN_WEEKLY_JOBS_FORCE = _env_bool("RUN_WEEKLY_JOBS_FORCE", "false")

# Output aliases used by the cache-aware code.
CACHE_INDICES = [NIFTY_SYMBOL, "^NSEBANK", INDIA_VIX_SYMBOL]

# ===================================================================
# NEWS FETCH / AI COST CONTROL
# ===================================================================
# Full NSE scanning should remain deterministic and fast. News and AI are only
# run after the first-pass ranking has reduced the universe.
NEWS_FETCH_UNIVERSE_FILE = os.getenv("NEWS_FETCH_UNIVERSE_FILE", "news_fetch_universe.txt")
AI_NEWS_UNIVERSE_FILE = os.getenv("AI_NEWS_UNIVERSE_FILE", "ai_news_universe.txt")
PRE_NEWS_CANDIDATES_FILE = os.getenv("PRE_NEWS_CANDIDATES_FILE", "pre_news_candidates.csv")
NEWS_FETCH_REPORT_FILE = os.getenv("NEWS_FETCH_REPORT_FILE", "news_fetch_report.csv")
NEWS_FETCH_SUMMARY_FILE = os.getenv("NEWS_FETCH_SUMMARY_FILE", "news_fetch_summary.txt")
NEWS_CACHE_DIR = os.getenv("NEWS_CACHE_DIR", "news_cache")

# News is fetched for top deterministic candidates only. Active holdings are
# always included on top of this limit when needed.
NEWS_FETCH_TOP_N = int(os.getenv("NEWS_FETCH_TOP_N", "40"))
AI_NEWS_SYMBOL_LIMIT = int(os.getenv("AI_NEWS_SYMBOL_LIMIT", "15"))
NEWS_MAX_HEADLINES_PER_SYMBOL = int(os.getenv("NEWS_MAX_HEADLINES_PER_SYMBOL", "8"))
NEWS_FETCH_MAX_WORKERS = int(os.getenv("NEWS_FETCH_MAX_WORKERS", "10"))
NEWS_FETCH_TIMEOUT_SECONDS = int(os.getenv("NEWS_FETCH_TIMEOUT_SECONDS", "8"))
NEWS_CACHE_TTL_HOURS = float(os.getenv("NEWS_CACHE_TTL_HOURS", "12"))
NEWS_ALLOW_STALE_CACHE_ON_FAILURE = _env_bool("NEWS_ALLOW_STALE_CACHE_ON_FAILURE", "true")

# ===================================================================
# SMART OHLCV CACHE / MARKET CALENDAR FINAL STEP
# ===================================================================
# Prevents repeated GitHub/manual runs from redownloading the same OHLCV data
# when the cache already contains the latest completed NSE trading-day candle.

CACHE_USE_LATEST_CANDLE_CHECK = _env_bool("CACHE_USE_LATEST_CANDLE_CHECK", "true")

# Yahoo daily candles for NSE are normally available after market close.
# 16:15 IST gives a buffer after the 15:30 close. If you schedule before this,
# the expected candle will be the previous trading day.
MARKET_DATA_READY_TIME_IST = os.getenv("MARKET_DATA_READY_TIME_IST", "16:15")

# Optional plain text/CSV file with exchange holidays. One date per line is enough.
# Supported formats: YYYY-MM-DD, DD-MM-YYYY, DD/MM/YYYY, DD-Mon-YYYY.
# If absent, weekends are still handled; holidays are simply unknown.
NSE_TRADING_HOLIDAYS_FILE = os.getenv("NSE_TRADING_HOLIDAYS_FILE", "nse_trading_holidays.csv")

# If Yahoo was just queried but still returned yesterday's candle, wait before
# trying again on manual reruns. This avoids repeated downloads when data is delayed.
CACHE_STALE_CANDLE_RETRY_HOURS = float(os.getenv("CACHE_STALE_CANDLE_RETRY_HOURS", "1.0"))

# If cache lags the expected candle by this many trading/calendar days, always
# try to repair it instead of relying only on file age.
CACHE_REDOWNLOAD_IF_LAST_CANDLE_OLDER_THAN_DAYS = int(os.getenv("CACHE_REDOWNLOAD_IF_LAST_CANDLE_OLDER_THAN_DAYS", "2"))

# ===================================================================
# MANUAL PORTFOLIO / REPORT CLEANUP FINAL STEP
# ===================================================================
# BUY recommendations are recommendations only. The system tracks only the
# positions you explicitly list in MANUAL_PORTFOLIO_JSON.
PORTFOLIO_SOURCE = os.getenv("PORTFOLIO_SOURCE", "MANUAL_ENV").strip().upper()
AUTO_TRACK_RECOMMENDED_BUYS = _env_bool("AUTO_TRACK_RECOMMENDED_BUYS", "false")
AUTO_CLOSE_EXIT_SIGNALS = _env_bool("AUTO_CLOSE_EXIT_SIGNALS", "false")
MANUAL_PORTFOLIO_JSON = os.getenv("MANUAL_PORTFOLIO_JSON", "").strip()
MANUAL_PORTFOLIO_REPORT_FILE = os.getenv("MANUAL_PORTFOLIO_REPORT_FILE", "manual_portfolio_report.txt")
MANUAL_PORTFOLIO_REQUIRE_POSITION_SIZE = _env_bool("MANUAL_PORTFOLIO_REQUIRE_POSITION_SIZE", "false")

# Reporting and classification guardrails.
PORTFOLIO_UNKNOWN_EXPOSURE_LABEL = os.getenv("PORTFOLIO_UNKNOWN_EXPOSURE_LABEL", "Unknown - add position_pct or quantity in MANUAL_PORTFOLIO_JSON")
WATCHLIST_CONFIDENCE_BUFFER = float(os.getenv("WATCHLIST_CONFIDENCE_BUFFER", "10"))
WATCHLIST_TQ_BUFFER = float(os.getenv("WATCHLIST_TQ_BUFFER", "8"))
WATCHLIST_MIN_TQ_FLOOR = float(os.getenv("WATCHLIST_MIN_TQ_FLOOR", "72"))
WATCHLIST_MIN_CONF_FLOOR = float(os.getenv("WATCHLIST_MIN_CONF_FLOOR", "70"))
REJECTED_REPORT_COUNT = int(os.getenv("REJECTED_REPORT_COUNT", "6"))
HOLD_REPORT_COUNT = int(os.getenv("HOLD_REPORT_COUNT", "8"))
WATCHLIST_REPORT_COUNT = int(os.getenv("WATCHLIST_REPORT_COUNT", "8"))

# A small explicit sector fallback list. Expand sector_master.csv later for full coverage.
SECTOR_OVERRIDES = {
    "SYRMA.NS": "Electronics Manufacturing",
    "NETWEB.NS": "IT Hardware",
    "RAMCOSYS.NS": "IT",
    "HONASA.NS": "FMCG",
    "GLAND.NS": "Pharma",
    "BELRISE.NS": "Auto",
    "CARBORUNIV.NS": "Capital Goods",
    "ADANIPOWER.NS": "Power",
    "EMCURE.NS": "Pharma",
    "SAILIFE.NS": "Pharma",
    "WELCORP.NS": "Metals",
    "KEI.NS": "Capital Goods",
    "BHARATFORG.NS": "Auto",
    "BHEL.NS": "Capital Goods",
}
UNMAPPED_SECTOR_LABEL = os.getenv("UNMAPPED_SECTOR_LABEL", "UNMAPPED")
SECTOR_MASTER_FILE = os.getenv("SECTOR_MASTER_FILE", "sector_master.csv")

# ===================================================================
# MANUAL PORTFOLIO + FINAL REPORT CLEANUP OVERRIDES
# ===================================================================
# BUY recommendations are recommendations only. Actual holdings are loaded from
# MANUAL_PORTFOLIO_JSON through manual_portfolio_loader.py.
PORTFOLIO_SOURCE = os.getenv("PORTFOLIO_SOURCE", "MANUAL_ENV").strip().upper()
AUTO_TRACK_RECOMMENDED_BUYS = _env_bool("AUTO_TRACK_RECOMMENDED_BUYS", "false")
MANUAL_PORTFOLIO_JSON = os.getenv("MANUAL_PORTFOLIO_JSON", "").strip()
MANUAL_PORTFOLIO_FILE = os.getenv("MANUAL_PORTFOLIO_FILE", "manual_portfolio.json")
PORTFOLIO_SOURCE_REPORT_FILE = os.getenv("PORTFOLIO_SOURCE_REPORT_FILE", "portfolio_source_report.txt")
MANUAL_PORTFOLIO_REQUIRED_FIELDS = ["symbol", "entry_price", "entry_date"]
DEFAULT_MANUAL_POSITION_PCT = os.getenv("DEFAULT_MANUAL_POSITION_PCT", "").strip()
UNMAPPED_SECTOR_LABEL = os.getenv("UNMAPPED_SECTOR_LABEL", "UNMAPPED")
SECTOR_MASTER_FILE = os.getenv("SECTOR_MASTER_FILE", "sector_master.csv")
WATCHLIST_CONFIDENCE_BUFFER = float(os.getenv("WATCHLIST_CONFIDENCE_BUFFER", "10"))
WATCHLIST_TRADE_QUALITY_BUFFER = float(os.getenv("WATCHLIST_TRADE_QUALITY_BUFFER", "10"))
WATCHLIST_MAX_FAILED_GATES = int(os.getenv("WATCHLIST_MAX_FAILED_GATES", "2"))
REPORT_MAX_WATCHLIST = int(os.getenv("REPORT_MAX_WATCHLIST", "6"))
REPORT_MAX_REJECTED = int(os.getenv("REPORT_MAX_REJECTED", "6"))
REPORT_SHOW_FULL_HOLD_DETAIL = _env_bool("REPORT_SHOW_FULL_HOLD_DETAIL", "false")

# If the user supplies a GroqCloud key but not explicit xAI/Grok settings, use
# the Groq OpenAI-compatible endpoint by default. This prevents the common
# situation where GROQ_API_KEY exists but requests are accidentally sent to xAI.
if os.getenv("GROQ_API_KEY", "") and not os.getenv("GROK_API_URL", ""):
    GROK_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROK_MODEL = os.getenv("GROK_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))

# Prefer GroqCloud defaults automatically when only GROQ_API_KEY is provided.
if os.getenv("GROQ_API_KEY") and not os.getenv("GROK_API_KEY") and not os.getenv("GROK_API_URL"):
    GROK_API_KEY_ENV_NAME = "GROQ_API_KEY"
    GROK_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROK_API_URL = os.getenv("GROK_API_URL", "https://api.groq.com/openai/v1/chat/completions")
    GROK_MODEL = os.getenv("GROK_MODEL", os.getenv("GROQ_MODEL", "llama-3.1-8b-instant"))
