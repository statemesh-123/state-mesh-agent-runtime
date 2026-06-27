import sys
import pytest
import asyncio
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh" / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh" / "guardrails"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh"))
from pydantic import BaseModel
from context import Context
from step import Step, StepResult, Branch, RetryConfig, step


class DummyState(BaseModel):
    value: int = 0


def make_ctx() -> Context:
    return Context(state=DummyState())


# --- @step decorator ---

def test_step_decorator_no_args_wraps_into_step():
    @step
    async def my_fn(ctx): pass
    assert isinstance(my_fn, Step)
    assert my_fn.name == "my_fn"


def test_step_decorator_with_args_wraps_correctly():
    @step(timeout_seconds=30)
    async def my_fn(ctx): pass
    assert isinstance(my_fn, Step)
    assert my_fn.timeout_seconds == 30


# --- execute ---

@pytest.mark.asyncio
async def test_successful_step_returns_success():
    @step
    async def my_fn(ctx): return "ok"
    result = await my_fn.execute(make_ctx())
    assert result.status == "success"
    assert result.output == "ok"


@pytest.mark.asyncio
async def test_step_retries_and_succeeds_on_third_attempt():
    calls = {"n": 0}
    async def flaky(ctx):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("not yet")
        return "done"
    s = Step(fn=flaky, retry_config=RetryConfig(max_attempts=3, backoff_base=0, backoff_multiplier=0))
    result = await s.execute(make_ctx())
    assert result.status == "success"
    assert result.attempts == 3


@pytest.mark.asyncio
async def test_step_returns_failed_after_max_retries():
    async def always_fails(ctx):
        raise RuntimeError("boom")
    s = Step(fn=always_fails, retry_config=RetryConfig(max_attempts=3, backoff_base=0, backoff_multiplier=0))
    result = await s.execute(make_ctx())
    assert result.status == "failed"
    assert result.attempts == 3
    assert "boom" in result.error


@pytest.mark.asyncio
async def test_step_returns_timed_out():
    async def slow(ctx):
        await asyncio.sleep(5)
    s = Step(fn=slow, timeout_seconds=0.01)
    result = await s.execute(make_ctx())
    assert result.status == "timed_out"
    assert "timed out" in result.error


@pytest.mark.asyncio
async def test_step_branch_captured_in_output():
    ctx = make_ctx()
    async def branching(ctx):
        return Branch(to="next_step", context=ctx)
    s = Step(fn=branching)
    result = await s.execute(ctx)
    assert result.status == "success"
    assert isinstance(result.output, Branch)
    assert result.output.to == "next_step"


@pytest.mark.asyncio
async def test_step_name_set_on_context():
    async def my_fn(ctx):
        assert ctx._step_name == "my_fn"
    s = Step(fn=my_fn)
    await s.execute(make_ctx())


@pytest.mark.asyncio
async def test_flags_appear_in_step_result():
    async def flagging(ctx):
        ctx.emit_flag(flag_type="check", reason="test flag", severity="info")
    s = Step(fn=flagging)
    result = await s.execute(make_ctx())
    assert len(result.flags) == 1
    assert result.flags[0].flag_type == "check"
