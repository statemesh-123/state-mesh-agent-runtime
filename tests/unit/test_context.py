import sys
from pathlib import Path
import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "state-mesh" / "core"))
from context import Context, ContextMutationError


class DummyState(BaseModel):
    value: int = 0


def make_ctx(**kwargs) -> Context:
    return Context(state=DummyState(), **kwargs)



def test_set_raises_on_duplicate_key():
    ctx = make_ctx()
    ctx.set("x", 1)
    with pytest.raises(ContextMutationError):
        ctx.set("x", 2)


def test_get_returns_default_when_missing():
    ctx = make_ctx()
    assert ctx.get("missing", "default") == "default"


def test_flags_returns_copy():
    ctx = make_ctx()
    ctx._set_current_step("step1")
    ctx.emit_flag(flag_type="test", reason="r")
    returned = ctx.flags
    returned.clear()
    assert len(ctx.flags) == 1


def test_emit_flag_correct_fields():
    ctx = make_ctx()
    ctx._set_current_step("validate")
    ctx.emit_flag(flag_type="missing_field", reason="field was null", severity="error", payload={"field": "name"})
    flag = ctx.flags[0]
    assert flag.step_name == "validate"
    assert flag.flag_type == "missing_field"
    assert flag.reason == "field was null"
    assert flag.severity == "error"
    assert flag.payload == {"field": "name"}


def test_replace_state_updates_state():
    ctx = make_ctx()
    ctx._replace_state(DummyState(value=99))
    assert ctx.state.value == 99


def test_auto_generates_run_id_and_trace_id():
    ctx = make_ctx()
    assert ctx.run_id is not None
    assert ctx.trace_id is not None
    assert ctx.run_id != ctx.trace_id


def test_uses_provided_run_id_and_trace_id():
    ctx = make_ctx(run_id="run-123", trace_id="trace-456")
    assert ctx.run_id == "run-123"
    assert ctx.trace_id == "trace-456"


def test_set_current_step_updates_correctly():
    ctx = make_ctx()
    ctx._set_current_step("my_step")
    assert ctx._step_name == "my_step"


def test_emit_flag_uses_step_name_automatically():
    ctx = make_ctx()
    ctx._set_current_step("auto_step")
    ctx.emit_flag(flag_type="check", reason="something")
    assert ctx.flags[0].step_name == "auto_step"
