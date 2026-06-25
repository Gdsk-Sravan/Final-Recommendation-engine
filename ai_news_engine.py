"""
ai_news_engine.py - Optional AI news risk layer for selected symbols only.

This module runs after news_engine_v2.py. It does NOT scan the full NSE
universe. It only reviews symbols listed in ai_news_universe.txt, normally:
  - active holdings
  - top 10-20 deterministic candidates

If Groq/Grok is unavailable, the module writes deterministic fallback rows from
news_scores.csv and the rest of the pipeline continues.
"""

from __future__ import annotations

import csv
import json
import os
import time
from typing import Dict, Iterable, List, Optional, Tuple

import requests

from config import (
    AI_NEWS_SCORES_FILE,
    AI_NEWS_SYMBOL_LIMIT,
    AI_NEWS_UNIVERSE_FILE,
    GROQ_API_KEY as CONFIG_GROQ_API_KEY,
    GROQ_MAX_RETRY as CONFIG_GROQ_MAX_RETRY,
    GROQ_MODEL as CONFIG_GROQ_MODEL,
    GROQ_TIMEOUT as CONFIG_GROQ_TIMEOUT,
    NEWS_HEADLINES_FILE,
    NEWS_SCORES_FILE,
)

GROQ_API_KEY = CONFIG_GROQ_API_KEY or os.getenv("GROQ_API_KEY", "") or os.getenv("GROK_API_KEY", "")
GROQ_API_URL = os.getenv("GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions")
GROQ_MODEL = CONFIG_GROQ_MODEL
GROQ_TIMEOUT = CONFIG_GROQ_TIMEOUT
GROQ_MAX_RETRY = CONFIG_GROQ_MAX_RETRY
GROQ_RPM_DELAY = float(os.getenv("GROQ_RPM_DELAY", "0.4"))
MAX_HEADLINES = int(os.getenv("AI_NEWS_MAX_HEADLINES", "8"))

BLACK_SWAN_KEYWORDS = [
    "usfda", "fda import alert", "fda ban", "fda warning letter",
    "complete response letter", "crl ", "sebi ban", "sebi order",
    "sebi investigation", "sebi notice", "enforcement directorate",
    "ed raid", "cbi raid", "income tax raid", "fraud", "fraudulent",
    "accounting fraud", "falsified", "forensic audit", "accounting irregularities",
    "promoter arrested", "ceo arrested", "cfo arrested", "md arrested",
    "bankruptcy", "insolvency proceedings", "nclt admission", "liquidation order",
    "debt default", "loan default", "insider trading",
]

SYSTEM_PROMPT = """You are a senior quantitative analyst specialising in Indian equity news risk.

You will receive a JSON object with a stock symbol and recent headlines.
Return ONLY a valid JSON object with exactly these keys:
{
  "sentiment": "Positive" | "Negative" | "Neutral",
  "severity": integer 0-100,
  "event_type": string,
  "swing_impact": "High" | "Medium" | "Low",
  "black_swan": true | false,
  "black_swan_reason": string or null,
  "summary": string
}

Rules:
- Do not invent facts beyond the provided headlines.
- Treat USFDA bans/import alerts, SEBI enforcement, fraud, raids, insolvency,
  promoter/CEO/CFO arrest, and severe governance failures as black-swan risk.
- Positive news can be positive, but do not ignore severe negative risk.
- Keep summary to one short sentence.
Return JSON only. No markdown. No prose outside JSON."""

FIELDNAMES = [
    "SYMBOL",
    "AI_SCORE",
    "AI_SEVERITY",
    "AI_SENTIMENT",
    "AI_EVENT_TYPE",
    "AI_SWING_IMPACT",
    "BLACK_SWAN",
    "BLACK_SWAN_REASON",
    "AI_SUMMARY",
]


def _norm_symbol(raw: str) -> str:
    s = (raw or "").strip().upper()
    if not s:
        return ""
    if s.startswith("^") or s.endswith(".NS") or s.endswith(".BO"):
        return s
    return f"{s}.NS"


