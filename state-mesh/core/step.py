from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, Literal, List, Optional, Callable
from context import Context, Flag
from pydantic import BaseModel,Field
import time

class StepResult(BaseModel):
    status: Literal["success","failed","timed_out","guarded"]
    step_name:str
    output:Any
    duration_ms:float
    attempts:int
    flags:list[Flag]=Field(default_factory=list)
    error:Optional[str]=None

@dataclass
class RetryConfig:
    max_attempts:int=3
    backoff_base:float=1.0
    backoff_multiplier:float=2.0

class Branch:
    def __init__(self, to:str, context: Context):
        self.to = to
        self.context = context


class Step:
    def __init__(self, fn: Callable, name:str |None=None, retry_config:RetryConfig=None, 
                 timeout_seconds:Optional[float]=None, guard_before:list=None, guard_after:list=None, 
                 tags:Optional[List[str]]=None):
        self.name = name or fn.__name__
        self.fn = fn
        self.retry_config = retry_config or RetryConfig()
        self.timeout_seconds = timeout_seconds
        self.guard_before = guard_before or []
        self.guard_after = guard_after or []
        self.tags = tags or []


async def execute(self, ctx:Context) -> StepResult:
    # This is where the main logic for executing the step will go, including handling retries, timeouts, guards, and collecting flags.
    
    start = time.monotonic()
    last_error = None
    ctx._set_current_step(self.name)
    for attempt in range(1, self.retry_config.max_attempts + 1):
        try:
            if self.timeout_seconds:
                result = await asyncio.wait_for(self.fn(ctx), timeout=self.timeout_seconds)
            else:
                result = await self.fn(ctx)

            elapsed = (time.monotonic() - start) * 1000

            if isinstance(result, Branch):
                return StepResult(status="success", flags=ctx.flags, step_name=self.name, output=result, duration_ms=elapsed, attempts=attempt)

            return StepResult(status="success", flags=ctx.flags, step_name=self.name, output=result, duration_ms=elapsed, attempts=attempt)
        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start) * 1000
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
    
    elapsed = (time.monotonic() - start) * 1000
    return StepResult(status="failed", flags=ctx.flags, step_name=self.name, output=None, duration_ms=elapsed, attempts=self.retry_config.max_attempts, error=str(last_error))