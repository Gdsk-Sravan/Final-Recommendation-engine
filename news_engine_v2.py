"""
news_engine_v2.py — Decay-Weighted News Scoring with Event Classification

DESIGN RATIONALE
────────────────
Previous version: bag-of-words, no decay, no severity, no event detection.
Every headline (whether from yesterday or 3 weeks ago) had equal weight.
"cuts losses" scored negative twice; "buy" scored positive in any context.

This version implements:

1. NEWS DECAY
   Age of each headline reduces its weight exponentially:
     0–1 days  → 1.00  (full weight)
     2–3 days  → 0.80
     4–7 days  → 0.60
     8–14 days → 0.30
     15+ days  → 0.10

2. EVENT CLASSIFICATION & SEVERITY SCORING
   Each headline is matched against ordered event templates.
   Events are categorized and assigned a raw severity (0–100).
   Black-swan events (fraud, USFDA ban, SEBI action, bankruptcy)
   receive HARD PENALTIES that override the aggregate score.

3. CONTEXTUAL NEGATION
   Words like "not", "no", "dismisses", "denies", "avoids" in a
   ±3-token window before a keyword flip the sentiment of that token.

4. OUTPUT FORMAT
   news_scores.txt:
     SYMBOL,NEWS_SCORE,MAX_SEVERITY,EVENT_TYPE,SENTIMENT

   BLACK_SWAN stocks are flagged with severity ≥ 90 and event
   category "BlackSwan" so fusion_scanner can penalize or exclude them.
"""

import csv
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from config import NEWS_HEADLINES_FILE, NEWS_SCORES_FILE

INPUT_FILE  = NEWS_HEADLINES_FILE
OUTPUT_FILE = NEWS_SCORES_FILE

# ─────────────────────────────────────────────────────────────────────
# DECAY TABLE  (age in days → weight multiplier)
# ─────────────────────────────────────────────────────────────────────
DECAY_TABLE = [
    (1,  1.00),
    (3,  0.80),
    (7,  0.60),
    (14, 0.30),
]
DECAY_FLOOR = 0.10   # anything older than 14 days


