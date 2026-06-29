from __future__ import annotations

import asyncio

from state_mesh.core.context import Context
from state_mesh.core.step import Step, StepResult


class Parallel:
    def __init__(self, steps: list[Step], name: str = "parallel"):
        self.name = name
        self.steps = steps

    async def execute(self, ctx: Context) -> list[StepResult]:
        results: list[StepResult] = list(
            await asyncio.gather(*[step.execute(ctx) for step in self.steps], return_exceptions=True)
        )

        for step, result in zip(self.steps, results):
            if not isinstance(result, BaseException) and result.status == "success":
                ctx.set(step.name, result.output)

        return results
