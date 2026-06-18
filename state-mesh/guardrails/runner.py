from __future__ import annotations

from typing import Any

from base import Guard, GuardResult
from core.context import Context


async def run_guards(guards: list[Guard], ctx: Context, data: Any) -> GuardResult:
    for guard in guards:
        result = await guard.check(ctx, data)

        if not result.passed:
            if result.severity == "block":
                return result

            if result.severity == "warn":
                ctx.emit_flag(flag_type="guard_warn", reason=result.reason, severity="warn")

    return GuardResult(passed=True, reason="all guards passed")
