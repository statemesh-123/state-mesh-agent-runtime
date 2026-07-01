from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Literal, Optional, Callable

from pydantic import BaseModel, Field

from state_mesh.core.context import Context, Flag
from state_mesh.guardrails.runner import run_guards
from state_mesh.output.retry import run_with_retry
from state_mesh.output.parser import Parser
from state_mesh.output.contract import OutputContract


class StepResult(BaseModel):
    status: Literal["success", "failed", "timed_out", "guarded"]
    step_name: str
    output: Any
    duration_ms: float
    attempts: int
    flags: list[Flag] = Field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RetryConfig:
    max_attempts: int = 3
    backoff_base: float = 1.0
    backoff_multiplier: float = 2.0


class Branch:
    def __init__(self, to: str, context: Context):
        self.to = to
        self.context = context


class Step:
    def __init__(self, fn: Callable, name: str | None = None, retry_config: RetryConfig = None,
                 timeout_seconds: Optional[float] = None, guard_before: list = None, guard_after: list = None,
                 tags: Optional[list[str]] = None, output_contract: Optional[OutputContract] = None):
        self.name = name or fn.__name__
        self.fn = fn
        self.retry_config = retry_config or RetryConfig()
        self.timeout_seconds = timeout_seconds
        self.guard_before = guard_before or []
        self.guard_after = guard_after or []
        self.tags = tags or []
        self.output_contract = output_contract

    async def execute(self, ctx: Context, prompt: str | None = None) -> StepResult:
        start = time.perf_counter()
        last_error = None
        ctx._set_current_step(self.name)

        if self.guard_before:
            guard_result = await run_guards(self.guard_before, ctx, ctx.state)
            if not guard_result.passed:
                elapsed = (time.perf_counter() - start) * 1000
                return StepResult(status="guarded", flags=ctx.flags, step_name=self.name, output=None, duration_ms=elapsed, attempts=0, error=guard_result.reason)

        for attempt in range(1, self.retry_config.max_attempts + 1):
            try:
                if self.output_contract is not None:
                    coro = run_with_retry(self.fn, prompt, self.output_contract, Parser())
                    if self.timeout_seconds:
                        result = await asyncio.wait_for(coro, timeout=self.timeout_seconds)
                    else:
                        result = await coro
                elif self.timeout_seconds:
                    result = await asyncio.wait_for(self.fn(ctx), timeout=self.timeout_seconds)
                else:
                    result = await self.fn(ctx)

                if self.guard_after:
                    guard_result = await run_guards(self.guard_after, ctx, result)
                    if not guard_result.passed:
                        elapsed = (time.perf_counter() - start) * 1000
                        return StepResult(status="guarded", flags=ctx.flags, step_name=self.name, output=None, duration_ms=elapsed, attempts=attempt, error=guard_result.reason)

                elapsed = (time.perf_counter() - start) * 1000

                if isinstance(result, Branch):
                    return StepResult(status="success", flags=ctx.flags, step_name=self.name, output=result, duration_ms=elapsed, attempts=attempt)

                return StepResult(status="success", flags=ctx.flags, step_name=self.name, output=result, duration_ms=elapsed, attempts=attempt)
            except asyncio.TimeoutError:
                elapsed = (time.perf_counter() - start) * 1000
                return StepResult(
                    status="timed_out",
                    flags=ctx.flags,
                    step_name=self.name,
                    output=None,
                    duration_ms=elapsed,
                    attempts=attempt,
                    error=f"Step timed out after {self.timeout_seconds} seconds"
                )
            except Exception as e:
                last_error = e
                if attempt < self.retry_config.max_attempts:
                    wait = self.retry_config.backoff_base * (self.retry_config.backoff_multiplier ** (attempt - 1))
                    await asyncio.sleep(wait)
                continue

        elapsed = (time.perf_counter() - start) * 1000
        return StepResult(status="failed", flags=ctx.flags, step_name=self.name, output=None, duration_ms=elapsed, attempts=self.retry_config.max_attempts, error=str(last_error))


def step(fn=None, *, name=None, timeout_seconds=None, retry_config=None, guard_before=None, guard_after=None, tags=None, output_contract=None):
    if fn is not None:
        return Step(fn=fn)
    def wrap(f):
        return Step(fn=f, name=name, timeout_seconds=timeout_seconds, retry_config=retry_config, guard_before=guard_before, guard_after=guard_after, tags=tags, output_contract=output_contract)
    return wrap
