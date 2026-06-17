from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from contract import OutputContract


class ContractViolationError(Exception):
    pass


@dataclass
class ParseResult:
    success: bool
    data: Any
    error: str | None = None


class Parser:
    async def parse(self, raw: str, contract: OutputContract) -> ParseResult:
        if contract.parser_strategy == "json":
            return self._parse_json(raw, contract)
        elif contract.parser_strategy == "xml":
            return ParseResult(success=False, data=None, error="XML parsing not yet implemented")
        elif contract.parser_strategy == "markdown_block":
            return ParseResult(success=False, data=None, error="Markdown block parsing not yet implemented")
        elif contract.parser_strategy == "raw":
            return ParseResult(success=True, data=raw.strip())

    def _parse_json(self, raw: str, contract: OutputContract) -> ParseResult:
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", raw, re.DOTALL)
        if not match:
            start = raw.find("{")
            arr_start = raw.find("[")
            if start == -1 and arr_start == -1:
                return ParseResult(success=False, data=None, error="No JSON found in response")
            if start == -1:
                start = arr_start
            elif arr_start != -1:
                start = min(start, arr_start)
            extracted = raw[start:]
        else:
            extracted = match.group(1)

        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError as e:
            return ParseResult(success=False, data=None, error=f"JSON decode error: {e}")

        try:
            validated = contract.target_schema(**parsed)
        except (ValidationError, TypeError) as e:
            return ParseResult(success=False, data=None, error=f"Schema validation error: {e}")

        return ParseResult(success=True, data=validated)
