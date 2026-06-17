from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar, Literal, List
from dataclasses import dataclass

from pydantic import BaseModel,Field


@dataclass
class OutputContract:
    target_schema: type[BaseModel]
    max_retries: int = 3
    retry_prompt_template: str = "The output did not match the expected schema. Please provide a valid output."
    fallback : Literal["raise","return_partial","return_none"] = "raise"
    parser_strategy: Literal["json", "xml", "markdown_block", "raw"] = "json"