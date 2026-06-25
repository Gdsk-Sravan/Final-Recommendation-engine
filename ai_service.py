"""
ai_service.py - Optional Grok/Groq-compatible AI service wrapper.

The trading engine remains deterministic. This wrapper only provides a safe
structured JSON second pass for explanations, news interpretation, and
borderline candidate review. If the API key is absent or the response is bad,
callers receive a deterministic fallback status.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

from config import (
    ENABLE_AI_SECOND_PASS,
    GROK_API_KEY,
    GROK_API_URL,
    GROK_MODEL,
    AI_TIMEOUT_SECONDS,
    AI_MAX_RETRIES,
)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except Exception:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


class AIService:
    def __init__(self) -> None:
        self.enabled = bool(ENABLE_AI_SECOND_PASS and GROK_API_KEY)
        self.api_key = GROK_API_KEY
        self.api_url = GROK_API_URL
        self.model = GROK_MODEL
        self.timeout = AI_TIMEOUT_SECONDS
        self.max_retries = AI_MAX_RETRIES

    def complete_json(self, system_prompt: str, payload: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "enabled": self.enabled,
            "model": self.model,
            "api_url": self.api_url,
            "ok": False,
            "error": "",
        }
        if not self.enabled:
            meta["error"] = "AI second pass disabled or API key missing"
            return None, meta

        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        last_error = ""
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = requests.post(self.api_url, headers=headers, json=body, timeout=self.timeout)
                if resp.status_code >= 400:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:400]}"
                    time.sleep(min(2 * attempt, 6))
                    continue
                raw = resp.json()
                content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
                parsed = extract_json_object(content)
                if parsed is None:
                    last_error = "model returned invalid JSON"
                    continue
                meta.update({"ok": True, "error": "", "attempt": attempt})
                return parsed, meta
            except Exception as exc:
                last_error = str(exc)
                time.sleep(min(2 * attempt, 6))
        meta["error"] = last_error or "unknown AI service failure"
        return None, meta
