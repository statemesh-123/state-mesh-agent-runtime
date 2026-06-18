import sys
import pytest
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh" / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh" / "guardrails"))

from pydantic import BaseModel
from context import Context

from base import Guard, GuardResult
from schema import SchemaGuard
from content import PIIGuard
from runner import run_guards


# --- helpers ---

class DummyState(BaseModel):
    value: int = 0

class User(BaseModel):
    name: str
    age: int

def make_ctx() -> Context:
    ctx = Context(state=DummyState())
    ctx._set_current_step("test")
    return ctx


# --- base ---

def test_guard_result_passed():
    result = GuardResult(passed=True, reason="ok")
    assert result.passed is True
    assert result.severity == "warn"


def test_guard_result_block_severity():
    result = GuardResult(passed=False, reason="blocked", severity="block")
    assert result.severity == "block"
    assert result.passed is False


def test_guard_is_abstract():
    with pytest.raises(TypeError):
        Guard()


# --- schema guard ---

@pytest.mark.asyncio
async def test_schema_guard_passes_valid_data():
    guard = SchemaGuard(User)
    result = await guard.check(make_ctx(), {"name": "Prabha", "age": 22})
    assert result.passed is True


@pytest.mark.asyncio
async def test_schema_guard_fails_missing_field():
    guard = SchemaGuard(User)
    result = await guard.check(make_ctx(), {"name": "Prabha"})
    assert result.passed is False
    assert result.reason != ""


@pytest.mark.asyncio
async def test_schema_guard_fails_wrong_type():
    guard = SchemaGuard(User)
    result = await guard.check(make_ctx(), {"name": "Prabha", "age": "not_an_int"})
    # pydantic coerces str -> int so check with a non-coercible value
    result2 = await guard.check(make_ctx(), {"name": "Prabha", "age": "abc"})
    assert result2.passed is False


# --- pii guard ---

@pytest.mark.asyncio
async def test_pii_guard_detects_email_in_string():
    guard = PIIGuard()
    result = await guard.check(make_ctx(), "contact me at user@example.com please")
    assert result.passed is False
    assert result.severity == "block"


@pytest.mark.asyncio
async def test_pii_guard_passes_clean_string():
    guard = PIIGuard()
    result = await guard.check(make_ctx(), "hello world no pii here")
    assert result.passed is True


@pytest.mark.asyncio
async def test_pii_guard_detects_email_in_sensitive_field():
    class Profile(BaseModel):
        email: str
        bio: str

    guard = PIIGuard(sensitive_fields=["email"])
    data = Profile(email="user@example.com", bio="safe bio")
    result = await guard.check(make_ctx(), data)
    assert result.passed is False
    assert "email" in result.reason


@pytest.mark.asyncio
async def test_pii_guard_ignores_non_sensitive_field():
    class Profile(BaseModel):
        email: str
        bio: str

    guard = PIIGuard(sensitive_fields=["bio"])
    data = Profile(email="user@example.com", bio="safe bio")
    result = await guard.check(make_ctx(), data)
    assert result.passed is True


@pytest.mark.asyncio
async def test_pii_guard_warn_severity():
    guard = PIIGuard(severity="warn")
    result = await guard.check(make_ctx(), "user@example.com")
    assert result.passed is False
    assert result.severity == "warn"


@pytest.mark.asyncio
async def test_pii_guard_ignore_pattern_skips_match():
    guard = PIIGuard(ignore_patterns=[r"example\.com"])
    result = await guard.check(make_ctx(), "user@example.com")
    assert result.passed is True


# --- runner ---

@pytest.mark.asyncio
async def test_runner_all_pass():
    guard = SchemaGuard(User)
    ctx = make_ctx()
    result = await run_guards([guard], ctx, {"name": "Prabha", "age": 25})
    assert result.passed is True


@pytest.mark.asyncio
async def test_runner_blocks_on_first_block_guard():
    class BlockingGuard(Guard):
        async def check(self, ctx: Context, data: Any) -> GuardResult:
            return GuardResult(passed=False, reason="blocked", severity="block")

    class NeverReachedGuard(Guard):
        async def check(self, ctx: Context, data: Any) -> GuardResult:
            raise AssertionError("should not be reached")

    ctx = make_ctx()
    result = await run_guards([BlockingGuard(), NeverReachedGuard()], ctx, "data")
    assert result.passed is False
    assert result.reason == "blocked"


@pytest.mark.asyncio
async def test_runner_warn_emits_flag_and_continues():
    class WarnGuard(Guard):
        async def check(self, ctx: Context, data: Any) -> GuardResult:
            return GuardResult(passed=False, reason="suspicious", severity="warn")

    ctx = make_ctx()
    result = await run_guards([WarnGuard(), SchemaGuard(User)], ctx, {"name": "Prabha", "age": 25})
    assert result.passed is True
    assert len(ctx.flags) == 1
    assert ctx.flags[0].reason == "suspicious"


@pytest.mark.asyncio
async def test_runner_empty_guards_passes():
    ctx = make_ctx()
    result = await run_guards([], ctx, "anything")
    assert result.passed is True


@pytest.mark.asyncio
async def test_runner_multiple_warns_emit_multiple_flags():
    class WarnGuard(Guard):
        def __init__(self, reason: str):
            self.reason = reason
        async def check(self, ctx: Context, data: Any) -> GuardResult:
            return GuardResult(passed=False, reason=self.reason, severity="warn")

    ctx = make_ctx()
    await run_guards([WarnGuard("first"), WarnGuard("second")], ctx, "data")
    assert len(ctx.flags) == 2
    assert ctx.flags[0].reason == "first"
    assert ctx.flags[1].reason == "second"
