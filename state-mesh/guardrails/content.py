from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from base import Guard, GuardResult
from core.context import Context

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
            #field -aware check
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
