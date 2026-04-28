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
        self._last_errors: List[str] = []

    def validate(self, data: Any) -> ValidationResult:
        self._last_errors = []
        if not isinstance(data, (dict, list)) and self.schema.get("type") == "object":
            self._last_errors.append("expected object")
            return ValidationResult(False, list(self._last_errors))
        try:
            self._validator.validate(data)
            return ValidationResult(True, [])
        except jsonschema.ValidationError as e:
            self._last_errors.append(e.message)
            return ValidationResult(False, list(self._last_errors))

    def get_error_details(self) -> Dict[str, Any]:
        return {"errors": list(self._last_errors)}
