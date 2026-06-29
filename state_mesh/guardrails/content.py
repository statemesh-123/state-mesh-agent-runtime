from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from state_mesh.guardrails.base import Guard, GuardResult
from state_mesh.core.context import Context

try:
    from detoxify import Detoxify
except ImportError:  # pragma: no cover - optional dependency
    class Detoxify:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError("detoxify is required to use ToxicityGuard")

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


class PIIGuard(Guard):
    def __init__(
        self,
        sensitive_fields: list[str] | None = None,
        ignore_patterns: list[str] | None = None,
        severity: Literal["warn", "block"] = "block",
    ):
        self.sensitive_fields = sensitive_fields
        self.ignore_patterns = [re.compile(p) for p in (ignore_patterns or [])]
        self.severity = severity

    async def check(self, ctx: Context, data: Any) -> GuardResult:
        if self.sensitive_fields and isinstance(data, BaseModel):
            candidates = {
                f: str(v)
                for f, v in data.model_dump().items()
                if f in self.sensitive_fields
            }
        else:
            candidates = {"data": data if isinstance(data, str) else str(data)}

        for field, value in candidates.items():
            if any(p.search(value) for p in self.ignore_patterns):
                continue
            if EMAIL_PATTERN.search(value):
                return GuardResult(passed=False, severity=self.severity, reason=f"Email detected in field '{field}'")

        return GuardResult(passed=True, reason="No PII detected")


class ConfidenceGuard(Guard):
    def __init__(self, min_confidence: float, field: str = "confidence", severity: Literal["warn", "block"] = "block"):
        self.min_confidence = min_confidence
        self.field = field
        self.severity = severity

    async def check(self, ctx: Context, data: Any) -> GuardResult:
        if isinstance(data, BaseModel):
            score = data.model_dump().get(self.field)
        elif isinstance(data, dict):
            score = data.get(self.field)
        else:
            return GuardResult(passed=False, severity=self.severity, reason=f"Cannot extract confidence field '{self.field}' from {type(data).__name__}")

        if score is None:
            return GuardResult(passed=False, severity=self.severity, reason=f"Confidence field '{self.field}' missing")

        if score < self.min_confidence:
            return GuardResult(passed=False, severity=self.severity, reason=f"Confidence {score:.2f} below threshold {self.min_confidence:.2f}")

        return GuardResult(passed=True, reason=f"Confidence {score:.2f} meets threshold")


class ToxicityGuard(Guard):
    def __init__(self, threshold: float = 0.5, categories: list[str] | None = None, severity: Literal["warn", "block"] = "block"):
        self._model = Detoxify("original")
        self.threshold = threshold
        self.categories = categories or ["toxicity", "severe_toxicity", "obscene", "threat", "insult", "identity_attack"]
        self.severity = severity

    async def check(self, ctx: Context, data: Any) -> GuardResult:
        text = data if isinstance(data, str) else str(data)
        scores = self._model.predict(text)

        for category in self.categories:
            score = scores.get(category, 0)
            if score >= self.threshold:
                return GuardResult(passed=False, severity=self.severity, reason=f"Toxicity detected — {category}: {score:.2f} (threshold: {self.threshold:.2f})")

        return GuardResult(passed=True, reason="No toxic content detected")

