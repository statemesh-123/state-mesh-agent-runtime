from __future__ import annotations

import time
from typing import Any, Literal

from pydantic import BaseModel

from state_mesh.core.context import Context, Flag
from state_mesh.core.step import StepResult, Step, Branch
from state_mesh.core.parallel import Parallel
from state_mesh.observability.events import EventEmitter
from state_mesh.observability.tracer import get_tracer
from state_mesh.observability.flags import attach_flags_to_span
from state_mesh.mcp.bus import MCPBus


class PipelineResult(BaseModel):
    output: Any
    run_id: str
    trace_id: str
    duration_ms: float
    status: Literal["success", "failed", "timed_out", "guarded"]
    step_results: list[StepResult]
    flags: list[Flag]


class Pipeline:
    def __init__(self, steps: list[Step], name: str = None, state_backend: Any = None, mcp_servers: list[str] | None = None):
        self.name = name
        self.steps = steps
        self.state_backend = state_backend
        self.mcp_servers = mcp_servers
        self._step_map: dict[str, Step] = {s.name: s for s in steps}
        self._emitter = EventEmitter()

    async def run(self, ctx: Context) -> PipelineResult:
        step_results = []
        start = time.perf_counter()

        bus = None
        if self.mcp_servers:
            bus = MCPBus(self.mcp_servers)
            await bus.start()
            ctx._tools = bus

        try:
            tracer = get_tracer()
            with tracer.start_as_current_span("pipeline.run") as pipeline_span:
                pipeline_span.set_attribute("pipeline.name", self.name or "unnamed")
                pipeline_span.set_attribute("run_id", ctx.run_id)
                pipeline_span.set_attribute("trace_id", ctx.trace_id)

                self._emitter.pipeline_started(ctx, self.name)

                for step in self.steps:
                    if isinstance(step, Parallel):
                        parallel_results = await step.execute(ctx)
                        step_results.extend(parallel_results)
                        failed = next((r for r in parallel_results if isinstance(r, BaseException) or r.status != "success"), None)
                        if failed:
                            duration = (time.perf_counter() - start) * 1000
                            status = failed.status if isinstance(failed, StepResult) else "failed"
                            self._emitter.pipeline_finished(ctx, self.name, duration, status)
                            return PipelineResult(output=None, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=status, step_results=step_results, flags=ctx.flags)
                        continue

                    self._emitter.step_started(ctx, step.name)
                    with tracer.start_as_current_span(f"step.{step.name}") as step_span:
                        step_span.set_attribute("step.name", step.name)
                        step_span.set_attribute("run_id", ctx.run_id)
                        result = await step.execute(ctx)
                        step_span.set_attribute("step.status", result.status)
                        step_span.set_attribute("step.attempts", result.attempts)
                        step_span.set_attribute("step.duration_ms", result.duration_ms)
                        attach_flags_to_span(result.flags)

                    self._emitter.step_finished(ctx, step.name, result.duration_ms, result.status)
                    step_results.append(result)

                    if result.status != "success":
                        duration = (time.perf_counter() - start) * 1000
                        self._emitter.pipeline_finished(ctx, self.name, duration, result.status)
                        return PipelineResult(output=result.output, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=result.status, step_results=step_results, flags=ctx.flags)

                    if isinstance(result.output, Branch):
                        branch = result.output
                        ctx = branch.context
                        if branch.to not in self._step_map:
                            raise ValueError(f"Branch target to {branch.to} not found in pipeline steps")
                        self._emitter.step_started(ctx, branch.to)
                        with tracer.start_as_current_span(f"step.{branch.to}") as step_span:
                            step_span.set_attribute("step.name", branch.to)
                            step_span.set_attribute("run_id", ctx.run_id)
                            result = await self._step_map[branch.to].execute(ctx)
                            step_span.set_attribute("step.status", result.status)
                            step_span.set_attribute("step.attempts", result.attempts)
                            step_span.set_attribute("step.duration_ms", result.duration_ms)
                            attach_flags_to_span(result.flags)

                        self._emitter.step_finished(ctx, branch.to, result.duration_ms, result.status)
                        step_results.append(result)
                        if result.status != "success":
                            duration = (time.perf_counter() - start) * 1000
                            self._emitter.pipeline_finished(ctx, self.name, duration, result.status)
                            return PipelineResult(output=result.output, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status=result.status, step_results=step_results, flags=ctx.flags)
                        continue

                    ctx._replace_state(result.output)
                    if self.state_backend:
                        await self.state_backend.save(ctx.run_id, ctx.state)

                duration = (time.perf_counter() - start) * 1000
                self._emitter.pipeline_finished(ctx, self.name, duration, "success")
                if self.state_backend:
                    await self.state_backend.delete(ctx.run_id)
                return PipelineResult(output=step_results[-1].output if step_results else None, run_id=ctx.run_id, trace_id=ctx.trace_id, duration_ms=duration, status="success", step_results=step_results, flags=ctx.flags)
        finally:
            if bus:
                await bus.stop()
