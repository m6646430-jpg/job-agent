"""OpenRouter client with model fallback chain, daily budget, and JSON-mode helpers."""

import json
import os
import re
import sqlite3
import time
from datetime import date
from pathlib import Path

import requests

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "jobs.db"


class BudgetExceeded(Exception):
    pass


class LLM:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not self.api_key:
            raise SystemExit("Set OPENROUTER_API_KEY in your environment (.env).")
        self.models = cfg["models"]
        self.base_url = cfg["base_url"].rstrip("/")
        self.max_per_day = int(cfg.get("max_requests_per_day", 48))
        self.min_gap = float(cfg.get("min_seconds_between_calls", 4))
        self._last_call = 0.0
        self._db = sqlite3.connect(DB_PATH)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS llm_usage (day TEXT PRIMARY KEY, calls INTEGER)"
        )
        self._db.commit()

    # -- budget -------------------------------------------------------------
    def _calls_today(self) -> int:
        row = self._db.execute(
            "SELECT calls FROM llm_usage WHERE day=?", (date.today().isoformat(),)
        ).fetchone()
        return row[0] if row else 0

    def _record_call(self):
        self._db.execute(
            "INSERT INTO llm_usage(day, calls) VALUES(?,1) "
            "ON CONFLICT(day) DO UPDATE SET calls=calls+1",
            (date.today().isoformat(),),
        )
        self._db.commit()

    def remaining_budget(self) -> int:
        return max(0, self.max_per_day - self._calls_today())

    # -- calls --------------------------------------------------------------
    def chat(self, system: str, user: str, json_mode: bool = False) -> str:
        if self.remaining_budget() <= 0:
            raise BudgetExceeded(f"Daily LLM budget ({self.max_per_day}) exhausted.")
        gap = time.time() - self._last_call
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)

        errors = []
        for model in self.models:
            body = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.3,
            }
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            try:
                r = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": "https://github.com/m6646430-jpg/job-agent",
                        "X-Title": "job-agent",
                    },
                    json=body,
                    timeout=120,
                )
                self._last_call = time.time()
                if r.status_code == 429:
                    errors.append(f"{model}: rate limited")
                    time.sleep(10)
                    continue
                r.raise_for_status()
                data = r.json()
                if "error" in data:
                    errors.append(f"{model}: {data['error']}")
                    continue
                self._record_call()
                content = data["choices"][0]["message"].get("content")
                if not content or not content.strip():
                    # Some free models return an empty answer: try the next one.
                    errors.append(f"{model}: empty answer")
                    continue
                return content
            except requests.RequestException as e:
                errors.append(f"{model}: {e}")
                continue
        raise RuntimeError("All models in the fallback chain failed:\n" + "\n".join(errors))

    def chat_json(self, system: str, user: str) -> dict:
        """Chat expecting a JSON object back; tolerates markdown fences."""
        text = self.chat(system + " Respond with a single JSON object only.", user, json_mode=True)
        text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError(f"Model did not return JSON: {text[:200]}")
        return json.loads(text[start : end + 1])
