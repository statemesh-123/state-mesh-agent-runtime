import pytest
from pydantic import BaseModel

from state_mesh.output.contract import OutputContract
from state_mesh.output.parser import Parser, ParseResult
from state_mesh.output.retry import run_with_retry
from state_mesh.output.parser import ContractViolationError


class User(BaseModel):
    name: str


def make_contract(**kwargs) -> OutputContract:
    return OutputContract(target_schema=User, **kwargs)


# --- contract ---

def test_contract_defaults():
    contract = make_contract()
    assert contract.max_retries == 3
    assert contract.parser_strategy == "json"
    assert contract.fallback == "raise"


def test_contract_schema_is_set():
    contract = make_contract()
    assert contract.target_schema is User


def test_contract_invalid_parser_strategy_rejected():
    with pytest.raises(Exception):
        OutputContract(target_schema=User, parser_strategy="toml")


def test_contract_invalid_fallback_rejected():
    with pytest.raises(Exception):
        OutputContract(target_schema=User, fallback="ignore")


# --- parser ---

@pytest.mark.asyncio
async def test_parser_valid_json():
    parser = Parser()
    contract = make_contract()
    result = await parser.parse('{"name": "state-mesh"}', contract)
    assert result.success is True
    assert result.data.name == "state-mesh"


@pytest.mark.asyncio
async def test_parser_markdown_block():
    parser = Parser()
    contract = make_contract()
    result = await parser.parse('```json\n{"name": "state-mesh"}\n```', contract)
    assert result.success is True
    assert result.data.name == "state-mesh"


@pytest.mark.asyncio
async def test_parser_invalid_json():
    parser = Parser()
    contract = make_contract()
    result = await parser.parse("not json at all", contract)
    assert result.success is False
    assert "No JSON found" in result.error


@pytest.mark.asyncio
async def test_parser_schema_validation_failure():
    parser = Parser()
    contract = make_contract()
    result = await parser.parse('{"wrong_field": 123}', contract)
    assert result.success is False
    assert "validation" in result.error.lower()


@pytest.mark.asyncio
async def test_parser_extra_text_around_json():
    parser = Parser()
    contract = make_contract()
    result = await parser.parse('Here is the result: {"name": "state-mesh"} hope that helps!', contract)
    assert result.success is True
    assert result.data.name == "state-mesh"


@pytest.mark.asyncio
async def test_parser_raw_strategy_returns_raw_string():
    parser = Parser()
    contract = make_contract(parser_strategy="raw")
    result = await parser.parse("  hello world  ", contract)
    assert result.success is True
    assert result.data == "hello world"


@pytest.mark.asyncio
async def test_parser_xml_valid():
    parser = Parser()
    contract = make_contract(parser_strategy="xml")
    result = await parser.parse("<user><name>state-mesh</name></user>", contract)
    assert result.success is True
    assert result.data.name == "state-mesh"


@pytest.mark.asyncio
async def test_parser_xml_invalid_xml():
    parser = Parser()
    contract = make_contract(parser_strategy="xml")
    result = await parser.parse("not xml at all", contract)
    assert result.success is False
    assert "XML parse error" in result.error


@pytest.mark.asyncio
async def test_parser_xml_schema_validation_failure():
    parser = Parser()
    contract = make_contract(parser_strategy="xml")
    result = await parser.parse("<user><wrong_field>123</wrong_field></user>", contract)
    assert result.success is False
    assert "validation" in result.error.lower()


@pytest.mark.asyncio
async def test_parser_markdown_block_valid():
    parser = Parser()
    contract = make_contract(parser_strategy="markdown_block")
    result = await parser.parse('```json\n{"name": "State mesh"}\n```', contract)
    assert result.success is True
    assert result.data.name == "State mesh"


@pytest.mark.asyncio
async def test_parser_markdown_block_without_json_label():
    parser = Parser()
    contract = make_contract(parser_strategy="markdown_block")
    result = await parser.parse('```\n{"name": "state-mesh"}\n```', contract)
    assert result.success is True
    assert result.data.name == "state-mesh"


@pytest.mark.asyncio
async def test_parser_markdown_block_no_fence_fails():
    parser = Parser()
    contract = make_contract(parser_strategy="markdown_block")
    result = await parser.parse('{"name": "state-mesh"}', contract)
    assert result.success is False
    assert "No markdown JSON block found" in result.error


@pytest.mark.asyncio
async def test_parser_markdown_block_schema_validation_failure():
    parser = Parser()
    contract = make_contract(parser_strategy="markdown_block")
    result = await parser.parse('```json\n{"wrong_field": 123}\n```', contract)
    assert result.success is False
    assert "validation" in result.error.lower()


# --- retry ---

@pytest.mark.asyncio
async def test_retry_success_on_first_try():
    async def mock_llm(prompt: str) -> str:
        return '{"name": "state-mesh"}'

    result = await run_with_retry(mock_llm, "prompt", make_contract(), Parser())
    assert result.name == "state-mesh"


@pytest.mark.asyncio
async def test_retry_success_after_failures():
    calls = {"count": 0}

    async def flaky_llm(prompt: str) -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            return "bad response"
        return '{"name": "state-mesh"}'

    result = await run_with_retry(flaky_llm, "prompt", make_contract(max_retries=3), Parser())
    assert result.name == "state-mesh"
    assert calls["count"] == 3


@pytest.mark.asyncio
async def test_retry_raises_on_exhaustion():
    async def bad_llm(prompt: str) -> str:
        return "bad response"

    with pytest.raises(ContractViolationError):
        await run_with_retry(bad_llm, "prompt", make_contract(max_retries=3, fallback="raise"), Parser())


@pytest.mark.asyncio
async def test_retry_returns_none_on_exhaustion():
    async def bad_llm(prompt: str) -> str:
        return "bad response"

    result = await run_with_retry(bad_llm, "prompt", make_contract(max_retries=2, fallback="return_none"), Parser())
    assert result is None


@pytest.mark.asyncio
async def test_retry_corrective_prompt_includes_error_and_schema():
    prompts = []

    async def capturing_llm(prompt: str) -> str:
        prompts.append(prompt)
        if len(prompts) == 1:
            return "bad response"
        return '{"name": "state-mesh"}'

    await run_with_retry(capturing_llm, "initial prompt", make_contract(max_retries=3), Parser())
    assert len(prompts) == 2
    assert "Error" in prompts[1]
    assert "name" in prompts[1]


@pytest.mark.asyncio
async def test_retry_return_partial_returns_none():
    async def bad_llm(prompt: str) -> str:
        return "bad response"

    result = await run_with_retry(bad_llm, "prompt", make_contract(max_retries=2, fallback="return_partial"), Parser())
    assert result is None
