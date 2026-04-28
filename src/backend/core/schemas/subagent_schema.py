"""JSON Schema for subagents/runs.json root object."""

subagent_runs_root_schema: dict = {
    "$id": "https://openclaw/schemas/subagent-runs/v1",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "version": {"type": ["integer", "number"]},
        "runs": {"type": "object", "additionalProperties": True},
    },
}

subagent_run_record_schema: dict = {
    "$id": "https://openclaw/schemas/subagent-run-record/v1",
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "childSessionKey": {"type": "string"},
        "requesterSessionKey": {"type": "string"},
        "startedAt": {"type": ["integer", "number"]},
        "endedAt": {},
    },
}
