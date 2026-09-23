from datetime import UTC, datetime
from uuid import UUID

import pytest
from paper_helper_messaging.envelope import (
    EnvelopeError,
    MessageActor,
    MessageEnvelope,
    MessageKind,
)


def _envelope(**overrides: object) -> MessageEnvelope:
    values: dict[str, object] = {
        "message_id": UUID("6cd58d29-a93b-41bc-bd4a-e2ac3360d30a"),
        "message_type": "knowledge.ingestion.requested",
        "message_kind": MessageKind.COMMAND,
        "schema_version": 1,
        "occurred_at": datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
        "producer": "knowledge-service",
        "correlation_id": UUID("b57a9b8f-2312-48f7-a360-19e40121dd91"),
        "causation_id": None,
        "workspace_id": UUID("a6a44285-99df-41c6-92af-b54fa61907c9"),
        "aggregate_type": "source",
        "aggregate_id": UUID("31fdbbd2-314f-4711-a147-fc0148a5d678"),
        "aggregate_version": 3,
        "actor": MessageActor(type="user", id="user-123"),
        "payload": {
            "source_id": "31fdbbd2-314f-4711-a147-fc0148a5d678",
            "object_key": "sources/example.pdf",
            "object_hash": "sha256:abc123",
            "pipeline_version": "2026-09-22",
        },
    }
    values.update(overrides)
    return MessageEnvelope(**values)  # type: ignore[arg-type]


def test_envelope_round_trips_through_wire_json() -> None:
    envelope = _envelope()

    decoded = MessageEnvelope.from_json(envelope.to_json())

    assert decoded == envelope
    assert decoded.routing_key == "knowledge.ingestion.requested.v1"


def test_envelope_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(EnvelopeError, match="timezone-aware"):
        _envelope(occurred_at=datetime(2026, 9, 22, 10, 0))


def test_envelope_rejects_unknown_wire_fields() -> None:
    value = _envelope().to_dict()
    value["access_token"] = "must-not-cross-the-boundary"

    with pytest.raises(EnvelopeError, match="missing or unknown"):
        MessageEnvelope.from_dict(value)


def test_aggregate_identity_is_all_or_nothing() -> None:
    with pytest.raises(EnvelopeError, match="both be set or null"):
        _envelope(aggregate_id=None)
