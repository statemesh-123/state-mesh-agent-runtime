from __future__ import annotations

from typing import Any, Awaitable, Callable

from state_mesh.output.contract import OutputContract
from state_mesh.output.parser import ContractViolationError, Parser


async def run_with_retry(
    llm_fn: Callable[[str], Awaitable[str]],
    initial_prompt: str,
    contract: OutputContract,
    parser: Parser,
) -> Any:
    prompt = initial_prompt
    last_error: str | None = None

    for _ in range(contract.max_retries):
        raw = await llm_fn(prompt)
        result = await parser.parse(raw, contract)

        if result.success:
            return result.data

        last_error = result.error
        schema_json = contract.target_schema.model_json_schema()
        prompt = (
            f"{contract.retry_prompt_template}\n\n"
            f"Error: {last_error}\n\n"
            f"Expected schema: {schema_json}\n\n"
            f"Previous response:\n{raw}"
        )

    if contract.fallback == "raise":
        raise ContractViolationError(
            f"All {contract.max_retries} retries exhausted. Last error: {last_error}"
        )
    return None
