from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from state_mesh.output.contract import OutputContract


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
            return self._parse_xml(raw, contract)
        elif contract.parser_strategy == "markdown_block":
            return self._parse_markdown_block(raw, contract)
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
            try:
                parsed, _ = json.JSONDecoder().raw_decode(raw, start)
            except json.JSONDecodeError as e:
                return ParseResult(success=False, data=None, error=f"JSON decode error: {e}")
        else:
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError as e:
                return ParseResult(success=False, data=None, error=f"JSON decode error: {e}")

        try:
            validated = contract.target_schema(**parsed)
        except (ValidationError, TypeError) as e:
            return ParseResult(success=False, data=None, error=f"Schema validation error: {e}")

        return ParseResult(success=True, data=validated)

    def _parse_markdown_block(self, raw: str, contract: OutputContract) -> ParseResult:
        match = re.search(r"```(?:json)?\s*({.*?})\s*```", raw, re.DOTALL)
        if not match:
            return ParseResult(success=False, data=None, error="No markdown JSON block found in response")
        try:
            parsed = json.loads(match.group(1))
        except json.JSONDecodeError as e:
            return ParseResult(success=False, data=None, error=f"JSON decode error: {e}")
        try:
            validated = contract.target_schema(**parsed)
        except (ValidationError, TypeError) as e:
            return ParseResult(success=False, data=None, error=f"Schema validation error: {e}")
        return ParseResult(success=True, data=validated)

    def _parse_xml(self, raw: str, contract: OutputContract) -> ParseResult:
        try:
            root = ET.fromstring(raw.strip())
        except ET.ParseError as e:
            return ParseResult(success=False, data=None, error=f"XML parse error: {e}")

        data = {child.tag: child.text for child in root}

        try:
            validated = contract.target_schema(**data)
        except (Exception,) as e:
            return ParseResult(success=False, data=None, error=f"Schema validation error: {e}")

        return ParseResult(success=True, data=validated)
