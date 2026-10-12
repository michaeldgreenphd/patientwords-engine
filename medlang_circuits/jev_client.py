"""Client and data types for TypeSafe AI's Jev classifier via OpenRouter.

OpenRouter Decisions API:
  POST https://openrouter.ai/api/alpha/decisions

Model:
  typesafe/jev-1.13 (or alias ~typesafe/jev-latest)

Jev is a non-generative, typed decision model. Instead of streaming free-form prose,
it evaluates structured questions over a given state context and returns:
- choice: categorized selection with probability distribution across criteria and confidence score
- noul: calibrated probability (0.0 to 1.0) of a condition being true
- score: continuous expected score across an ordered scale (criteria passed as ordered array of strings)

Conventions honored:
- No medical terms hardcoded in Python source (AGENTS.md).
- Strict typing, robust error handling, and mock support for offline testing.
- Distinguishes actual provider spend (`cost_usd`) from estimated list-price cost (`estimated_cost_usd`).
- Fails loud on malformed or null answers instead of silently dropping them.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Literal

OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
JEV_INPUT_PRICE_PER_M = 0.042  # $0.042 / million tokens list price
JEV_OUTPUT_PRICE_PER_M = 0.0   # $0 / million tokens list price


class JevError(Exception):
    """Base exception for Jev client errors."""


class JevApiError(JevError):
    """HTTP error returned by OpenRouter Decisions API."""

    def __init__(self, status_code: int, message: str, body: str | None = None):
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.body = body


class JevParseError(JevError):
    """Error raised when provider returns an unrecognized or malformed answer."""


@dataclass(frozen=True)
class ChoiceQuestion:
    instructions: str
    criteria: dict[str, str]
    type: Literal["choice"] = "choice"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "choice",
            "instructions": self.instructions,
            "criteria": self.criteria,
        }


@dataclass(frozen=True)
class NoulQuestion:
    instructions: str
    type: Literal["noul"] = "noul"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "noul",
            "instructions": self.instructions,
        }


@dataclass(frozen=True)
class ScoreQuestion:
    instructions: str
    criteria: list[str]
    type: Literal["score"] = "score"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "score",
            "instructions": self.instructions,
            "criteria": list(self.criteria),
        }


Question = ChoiceQuestion | NoulQuestion | ScoreQuestion


@dataclass(frozen=True)
class ChoiceAnswer:
    choice: str
    probabilities: dict[str, float]
    confidence: float
    type: Literal["choice"] = "choice"


@dataclass(frozen=True)
class NoulAnswer:
    noul: float
    type: Literal["noul"] = "noul"


@dataclass(frozen=True)
class ScoreAnswer:
    score: float
    probabilities: dict[str, float]
    confidence: float
    type: Literal["score"] = "score"


Answer = ChoiceAnswer | NoulAnswer | ScoreAnswer


@dataclass(frozen=True)
class JevUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float | None = None
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class JevResponse:
    id: str
    model: str
    answers: dict[str, Answer]
    usage: JevUsage
    raw: dict[str, Any] = field(default_factory=dict)


def build_decisions_payload(
    state: Any,
    questions: dict[str, Question],
    model: str = DEFAULT_JEV_MODEL,
) -> dict[str, Any]:
    """Assemble the OpenRouter Decisions request dictionary."""
    if not questions:
        raise ValueError("At least one question is required for a decisions request")
    q_dict = {qid: q.to_dict() for qid, q in questions.items()}
    return {
        "model": model,
        "state": state,
        "questions": q_dict,
    }


def parse_decisions_response(data: dict[str, Any], requested_questions: dict[str, Question] | None = None) -> JevResponse:
    """Parse raw OpenRouter Decisions JSON response into typed JevResponse.
    Raises JevParseError on malformed, null, or missing answers.
    """
    resp_id = str(data.get("id") or "")
    model = str(data.get("model") or "")
    answers_raw = data.get("answers")
    if not isinstance(answers_raw, dict):
        raise JevParseError(f"Decisions response missing 'answers' dict: {data}")

    parsed_answers: dict[str, Answer] = {}

    for qid, ans in answers_raw.items():
        if not isinstance(ans, dict):
            raise JevParseError(f"Malformed answer for question {qid!r}: expected dict, got {type(ans).__name__}")
        atype = ans.get("type")

        if atype == "choice" or "choice" in ans:
            probs = {str(k): float(v) for k, v in (ans.get("probabilities") or {}).items()}
            choice = str(ans.get("choice") or "")
            conf = float(ans.get("confidence") or 0.0)
            parsed_answers[qid] = ChoiceAnswer(
                choice=choice,
                probabilities=probs,
                confidence=conf,
            )
        elif atype == "noul" or "noul" in ans:
            if ans.get("noul") is None:
                raise JevParseError(f"Malformed noul answer for {qid!r}: 'noul' value missing")
            val = float(ans["noul"])
            parsed_answers[qid] = NoulAnswer(
                noul=val,
            )
        elif atype == "score" or "score" in ans:
            if ans.get("score") is None:
                raise JevParseError(f"Malformed score answer for {qid!r}: 'score' value missing")
            score = float(ans["score"])
            probs = {str(k): float(v) for k, v in (ans.get("probabilities") or {}).items()}
            conf = float(ans.get("confidence") or 0.0)
            parsed_answers[qid] = ScoreAnswer(
                score=score,
                probabilities=probs,
                confidence=conf,
            )
        else:
            raise JevParseError(f"Unrecognized answer format for question {qid!r}: {ans}")

    if requested_questions:
        missing = set(requested_questions) - set(parsed_answers)
        if missing:
            raise JevParseError(f"Decisions response omitted answers for requested questions: {sorted(missing)}")

    usage_raw = data.get("usage") or {}
    in_tok = int(usage_raw.get("input_tokens") or usage_raw.get("prompt_tokens") or 0)
    out_tok = int(usage_raw.get("output_tokens") or usage_raw.get("completion_tokens") or 0)
    
    # Cost tracking: actual provider spend vs list-price estimate
    cost_actual: float | None = float(usage_raw["cost"]) if "cost" in usage_raw and usage_raw["cost"] is not None else None
    est_cost = (in_tok * JEV_INPUT_PRICE_PER_M + out_tok * JEV_OUTPUT_PRICE_PER_M) / 1_000_000.0 if in_tok > 0 else 0.0

    return JevResponse(
        id=resp_id,
        model=model,
        answers=parsed_answers,
        usage=JevUsage(
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost_actual,
            estimated_cost_usd=est_cost,
        ),
        raw=data,
    )


class JevClient:
    """Client for TypeSafe AI Jev model on OpenRouter."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = OPENROUTER_DECISIONS_URL,
        timeout: float = 60.0,
        max_retries: int = 3,
        initial_backoff: float = 2.0,
    ):
        self.api_key = api_key or os.environ.get("OPENROUTER_API_KEY", "")
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff

    def decide(
        self,
        state: Any,
        questions: dict[str, Question],
        model: str = DEFAULT_JEV_MODEL,
    ) -> JevResponse:
        """Call OpenRouter Decisions API with retry backoff and return typed response."""
        if not self.api_key:
            raise JevError("OPENROUTER_API_KEY is not set or provided")

        payload = build_decisions_payload(state, questions, model=model)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            self.base_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "HTTP-Referer": "https://github.com/michaeldgreenphd/patientwords-engine",
                "X-Title": "patientwords-engine",
            },
            method="POST",
        )

        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    resp_bytes = response.read()
                    data = json.loads(resp_bytes.decode("utf-8"))
                    return parse_decisions_response(data, requested_questions=questions)
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                if e.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    wait = self.initial_backoff * (2 ** attempt)
                    time.sleep(wait)
                    continue
                raise JevApiError(e.code, e.reason, body=err_body) from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt < self.max_retries:
                    wait = self.initial_backoff * (2 ** attempt)
                    time.sleep(wait)
                    continue
                reason = getattr(e, "reason", str(e))
                raise JevError(f"Network error connecting to {self.base_url}: {reason}") from e
