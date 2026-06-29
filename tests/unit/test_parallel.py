import sys
import asyncio
import time
import pytest
from pathlib import Path
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state_mesh" / "core"))

from state_mesh.core.context import Context
from state_mesh.core.step import Step, RetryConfig
from state_mesh.core.parallel import Parallel


class DummyState(BaseModel):
    value: int = 0


def make_ctx() -> Context:
    ctx = Context(state=DummyState())
    ctx._set_current_step("test")
    return ctx


# --- all steps succeed ---

@pytest.mark.asyncio
async def test_all_steps_succeed_results_in_extras():
    async def s1(ctx): return "result_1"
    async def s2(ctx): return "result_2"

    p = Parallel(steps=[Step(fn=s1, name="s1"), Step(fn=s2, name="s2")])
    ctx = make_ctx()
    results = await p.execute(ctx)

    assert all(r.status == "success" for r in results)
    assert ctx.get("s1") == "result_1"
    assert ctx.get("s2") == "result_2"


@pytest.mark.asyncio
async def test_all_steps_succeed_returns_correct_count():
    async def s1(ctx): return 1
    async def s2(ctx): return 2
    async def s3(ctx): return 3

    p = Parallel(steps=[Step(fn=s1, name="s1"), Step(fn=s2, name="s2"), Step(fn=s3, name="s3")])
    results = await p.execute(make_ctx())
    assert len(results) == 3


# --- one step fails ---

@pytest.mark.asyncio
async def test_one_step_fails_all_results_returned():
    async def good(ctx): return "ok"
    async def bad(ctx): raise RuntimeError("boom")

    p = Parallel(steps=[
        Step(fn=good, name="good"),
        Step(fn=bad, name="bad", retry_config=RetryConfig(max_attempts=1)),
    ])
    ctx = make_ctx()
    results = await p.execute(ctx)

    assert len(results) == 2
    statuses = {r.step_name: r.status for r in results}
    assert statuses["good"] == "success"
    assert statuses["bad"] == "failed"


@pytest.mark.asyncio
async def test_failed_step_not_stored_in_extras():
    async def bad(ctx): raise RuntimeError("boom")

    p = Parallel(steps=[Step(fn=bad, name="bad", retry_config=RetryConfig(max_attempts=1))])
    ctx = make_ctx()
    await p.execute(ctx)

    assert ctx.get("bad") is None


# --- concurrent execution ---

@pytest.mark.asyncio
async def test_steps_run_concurrently():
    async def slow(ctx):
        await asyncio.sleep(0.1)
        return "done"

    p = Parallel(steps=[
        Step(fn=slow, name="s1"),
        Step(fn=slow, name="s2"),
        Step(fn=slow, name="s3"),
    ])

    start = time.monotonic()
    results = await p.execute(make_ctx())
    elapsed = time.monotonic() - start

    assert all(r.status == "success" for r in results)
    # if sequential this would take ~0.3s — concurrent should finish in ~0.1s
    assert elapsed < 0.25
