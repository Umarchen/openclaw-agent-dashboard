"""JSON Schema fragments for session JSONL lines and sessions.json index."""

# sessions.json 根对象：宽松，兼容 OpenClaw 多版本（仅约束为 object）
sessions_index_schema: dict = {
    "$id": "https://openclaw/schemas/sessions-index/v1",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "version": {},
        "schema": {},
        "entries": {"type": "object", "additionalProperties": True},
    },
}

# Line envelope: {"type": "message", "message": {...}, ... }
session_message_schema: dict = {
    "$id": "https://openclaw/schemas/session-message/v1",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "role": {"type": "string"},
        "content": {},
        "timestamp": {"type": ["integer", "number"]},
        "stopReason": {"type": "string"},
        "errorMessage": {"type": "string"},
    },
    "required": ["role"],
}

session_envelope_schema: dict = {
    "$id": "https://openclaw/schemas/session-envelope/v1",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "type": {"type": "string"},
        "message": {"type": "object", "additionalProperties": True},
        "timestamp": {},
    },
    "required": ["type"],
}