def _dedupe(symbols: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in symbols:
        sym = _norm_symbol(str(raw))
        if not sym or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def _read_symbol_limit() -> List[str]:
    if not os.path.exists(AI_NEWS_UNIVERSE_FILE):
        return []
    symbols: List[str] = []
    with open(AI_NEWS_UNIVERSE_FILE, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                symbols.append(line.split(",")[0].strip())
    return _dedupe(symbols)[:AI_NEWS_SYMBOL_LIMIT]


def _has_black_swan_keyword(text: str) -> Tuple[bool, str]:
    t = text.lower()
    for kw in BLACK_SWAN_KEYWORDS:
        if kw in t:
            return True, kw
    return False, ""


def _load_headlines() -> Dict[str, List[str]]:
    data: Dict[str, List[str]] = {}
    if not os.path.exists(NEWS_HEADLINES_FILE):
        return data

    allowed_order = _read_symbol_limit()
    allowed = set(allowed_order) if allowed_order else set()

    with open(NEWS_HEADLINES_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = _norm_symbol(row.get("Symbol") or row.get("SYMBOL") or "")
            headline = (row.get("Headline") or row.get("HEADLINE") or "").strip()
            if not sym or not headline:
                continue
            if allowed and sym not in allowed:
                continue
            data.setdefault(sym, [])
            if headline not in data[sym]:
                data[sym].append(headline)

    if allowed_order:
        ordered: Dict[str, List[str]] = {}
        for sym in allowed_order:
            if sym in data:
                ordered[sym] = data[sym]
        return ordered

    return dict(list(data.items())[:AI_NEWS_SYMBOL_LIMIT])


def _load_kw_scores() -> Dict[str, Dict[str, object]]:
    data: Dict[str, Dict[str, object]] = {}
    if not os.path.exists(NEWS_SCORES_FILE):
        return data
    with open(NEWS_SCORES_FILE, "r", newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = _norm_symbol(row.get("SYMBOL") or "")
            if not sym:
                continue
            try:
                severity = int(float(row.get("MAX_SEVERITY") or 0))
            except Exception:
                severity = 0
            try:
                score = float(row.get("NEWS_SCORE") or 50.0)
            except Exception:
                score = 50.0
            black = str(row.get("BLACK_SWAN", "0")).strip() in ("1", "true", "True")
            data[sym] = {
                "score": score,
                "severity": severity,
                "sentiment": row.get("SENTIMENT") or "Neutral",
                "event_type": row.get("EVENT_TYPE") or "Neutral",
                "black_swan": black,
                "summary": row.get("EVENT_SUMMARY") or row.get("EVENT_TYPE") or "Keyword news baseline.",
            }
    return data


def _build_user_prompt(symbol: str, headlines: List[str]) -> str:
    return json.dumps({"symbol": symbol, "headlines": headlines[:MAX_HEADLINES]}, ensure_ascii=False)


def _call_groq(symbol: str, headlines: List[str]) -> Optional[Dict[str, object]]:
    if not GROQ_API_KEY:
        return None

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(symbol, headlines)},
        ],
        "temperature": 0.1,
        "max_tokens": 512,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    for attempt in range(1, GROQ_MAX_RETRY + 1):
        try:
            resp = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=GROQ_TIMEOUT)
            if resp.status_code == 429:
                time.sleep(2.5 * attempt)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as exc:
            if attempt == GROQ_MAX_RETRY:
                print(f"    [AI] {symbol} failed: {exc}")
            else:
                time.sleep(1.0 * attempt)
    return None


def _validate(raw: Optional[Dict[str, object]], headlines: List[str], kw: Dict[str, object]) -> Dict[str, object]:
    result = {
        "sentiment": kw.get("sentiment", "Neutral"),
        "severity": int(kw.get("severity", 0) or 0),
        "event_type": kw.get("event_type", "Neutral"),
        "swing_impact": "Low",
        "black_swan": bool(kw.get("black_swan", False)),
        "black_swan_reason": "Keyword baseline" if kw.get("black_swan") else None,
        "summary": kw.get("summary", "No significant event detected."),
    }

    if raw:
        result.update(raw)

    if result.get("sentiment") not in ("Positive", "Negative", "Neutral"):
        result["sentiment"] = "Neutral"
    if result.get("swing_impact") not in ("High", "Medium", "Low"):
        result["swing_impact"] = "Low"

    try:
        result["severity"] = max(0, min(100, int(float(result.get("severity", 0) or 0))))
    except Exception:
        result["severity"] = 0

    result["black_swan"] = bool(result.get("black_swan", False))

    all_text = " ".join(headlines)
    kw_flag, kw_reason = _has_black_swan_keyword(all_text)
    if kw_flag:
        result["black_swan"] = True
        result["black_swan_reason"] = result.get("black_swan_reason") or f"Keyword match: {kw_reason}"
        result["severity"] = max(int(result["severity"]), 85)
        result["sentiment"] = "Negative"
        result["swing_impact"] = "High"
        if "BlackSwan" not in str(result.get("event_type", "")):
            result["event_type"] = "BlackSwan_Regulatory"

    if not str(result.get("summary") or "").strip():
        result["summary"] = "No significant event detected."

    return result


def _score_from_result(result: Dict[str, object]) -> float:
    severity = int(result.get("severity", 0) or 0)
    sentiment = str(result.get("sentiment", "Neutral"))
    if result.get("black_swan"):
        return 5.0
    if sentiment == "Positive":
        return min(100.0, 50.0 + severity * 0.5)
    if sentiment == "Negative":
        return max(0.0, 50.0 - severity * 0.5)
    return 50.0


def _fallback_result(symbol: str, kw_scores: Dict[str, Dict[str, object]]) -> Dict[str, object]:
    kw = kw_scores.get(symbol, {})
    black = bool(kw.get("black_swan", False))
    severity = int(kw.get("severity", 0) or 0)
    score = float(kw.get("score", 50.0) or 50.0)
    if black:
        score = min(score, 5.0)
        severity = max(severity, 85)
    return {
        "SYMBOL": symbol,
        "AI_SCORE": round(score, 2),
        "AI_SEVERITY": severity,
        "AI_SENTIMENT": kw.get("sentiment", "Neutral"),
        "AI_EVENT_TYPE": kw.get("event_type", "Neutral"),
        "AI_SWING_IMPACT": "High" if black or severity >= 75 else ("Medium" if severity >= 50 else "Low"),
        "BLACK_SWAN": 1 if black else 0,
        "BLACK_SWAN_REASON": "Keyword baseline" if black else "",
        "AI_SUMMARY": kw.get("summary", "AI unavailable; keyword baseline used."),
    }


def main() -> None:
    headlines_by_symbol = _load_headlines()
    kw_scores = _load_kw_scores()

    if not headlines_by_symbol:
        print(f"[WARN] No headlines available in {NEWS_HEADLINES_FILE}; writing fallback AI scores if possible.")
        symbols = _read_symbol_limit() or list(kw_scores.keys())[:AI_NEWS_SYMBOL_LIMIT]
        rows = [_fallback_result(sym, kw_scores) for sym in symbols]
    else:
        use_ai = bool(GROQ_API_KEY)
        if use_ai:
            print(f"[INFO] AI news enabled: {GROQ_MODEL}; symbols={len(headlines_by_symbol)}")
        else:
            print("[INFO] GROQ/GROK API key not set; using keyword fallback for AI news rows")

        rows = []
        print("\nAI NEWS ENGINE - LIMITED SECOND PASS")
        print("=" * 80)
        for symbol, headlines in headlines_by_symbol.items():
            kw = kw_scores.get(symbol, {})
            raw = None
            if use_ai:
                raw = _call_groq(symbol, headlines)
                time.sleep(GROQ_RPM_DELAY)
            result = _validate(raw, headlines, kw)
            score = _score_from_result(result) if use_ai else float(kw.get("score", 50.0) or 50.0)
            if result.get("black_swan"):
                score = min(score, 5.0)

            row = {
                "SYMBOL": symbol,
                "AI_SCORE": round(score, 2),
                "AI_SEVERITY": int(result.get("severity", 0) or 0),
                "AI_SENTIMENT": result.get("sentiment", "Neutral"),
                "AI_EVENT_TYPE": result.get("event_type", "Neutral"),
                "AI_SWING_IMPACT": result.get("swing_impact", "Low"),
                "BLACK_SWAN": 1 if result.get("black_swan") else 0,
                "BLACK_SWAN_REASON": result.get("black_swan_reason") or "",
                "AI_SUMMARY": result.get("summary", ""),
            }
            rows.append(row)
            flag = " BLACK_SWAN" if row["BLACK_SWAN"] else ""
            print(f"  {symbol:<24} score={row['AI_SCORE']:>5} sev={row['AI_SEVERITY']:>3} {row['AI_SENTIMENT']:<8} {row['AI_EVENT_TYPE']}{flag}")

    with open(AI_NEWS_SCORES_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})

    print("\nAI NEWS OUTPUT")
    print("=" * 80)
    print(f"Rows written: {len(rows)}")
    print(f"Saved       : {AI_NEWS_SCORES_FILE}")


def load_ai_scores(path: str = AI_NEWS_SCORES_FILE) -> Dict[str, Dict[str, object]]:
    data: Dict[str, Dict[str, object]] = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", newline="", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("SYMBOL", "").strip()
            if not sym:
                continue
            data[sym] = {
                "ai_score": float(row.get("AI_SCORE") or 50.0),
                "ai_severity": int(float(row.get("AI_SEVERITY") or 0)),
                "ai_sentiment": row.get("AI_SENTIMENT", "Neutral"),
                "ai_event_type": row.get("AI_EVENT_TYPE", "Neutral"),
                "ai_swing_impact": row.get("AI_SWING_IMPACT", "Low"),
                "black_swan": str(row.get("BLACK_SWAN", "0")) in ("1", "true", "True"),
                "black_swan_reason": row.get("BLACK_SWAN_REASON", ""),
                "ai_summary": row.get("AI_SUMMARY", ""),
            }
    return data


if __name__ == "__main__":
    main()
