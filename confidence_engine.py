"""
confidence_engine.py - Interpretable scoring and exit-risk engine.

The final confidence is component-based and calibrated by regime. The separate
trade_quality_score is used for ranking so a high confidence number alone does
not dominate selection.
"""

from typing import Dict

from config import REGIME_SETTINGS, SCORE_WEIGHTS, TRADE_QUALITY_WEIGHTS


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 84:
        return "A"
    if score >= 76:
        return "B+"
    if score >= 68:
        return "B"
    if score >= 58:
        return "C"
    return "D"


def _regime_alignment(regime: str) -> float:
    return {
        "STRONG_BULL": 92,
        "BULL": 82,
        "SIDEWAYS": 62,
        "WEAK_SIDEWAYS": 45,
        "BEAR": 28,
        "STRONG_BEAR": 3,
        "HIGH_VOLATILITY": 38,
        "TRANSITION": 48,
    }.get(regime, 50)


def _weighted_score(components: Dict[str, float], weights: Dict[str, float]) -> float:
    total_w = sum(max(0.0, float(w)) for w in weights.values()) or 1.0
    score = 0.0
    for key, weight in weights.items():
        score += _clamp(float(components.get(key, 50.0))) * max(0.0, float(weight))
    return score / total_w


def compute_score_components(
    trend_quality_score: float,
    momentum_quality_score: float,
    volume_participation_score: float,
    sector_strength_score: float,
    relative_strength_score: float,
    historical_edge_score: float,
    liquidity_tradability_score: float,
    event_news_risk_score: float,
    risk_reward_score: float,
    portfolio_fit_score: float,
    regime: str,
    correlation_penalty: float = 0.0,
    ai_severity: int = 0,
    black_swan: bool = False,
) -> Dict[str, object]:
    regime_alignment_score = _regime_alignment(regime)
    components = {
        "trend_quality_score": _clamp(trend_quality_score),
        "momentum_quality_score": _clamp(momentum_quality_score),
        "volume_participation_score": _clamp(volume_participation_score),
        "regime_alignment_score": _clamp(regime_alignment_score),
        "sector_strength_score": _clamp(sector_strength_score),
        "relative_strength_score": _clamp(relative_strength_score),
        "historical_edge_score": _clamp(historical_edge_score),
        "liquidity_tradability_score": _clamp(liquidity_tradability_score),
        "event_news_risk_score": _clamp(event_news_risk_score),
        "correlation_penalty": _clamp(correlation_penalty, 0, 40),
        "portfolio_fit_score": _clamp(portfolio_fit_score),
        "risk_reward_score": _clamp(risk_reward_score),
    }
    if black_swan:
        components["event_news_risk_score"] = 0.0
    base_conf = _weighted_score(components, SCORE_WEIGHTS)
    trade_quality_components = dict(components)
    trade_quality_components["entry_quality_score"] = _clamp((components["trend_quality_score"] * 0.35 + components["momentum_quality_score"] * 0.25 + components["volume_participation_score"] * 0.15 + components["risk_reward_score"] * 0.25))
    base_tq = _weighted_score(trade_quality_components, TRADE_QUALITY_WEIGHTS)

    severity_penalty = 0.0
    if ai_severity >= 90:
        severity_penalty = 45.0
    elif ai_severity >= 75:
        severity_penalty = 25.0
    elif ai_severity >= 60:
        severity_penalty = 12.0
    elif ai_severity >= 45:
        severity_penalty = 5.0

    multiplier = float(REGIME_SETTINGS.get(regime, REGIME_SETTINGS["TRANSITION"]).get("score_multiplier", 0.84))
    confidence = _clamp(base_conf * multiplier - severity_penalty - correlation_penalty)
    trade_quality = _clamp(base_tq - severity_penalty * 0.6 - correlation_penalty * 1.25)
    if black_swan:
        confidence = 0.0
        trade_quality = 0.0

    return {
        **components,
        "final_confidence": round(confidence, 2),
        "confidence": round(confidence, 2),
        "buy_confidence": round(confidence, 2),
        "trade_quality_score": round(trade_quality, 2),
        "confidence_grade": _grade(confidence),
        "severity_penalty": round(severity_penalty, 2),
        "score_multiplier": multiplier,
    }


