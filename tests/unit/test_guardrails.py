import pytest
from typing import Any
from unittest.mock import MagicMock, patch
from pydantic import BaseModel

from state_mesh.core.context import Context
from state_mesh.guardrails.base import Guard, GuardResult
from state_mesh.guardrails.schema import SchemaGuard
from state_mesh.guardrails.content import PIIGuard, ConfidenceGuard
from state_mesh.guardrails.runner import run_guards


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


# --- confidence guard ---

@pytest.mark.asyncio
async def test_confidence_guard_passes_above_threshold():
    class Output(BaseModel):
        confidence: float
        text: str

    guard = ConfidenceGuard(min_confidence=0.7)
    result = await guard.check(make_ctx(), Output(confidence=0.9, text="hello"))
    assert result.passed is True


@pytest.mark.asyncio
async def test_confidence_guard_blocks_below_threshold():
    class Output(BaseModel):
        confidence: float
        text: str

    guard = ConfidenceGuard(min_confidence=0.7)
    result = await guard.check(make_ctx(), Output(confidence=0.4, text="hello"))
    assert result.passed is False
    assert "0.40" in result.reason
    assert "0.70" in result.reason


@pytest.mark.asyncio
async def test_confidence_guard_missing_field_fails():
    class Output(BaseModel):
        text: str

    guard = ConfidenceGuard(min_confidence=0.5)
    result = await guard.check(make_ctx(), Output(text="hello"))
    assert result.passed is False
    assert "missing" in result.reason.lower()


@pytest.mark.asyncio
async def test_confidence_guard_works_with_dict():
    guard = ConfidenceGuard(min_confidence=0.5)
    result = await guard.check(make_ctx(), {"confidence": 0.8, "text": "hello"})
    assert result.passed is True


@pytest.mark.asyncio
async def test_confidence_guard_custom_field():
    class Output(BaseModel):
        score: float

    guard = ConfidenceGuard(min_confidence=0.5, field="score")
    result = await guard.check(make_ctx(), Output(score=0.3))
    assert result.passed is False


@pytest.mark.asyncio
async def test_confidence_guard_warn_severity():
    guard = ConfidenceGuard(min_confidence=0.9, severity="warn")
    result = await guard.check(make_ctx(), {"confidence": 0.5})
    assert result.passed is False
    assert result.severity == "warn"


# --- toxicity guard ---

def make_toxicity_guard(scores: dict, **kwargs):
    mock_model = MagicMock()
    mock_model.predict = MagicMock(return_value=scores)
    with patch("state_mesh.guardrails.content.Detoxify", return_value=mock_model):
        from state_mesh.guardrails.content import ToxicityGuard
        guard = ToxicityGuard(**kwargs)
        guard._model = mock_model
    return guard


@pytest.mark.asyncio
async def test_toxicity_guard_passes_clean_text():
    guard = make_toxicity_guard({"toxicity": 0.01, "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0, "insult": 0.0, "identity_attack": 0.0})
    result = await guard.check(make_ctx(), "hello, how are you?")
    assert result.passed is True


@pytest.mark.asyncio
async def test_toxicity_guard_blocks_toxic_text():
    guard = make_toxicity_guard({"toxicity": 0.95, "severe_toxicity": 0.1, "obscene": 0.0, "threat": 0.0, "insult": 0.0, "identity_attack": 0.0})
    result = await guard.check(make_ctx(), "some toxic text")
    assert result.passed is False
    assert "toxicity" in result.reason


@pytest.mark.asyncio
async def test_toxicity_guard_respects_threshold():
    guard = make_toxicity_guard({"toxicity": 0.6, "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0, "insult": 0.0, "identity_attack": 0.0}, threshold=0.8)
    result = await guard.check(make_ctx(), "borderline text")
    assert result.passed is True  # 0.6 < 0.8 threshold so passes


@pytest.mark.asyncio
async def test_toxicity_guard_warn_severity():
    guard = make_toxicity_guard({"toxicity": 0.9, "severe_toxicity": 0.0, "obscene": 0.0, "threat": 0.0, "insult": 0.0, "identity_attack": 0.0}, severity="warn")
    result = await guard.check(make_ctx(), "toxic text")
    assert result.passed is False
    assert result.severity == "warn"


@pytest.mark.asyncio
async def test_toxicity_guard_checks_only_specified_categories():
    # only checking threat — toxicity is high but not checked
    guard = make_toxicity_guard({"toxicity": 0.95, "threat": 0.1}, categories=["threat"])
    result = await guard.check(make_ctx(), "some text")
    assert result.passed is True
