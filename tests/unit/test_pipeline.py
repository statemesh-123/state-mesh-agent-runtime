import sys
import asyncio
import pytest
from pathlib import Path
from pydantic import BaseModel
from state_mesh.core.context import Context
from state_mesh.core.step import Step, Branch, RetryConfig
from state_mesh.core.pipeline import Pipeline, PipelineResult


class DummyState(BaseModel):
    value: int = 0


def make_ctx(**kwargs) -> Context:
    return Context(state=DummyState(), **kwargs)


# --- single step success ---

@pytest.mark.asyncio
async def test_single_step_success():
    async def fn(ctx): return DummyState(value=1)
    p = Pipeline(steps=[Step(fn=fn, name="s1")])
    ctx = make_ctx(run_id="run-1")
    result = await p.run(ctx)
    assert result.status == "success"
    assert result.output == DummyState(value=1)
    assert result.run_id == "run-1"
    assert len(result.step_results) == 1


# --- multi-step state threading ---

@pytest.mark.asyncio
async def test_multi_step_state_threads_correctly():
    async def add1(ctx): return DummyState(value=ctx.state.value + 1)
    async def add2(ctx): return DummyState(value=ctx.state.value + 2)
    p = Pipeline(steps=[Step(fn=add1, name="s1"), Step(fn=add2, name="s2")])
    result = await p.run(make_ctx())
    assert result.status == "success"
    assert result.output == DummyState(value=3)
    assert len(result.step_results) == 2


# --- early stop on failure ---

@pytest.mark.asyncio
async def test_pipeline_stops_on_failure():
    ran = []
    async def fails(ctx): raise RuntimeError("boom")
    async def should_not_run(ctx): ran.append(True)
    s1 = Step(fn=fails, name="s1", retry_config=RetryConfig(max_attempts=1))
    s2 = Step(fn=should_not_run, name="s2")
    result = await Pipeline(steps=[s1, s2]).run(make_ctx())
    assert result.status == "failed"
    assert ran == []


# --- timeout ---

@pytest.mark.asyncio
async def test_pipeline_returns_timed_out():
    async def slow(ctx): await asyncio.sleep(5)
    s = Step(fn=slow, name="s1", timeout_seconds=0.01)
    result = await Pipeline(steps=[s]).run(make_ctx())
    assert result.status == "timed_out"


# --- guarded ---

@pytest.mark.asyncio
async def test_pipeline_returns_guarded():
    async def guarded_fn(ctx): return "guarded"
    s = Step(fn=guarded_fn, name="s1")
    # Simulate a guarded result by patching execute directly
    original_execute = s.execute
    async def mock_execute(ctx):
        from state_mesh.core.step import StepResult
        return StepResult(status="guarded", step_name="s1", output=None, duration_ms=0, attempts=1)
    s.execute = mock_execute
    result = await Pipeline(steps=[s]).run(make_ctx())
    assert result.status == "guarded"


# --- branching: valid target ---

@pytest.mark.asyncio
async def test_branch_to_valid_step():
    async def router(ctx):
        return Branch(to="target", context=ctx)
    async def target(ctx):
        return DummyState(value=99)
    p = Pipeline(steps=[Step(fn=router, name="router"), Step(fn=target, name="target")])
    result = await p.run(make_ctx())
    assert result.status == "success"
    assert result.output == DummyState(value=99)


# --- branching: unknown target raises ValueError ---

@pytest.mark.asyncio
async def test_branch_to_unknown_step_raises():
    async def router(ctx):
        return Branch(to="nonexistent", context=ctx)
    p = Pipeline(steps=[Step(fn=router, name="router")])
    with pytest.raises(ValueError, match="nonexistent"):
        await p.run(make_ctx())


# --- flags aggregated ---

@pytest.mark.asyncio
async def test_flags_aggregated_from_all_steps():
    async def s1(ctx):
        ctx.emit_flag(flag_type="t1", reason="r1")
        return DummyState()
    async def s2(ctx):
        ctx.emit_flag(flag_type="t2", reason="r2")
        return DummyState()
    p = Pipeline(steps=[Step(fn=s1, name="s1"), Step(fn=s2, name="s2")])
    result = await p.run(make_ctx())
    assert len(result.flags) == 2
    assert {f.flag_type for f in result.flags} == {"t1", "t2"}


# --- duration_ms > 0 ---

@pytest.mark.asyncio
async def test_duration_ms_greater_than_zero():
    async def fn(ctx):
        await asyncio.sleep(0.01)
        return DummyState()
    result = await Pipeline(steps=[Step(fn=fn, name="s1")]).run(make_ctx())
    assert result.duration_ms > 0
