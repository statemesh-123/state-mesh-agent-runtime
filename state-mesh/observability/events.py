from opentelemetry import trace

from core.context import Context


class EventEmitter:
    def pipeline_started(self, ctx: Context, pipeline_name: str) -> None:
        trace.get_current_span().add_event(
            "pipeline.started",
            attributes={"pipeline_name": pipeline_name, "run_id": ctx.run_id, "trace_id": ctx.trace_id},
        )

    def pipeline_finished(self, ctx: Context, pipeline_name: str, duration_ms: float, status: str) -> None:
        trace.get_current_span().add_event(
            "pipeline.finished",
            attributes={"pipeline_name": pipeline_name, "run_id": ctx.run_id, "duration_ms": duration_ms, "status": status},
        )

    def step_started(self, ctx: Context, step_name: str) -> None:
        trace.get_current_span().add_event(
            "step.started",
            attributes={"step_name": step_name, "run_id": ctx.run_id},
        )

    def step_finished(self, ctx: Context, step_name: str, duration_ms: float, status: str) -> None:
        trace.get_current_span().add_event(
            "step.finished",
            attributes={"step_name": step_name, "run_id": ctx.run_id, "duration_ms": duration_ms, "status": status},
        )