def compute_buy_confidence(
    technical_score: float,
    elite_score: float,
    entry_score: float,
    news_score: float,
    rs_score: float,
    sector_score: float,
    regime: str,
    risk_reward_score: float = 50.0,
    liquidity_score: float = 50.0,
    ai_severity: int = 0,
    ai_sentiment: str = "Neutral",
    black_swan: bool = False,
    correlation_penalty: float = 0.0,
    portfolio_fit_score: float = 70.0,
) -> Dict[str, object]:
    # Backward-compatible API. Split technical into trend/momentum when callers
    # do not provide detailed components.
    return compute_score_components(
        trend_quality_score=technical_score,
        momentum_quality_score=entry_score,
        volume_participation_score=entry_score,
        sector_strength_score=sector_score,
        relative_strength_score=rs_score,
        historical_edge_score=elite_score,
        liquidity_tradability_score=liquidity_score,
        event_news_risk_score=news_score,
        risk_reward_score=risk_reward_score,
        portfolio_fit_score=portfolio_fit_score,
        regime=regime,
        correlation_penalty=correlation_penalty,
        ai_severity=ai_severity,
        black_swan=black_swan,
    )


def compute_confidence(*args, **kwargs) -> Dict[str, object]:
    return compute_buy_confidence(*args, **kwargs)


def compute_exit_risk_score(
    pnl_pct: float,
    below_stop: bool = False,
    below_ema20: bool = False,
    below_ema50: bool = False,
    sector_class: str = "NEUTRAL",
    rs_deteriorating: bool = False,
    market_regime: str = "TRANSITION",
    ai_severity: int = 0,
    black_swan: bool = False,
    trailing_stop_hit: bool = False,
    time_decay: bool = False,
) -> Dict[str, object]:
    if black_swan or below_stop or trailing_stop_hit:
        score = 100.0
    else:
        score = 0.0
        if below_ema20:
            score += 18
        if below_ema50:
            score += 25
        if sector_class == "WEAKENING":
            score += 15
        elif sector_class == "LAGGING":
            score += 25
        if rs_deteriorating:
            score += 15
        if market_regime in ("BEAR", "HIGH_VOLATILITY"):
            score += 15
        elif market_regime == "STRONG_BEAR":
            score += 35
        elif market_regime == "TRANSITION":
            score += 8
        if ai_severity >= 85:
            score += 35
        elif ai_severity >= 70:
            score += 20
        elif ai_severity >= 60:
            score += 10
        if time_decay:
            score += 12
        if pnl_pct < -3:
            score += 10
        score = _clamp(score)
    if score >= 85:
        action = "SELL"
    elif score >= 65:
        action = "REDUCE"
    elif score >= 48:
        action = "HOLD_CAUTION"
    else:
        action = "HOLD"
    return {"exit_risk_score": round(score, 2), "suggested_action": action}


def confidence_to_position_size(confidence: float, total_capital: float) -> float:
    if confidence >= 90:
        pct = 15
    elif confidence >= 84:
        pct = 12
    elif confidence >= 76:
        pct = 8
    elif confidence >= 68:
        pct = 5
    else:
        pct = 0
    return round(total_capital * pct / 100.0, 2)


def explain_confidence(symbol: str, result: Dict[str, object], technical: float, elite: float, entry: float, news: float, rs: float, sector: float, regime: str) -> str:
    strengths = []
    risks = []
    if technical >= 70:
        strengths.append("clean trend")
    if entry >= 70:
        strengths.append("good entry location")
    if rs >= 65:
        strengths.append("relative strength")
    if sector >= 65:
        strengths.append("sector support")
    if elite >= 60:
        strengths.append("historical edge")
    if news < 40:
        risks.append("news/event risk")
    if regime in ("BEAR", "STRONG_BEAR", "HIGH_VOLATILITY", "TRANSITION"):
        risks.append(f"{regime.lower()} regime")
    text = f"{symbol}: confidence {float(result.get('confidence', 0)):.1f}, trade quality {float(result.get('trade_quality_score', 0)):.1f}"
    if strengths:
        text += " | strengths: " + ", ".join(strengths)
    if risks:
        text += " | risks: " + ", ".join(risks)
    return text
