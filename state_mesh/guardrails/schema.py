from __future__ import annotations

from typing import Any, Type

from pydantic import BaseModel, ValidationError

from state_mesh.guardrails.base import Guard, GuardResult
from state_mesh.core.context import Context


class SchemaGuard(Guard):
    def __init__(self, schema: Type[BaseModel]):
        self.schema = schema

    async def check(self, ctx: Context, data: Any) -> GuardResult:
        try:
            self.schema.model_validate(data)
            return GuardResult(passed=True, reason="")
        except ValidationError as e:
            return GuardResult(passed=False, reason=str(e))
