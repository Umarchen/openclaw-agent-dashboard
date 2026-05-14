"""JSON Schema validation wrapper (jsonschema)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import jsonschema
from jsonschema import Draft202012Validator


@dataclass
class ValidationResult:
    is_valid: bool
    errors: List[str] = field(default_factory=list)

    @property
    def error_message(self) -> str:
        return "; ".join(self.errors) if self.errors else ""


class SchemaValidator:
    """Validate dict data against a JSON Schema dict."""

    def __init__(self, schema: Dict[str, Any], strict: bool = True):
        self.schema = schema
        self.strict = strict
        self._validator = Draft202012Validator(schema)

    def validate(self, data: Any) -> ValidationResult:
        """线程安全：校验结果仅通过返回值给出，实例上不保留最后一次错误（避免并发覆盖）。"""
        errors: List[str] = []
        if not isinstance(data, (dict, list)) and self.schema.get("type") == "object":
            errors.append("expected object")
            return ValidationResult(False, errors)
        try:
            self._validator.validate(data)
            return ValidationResult(True, [])
        except jsonschema.ValidationError as e:
            errors.append(e.message)
            return ValidationResult(False, errors)

    def get_error_details(self) -> Dict[str, Any]:
        """兼容旧接口；共享校验器实例时不代表「最后一次校验」。请使用 validate() 的返回值。"""
        return {"errors": []}