def _decay_weight(date_str: str) -> float:
    """Return the decay multiplier for a headline given its ISO-8601 date."""
    try:
        pub = datetime.strptime(date_str[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        age_days = (datetime.now(timezone.utc) - pub).total_seconds() / 86400
    except Exception:
        return DECAY_FLOOR   # unknown date → minimal weight

    for max_age, weight in DECAY_TABLE:
        if age_days <= max_age:
            return weight
    return DECAY_FLOOR


# ─────────────────────────────────────────────────────────────────────
# EVENT DEFINITIONS
# ─────────────────────────────────────────────────────────────────────
# Format: (event_type, sentiment, base_severity, keywords_any_of)
# Ordered from highest to lowest severity — first match wins.

EVENT_RULES: List[Tuple[str, str, int, List[str]]] = [
    # ── BLACK SWAN  (severity 80–100) ─────────────────────────────────
    ("BlackSwan_Fraud",       "Negative", 98,
     ["fraud", "fraudulent", "financial fraud", "accounting fraud", "money laundering"]),
    ("BlackSwan_Regulatory",  "Negative", 95,
     ["usfda", "fda import alert", "fda ban", "import ban", "sebi ban",
      "sebi order", "sebi action", "sebi probe", "ed raid", "cbi raid",
      "income tax raid", "it raid", "enforcement directorate"]),
    ("BlackSwan_Governance",  "Negative", 90,
     ["promoter arrested", "ceo arrested", "md arrested", "cfo arrested",
      "promoter fraud", "board fraud", "governance failure",
      "forensic audit", "accounting irregularities", "falsified accounts"]),
    ("BlackSwan_Insolvency",  "Negative", 88,
     ["bankruptcy", "insolvency", "nclt", "liquidation", "debt default",
      "payment default", "loan default", "npa", "corporate insolvency"]),

    # ── HIGH RISK  (severity 60–79) ────────────────────────────────────
    ("RegulatoryRisk",        "Negative", 75,
     ["regulatory action", "penalty imposed", "fine imposed", "show cause",
      "sebi notice", "rbi action", "competition commission", "cci order"]),
    ("PromoterRisk",          "Negative", 70,
     ["promoter pledge", "pledged shares", "promoter sells", "promoter stake sale",
      "promoter offloads", "promoter exits"]),
    ("DebtRisk",              "Negative", 68,
     ["credit downgrade", "rating downgrade", "moody's downgrade", "icra downgrade",
      "crisil downgrade", "debt restructuring", "stressed asset", "loan recall"]),
    ("LitigationRisk",        "Negative", 65,
     ["lawsuit", "litigation", "court order", "high court", "supreme court",
      "class action", "arbitration loss", "arbitration penalty"]),
    ("PlantShutdown",         "Negative", 62,
     ["plant shutdown", "plant closure", "factory shut", "facility closed",
      "production halt", "manufacturing halt"]),
    ("ManagementRisk",        "Negative", 60,
     ["ceo resigns", "cfo resigns", "md resigns", "ceo quits", "cfo quits",
      "key management exits", "board resignation", "chairman resigns"]),

    # ── MODERATE RISK  (severity 30–59) ───────────────────────────────
    ("EarningsWarning",       "Negative", 50,
     ["earnings warning", "profit warning", "guidance cut", "revenue miss",
      "eps miss", "below estimate", "disappoints", "shortfall", "weak results"]),
    ("AnalystDowngrade",      "Negative", 40,
     ["downgrade", "underperform", "reduce", "sell rating", "target cut",
      "price target cut", "below expectation"]),
    ("MinorNegative",         "Negative", 25,
     ["loss", "decline", "fall", "drops", "plunges", "weak", "bearish",
      "concern", "worry", "risk", "negative", "pressure"]),

    # ── POSITIVE CATALYSTS  (severity = impact, higher = more positive) ─
    ("LargeContract",         "Positive", 72,
     ["large order", "mega order", "landmark contract", "record order",
      "billion dollar", "multi-year contract", "strategic contract"]),
    ("Acquisition",           "Positive", 65,
     ["acquires", "acquisition", "takeover", "merger", "buyout", "stake purchase",
      "stake buy"]),
    ("CapacityExpansion",     "Positive", 55,
     ["capacity expansion", "new plant", "greenfield", "brownfield",
      "capex announcement", "new facility", "doubles capacity"]),
    ("OrderWin",              "Positive", 50,
     ["wins order", "secures order", "bags order", "order win", "contract win",
      "secures contract", "bags contract", "awarded contract"]),
    ("EarningsBeat",          "Positive", 48,
     ["beats estimate", "beats expectation", "above estimate", "record profit",
      "record revenue", "strong results", "best quarter", "q-o-q growth"]),
    ("AnalystUpgrade",        "Positive", 45,
     ["upgrade", "outperform", "buy rating", "target raised", "price target raised",
      "overweight", "strong buy", "accumulate"]),
    ("StrategicPartnership",  "Positive", 42,
     ["partnership", "joint venture", "collaboration", "mou", "strategic alliance",
      "tie-up", "agreement"]),
    ("FundingEvent",          "Positive", 40,
     ["qip", "fund raise", "rights issue", "private placement", "fpo",
      "preferential allotment", "institutional investors"]),
    ("MinorPositive",         "Positive", 20,
     ["growth", "strong", "record", "surge", "rally", "gains", "profit",
      "bullish", "positive", "optimistic"]),
]

# Negation words that flip the immediately following sentiment signal
NEGATION_TOKENS = {
    "not", "no", "never", "neither", "denies", "deny", "dismisses",
    "dismiss", "avoids", "avoid", "rejects", "reject", "clears",
    "cleared", "resolved", "acquitted", "exonerated",
}


# ─────────────────────────────────────────────────────────────────────
# HEADLINE SCORER
# ─────────────────────────────────────────────────────────────────────

def _tokenize(text: str) -> List[str]:
    return re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()


def _has_negation_near(tokens: List[str], phrase_start: int) -> bool:
    """Check if any negation token appears within 3 positions before phrase_start."""
    window = max(0, phrase_start - 3)
    return any(t in NEGATION_TOKENS for t in tokens[window:phrase_start])


def classify_headline(headline: str) -> Tuple[str, str, int]:
    """
    Returns (event_type, sentiment, severity) for a single headline.
    Checks every event rule (ordered) and returns the first match.
    Applies contextual negation: if negation found near trigger phrase,
    flips Negative↔Positive and halves severity.
    """
    text   = headline.lower()
    tokens = _tokenize(headline)

    for event_type, sentiment, severity, keywords in EVENT_RULES:
        for kw in keywords:
            if kw in text:
                # Find approximate token position for negation check
                kw_tokens  = kw.split()
                phrase_pos = 0
                for t_idx, tok in enumerate(tokens):
                    if tok == kw_tokens[0]:
                        phrase_pos = t_idx
                        break

                if _has_negation_near(tokens, phrase_pos):
                    # Negation detected: flip sentiment, halve severity
                    flipped_sentiment = "Positive" if sentiment == "Negative" else "Negative"
                    return event_type + "_Negated", flipped_sentiment, severity // 2

                return event_type, sentiment, severity

    return "NoEvent", "Neutral", 0


def headline_to_score(sentiment: str, severity: int) -> float:
    """
    Convert a sentiment+severity pair to a numeric score in [0, 100].
      Neutral  → 50
      Positive → 50 + severity * 0.5  (max = 100)
      Negative → 50 - severity * 0.5  (min = 0)
    """
    if sentiment == "Positive":
        return min(50 + severity * 0.5, 100)
    elif sentiment == "Negative":
        return max(50 - severity * 0.5, 0)
    return 50.0


# ─────────────────────────────────────────────────────────────────────
# AGGREGATOR
# ─────────────────────────────────────────────────────────────────────

def aggregate_scores(
    rows: List[Dict]
) -> Tuple[float, int, str, str]:
    """
    Aggregate multiple headlines for a single stock into:
      (final_score, max_severity, dominant_event_type, dominant_sentiment)

    Uses decay-weighted average.  Black-swan events apply a hard floor
    that clamps the stock's score to ≤ 10 regardless of other headlines.
    """
    if not rows:
        return 50.0, 0, "NoEvent", "Neutral"

    weighted_score_sum = 0.0
    total_weight       = 0.0
    max_severity       = 0
    dominant_event     = "NoEvent"
    dominant_sentiment = "Neutral"
    black_swan         = False

    for row in rows:
        date_str = row.get("Date", "")
        headline = row.get("Headline", "")

        event_type, sentiment, severity = classify_headline(headline)
        weight = _decay_weight(date_str)
        score  = headline_to_score(sentiment, severity)

        weighted_score_sum += score * weight
        total_weight       += weight

        if severity > max_severity:
            max_severity       = severity
            dominant_event     = event_type
            dominant_sentiment = sentiment

        if "BlackSwan" in event_type:
            black_swan = True

    if total_weight == 0:
        return 50.0, 0, "NoEvent", "Neutral"

    final_score = weighted_score_sum / total_weight

    # Hard floor for black-swan events
    if black_swan:
        final_score = min(final_score, 10.0)
        dominant_event = dominant_event  # keep the specific black swan type

    return round(final_score, 2), max_severity, dominant_event, dominant_sentiment


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"[ERROR] {INPUT_FILE} not found — run news_fetcher_v2.py first")
        return

    # ── Group headlines by symbol ─────────────────────────────────────
    symbol_rows: Dict[str, List[Dict]] = {}

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("Symbol", "").strip()
            if not sym:
                continue
            if sym not in symbol_rows:
                symbol_rows[sym] = []
            symbol_rows[sym].append(row)

    if not symbol_rows:
        print("[WARN] No data found in news_headlines.csv")
        return

    # ── Score each symbol ─────────────────────────────────────────────
    results = []
    for symbol, rows in symbol_rows.items():
        score, severity, event_type, sentiment = aggregate_scores(rows)
        results.append({
            "symbol":    symbol,
            "score":     score,
            "severity":  severity,
            "event":     event_type,
            "sentiment": sentiment,
            "count":     len(rows),
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    # ── Write output ──────────────────────────────────────────────────
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["SYMBOL", "NEWS_SCORE", "MAX_SEVERITY", "EVENT_TYPE", "SENTIMENT", "BLACK_SWAN", "HEADLINE_COUNT", "SOURCE_TYPE", "URGENCY", "EVENT_SUMMARY", "ACTION_IMPACT"])
        writer.writeheader()
        for r in results:
            black = 1 if "BlackSwan" in r["event"] else 0
            urgency = "HIGH" if r["severity"] >= 75 else ("MEDIUM" if r["severity"] >= 50 else "LOW")
            action_impact = "BLOCK_BUY_OR_EXIT" if black or r["severity"] >= 85 else ("WATCHLIST_OR_CAUTION" if r["severity"] >= 60 and r["sentiment"] == "Negative" else "NONE")
            writer.writerow({"SYMBOL": r["symbol"], "NEWS_SCORE": r["score"], "MAX_SEVERITY": r["severity"], "EVENT_TYPE": r["event"], "SENTIMENT": r["sentiment"], "BLACK_SWAN": black, "HEADLINE_COUNT": r["count"], "SOURCE_TYPE": "headline_keyword", "URGENCY": urgency, "EVENT_SUMMARY": r["event"], "ACTION_IMPACT": action_impact})

    # ── Console report ────────────────────────────────────────────────
    print("\nNEWS ENGINE V2  —  Decay + Event Classification")
    print("=" * 80)
    print(f"  {'SYMBOL':<22} {'SCORE':>6} {'SEV':>5} {'SENTIMENT':>10}  EVENT")
    print(f"  {'-'*72}")
    for r in results[:20]:
        flag = " ⚠️  BLACK SWAN" if "BlackSwan" in r["event"] else ""
        print(
            f"  {r['symbol']:<22} {r['score']:>6.1f} {r['severity']:>5}  "
            f"{r['sentiment']:>10}  {r['event']}{flag}"
        )

    black_swans = [r for r in results if "BlackSwan" in r["event"]]
    if black_swans:
        print(f"\n  ⛔ BLACK SWAN ALERTS ({len(black_swans)}):")
        for bs in black_swans:
            print(f"    {bs['symbol']} — {bs['event']} (severity {bs['severity']})")

    print(f"\n  Symbols scored : {len(results)}")
    print(f"  Saved          : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
