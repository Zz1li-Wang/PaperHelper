import json
from pathlib import Path

import jsonschema
from referencing import Registry, Resource

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EVENT_CONTRACTS = REPOSITORY_ROOT / "contracts" / "events" / "v1"


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    resources = []
    for path in EVENT_CONTRACTS.rglob("*.schema.json"):
        schema = _load(path)
        resources.append((str(schema["$id"]), Resource.from_contents(schema)))
    return Registry().with_resources(resources)


def test_all_event_contracts_are_valid_draft_2020_12_schemas() -> None:
    schemas = list(EVENT_CONTRACTS.rglob("*.schema.json"))
    assert schemas
    for path in schemas:
        jsonschema.Draft202012Validator.check_schema(_load(path))


def test_ingestion_requested_example_matches_contract() -> None:
    schema = _load(EVENT_CONTRACTS / "commands" / "knowledge.ingestion.requested.schema.json")
    message = {
        "message_id": "6cd58d29-a93b-41bc-bd4a-e2ac3360d30a",
        "message_type": "knowledge.ingestion.requested",
        "message_kind": "command",
        "schema_version": 1,
        "occurred_at": "2026-09-22T10:00:00Z",
        "producer": "knowledge-service",
        "correlation_id": "b57a9b8f-2312-48f7-a360-19e40121dd91",
        "causation_id": None,
        "workspace_id": "a6a44285-99df-41c6-92af-b54fa61907c9",
        "aggregate_type": "source",
        "aggregate_id": "31fdbbd2-314f-4711-a147-fc0148a5d678",
        "aggregate_version": 3,
        "actor": {"type": "user", "id": "user-123"},
        "payload": {
            "source_id": "31fdbbd2-314f-4711-a147-fc0148a5d678",
            "object_key": "sources/example.pdf",
            "object_hash": "sha256:abc123",
            "pipeline_version": "2026-09-22"
        }
    }

    jsonschema.Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=jsonschema.FormatChecker(),
    ).validate(message)
