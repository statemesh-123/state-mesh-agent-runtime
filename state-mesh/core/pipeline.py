from __future__ import annotations
import time
from typing import Any, Literal, Optional
from context import Context, Flag
from step import StepResult, Step,Branch
from pydantic import BaseModel

class PipelineResult(BaseModel):
    output:Any
    run_id:str
    trace_id:str
    duration_ms:float
    status: Literal["success","failed","timed_out","guarded"]
    step_results:list[StepResult]
    flags:list[Flag]

class Pipeline:
    def __init__(self,  steps:list[Step], name:str=None,state_backend:Any=None):
        self.name = name
        self.steps = steps
        self.state_backend = state_backend
        self._step_map:dict[str,Step]={s.name:s for s in steps}

    async def run(self, ctx:Context) -> PipelineResult:
        # This is where the main logic for running the pipeline will go, including executing steps in order, handling branching, and collecting results and flags.
        step_results = []
        start = time.monotonic()
        for step in self.steps:
            result = await step.execute(ctx)
            step_results.append(result)
            if result.status != "success":
                duration = (time.monotonic() - start) * 1000
                return PipelineResult(output=result.output, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=result.status, step_results=step_results, flags=ctx.flags)
            if isinstance(result.output, Branch):
                branch=result.output
                ctx=branch.context
                if branch.to not in self._step_map:
                    raise ValueError(f"Branch target to {branch.to} not found in pipeline steps")
                result = await self._step_map[branch.to].execute(ctx)
                step_results.append(result)
                continue
            ctx._replace_state(result.output)
        duration = (time.monotonic() - start) * 1000
        return PipelineResult(output=step_results[-1].output if step_results else None, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status="success", step_results=step_results, flags=ctx.flags)