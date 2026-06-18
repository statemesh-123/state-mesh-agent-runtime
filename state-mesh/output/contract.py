from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class OutputContract(BaseModel):
    model_config = {"arbitrary_types_allowed": True}
    target_schema: Any
    max_retries: int = 3
    retry_prompt_template: str = "The output did not match the expected schema. Please provide a valid output."
    fallback: Literal["raise", "return_partial", "return_none"] = "raise"
    parser_strategy: Literal["json", "xml", "markdown_block", "raw"] = "json"