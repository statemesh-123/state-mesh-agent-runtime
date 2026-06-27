from __future__ import annotations
import sys
import time
from pathlib import Path
from typing import Any, Literal, Optional
from context import Context, Flag
from step import StepResult, Step, Branch
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "observability"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from events import EventEmitter

class PipelineResult(BaseModel):
    output:Any
    run_id:str
    trace_id:str
    duration_ms:float
    status: Literal["success","failed","timed_out","guarded"]
    step_results:list[StepResult]
    flags:list[Flag]

class Pipeline:
    def __init__(self, steps: list[Step], name: str = None, state_backend: Any = None):
        self.name = name
        self.steps = steps
        self.state_backend = state_backend
        self._step_map: dict[str, Step] = {s.name: s for s in steps}
        self._emitter = EventEmitter()

    async def run(self, ctx: Context) -> PipelineResult:
        step_results = []
        start = time.monotonic()

        self._emitter.pipeline_started(ctx, self.name)

        for step in self.steps:
            self._emitter.step_started(ctx, step.name)
            result = await step.execute(ctx)
            self._emitter.step_finished(ctx, step.name, result.duration_ms, result.status)
            step_results.append(result)

            if result.status != "success":
                duration = (time.monotonic() - start) * 1000
                self._emitter.pipeline_finished(ctx, self.name, duration, result.status)
                return PipelineResult(output=result.output, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=result.status, step_results=step_results, flags=ctx.flags)

            if isinstance(result.output, Branch):
                branch = result.output
                ctx = branch.context
                if branch.to not in self._step_map:
                    raise ValueError(f"Branch target to {branch.to} not found in pipeline steps")
                self._emitter.step_started(ctx, branch.to)
                result = await self._step_map[branch.to].execute(ctx)
                self._emitter.step_finished(ctx, branch.to, result.duration_ms, result.status)
                step_results.append(result)
                if result.status != "success":
                    duration = (time.monotonic() - start) * 1000
                    self._emitter.pipeline_finished(ctx, self.name, duration, result.status)
                    return PipelineResult(output=result.output, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=result.status, step_results=step_results, flags=ctx.flags)
                continue

            ctx._replace_state(result.output)

        duration = (time.monotonic() - start) * 1000
        self._emitter.pipeline_finished(ctx, self.name, duration, "success")
        return PipelineResult(output=step_results[-1].output if step_results else None, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status="success", step_results=step_results, flags=ctx.flags)