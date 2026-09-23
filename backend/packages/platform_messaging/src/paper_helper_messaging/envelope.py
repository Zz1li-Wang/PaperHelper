"""Language-neutral message envelope representation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID, uuid4

_MESSAGE_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z][a-z0-9_-]*)+$")


class EnvelopeError(ValueError):
    """Raised when an envelope cannot be constructed or decoded."""


class MessageKind(StrEnum):
    """Wire-level distinction between an instruction and an observed fact."""

    COMMAND = "command"
    EVENT = "event"


@dataclass(frozen=True, slots=True)
class MessageActor:
    """Minimal identity snapshot propagated with an asynchronous message."""

    type: str
    id: str

    def __post_init__(self) -> None:
        if self.type not in {"user", "service", "system"}:
            raise EnvelopeError(f"unsupported actor type: {self.type}")
        if not self.id:
            raise EnvelopeError("actor id must not be empty")

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        if not isinstance(value, dict) or set(value) != {"type", "id"}:
            raise EnvelopeError("actor must contain exactly type and id")
        actor_type = value["type"]
        actor_id = value["id"]
        if not isinstance(actor_type, str) or not isinstance(actor_id, str):
            raise EnvelopeError("actor type and id must be strings")
        return cls(type=actor_type, id=actor_id)


@dataclass(frozen=True, slots=True)
class MessageEnvelope:
    """Stable metadata shared by every command and event payload."""

    message_id: UUID
    message_type: str
    message_kind: MessageKind
    schema_version: int
    occurred_at: datetime
    producer: str
    correlation_id: UUID
    causation_id: UUID | None
    workspace_id: UUID | None
    aggregate_type: str | None
    aggregate_id: UUID | None
    aggregate_version: int | None
    actor: MessageActor
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not _MESSAGE_TYPE_PATTERN.fullmatch(self.message_type):
            raise EnvelopeError(
                "message_type must contain at least two lowercase dot-separated segments"
            )
        if self.schema_version < 1:
            raise EnvelopeError("schema_version must be at least 1")
        if self.occurred_at.utcoffset() is None:
            raise EnvelopeError("occurred_at must be timezone-aware")
        if not self.producer:
            raise EnvelopeError("producer must not be empty")
        if (self.aggregate_type is None) != (self.aggregate_id is None):
            raise EnvelopeError("aggregate_type and aggregate_id must either both be set or null")
        if self.aggregate_version is not None and self.aggregate_version < 0:
            raise EnvelopeError("aggregate_version must not be negative")
        if not isinstance(self.payload, dict):
            raise EnvelopeError("payload must be a JSON object")

    @classmethod
    def new(
        cls,
        *,
        message_type: str,
        message_kind: MessageKind,
        producer: str,
        actor: MessageActor,
        payload: dict[str, Any],
        correlation_id: UUID | None = None,
        causation_id: UUID | None = None,
        workspace_id: UUID | None = None,
        aggregate_type: str | None = None,
        aggregate_id: UUID | None = None,
        aggregate_version: int | None = None,
        schema_version: int = 1,
        occurred_at: datetime | None = None,
    ) -> Self:
        return cls(
            message_id=uuid4(),
            message_type=message_type,
            message_kind=message_kind,
            schema_version=schema_version,
            occurred_at=occurred_at or datetime.now(UTC),
            producer=producer,
            correlation_id=correlation_id or uuid4(),
            causation_id=causation_id,
            workspace_id=workspace_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            actor=actor,
            payload=dict(payload),
        )

    @property
    def routing_key(self) -> str:
        return f"{self.message_type}.v{self.schema_version}"

    def to_dict(self) -> dict[str, Any]:
        occurred_at = self.occurred_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        return {
            "message_id": str(self.message_id),
            "message_type": self.message_type,
            "message_kind": self.message_kind.value,
            "schema_version": self.schema_version,
            "occurred_at": occurred_at,
            "producer": self.producer,
            "correlation_id": str(self.correlation_id),
            "causation_id": str(self.causation_id) if self.causation_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": str(self.aggregate_id) if self.aggregate_id else None,
            "aggregate_version": self.aggregate_version,
            "actor": self.actor.to_dict(),
            "payload": self.payload,
        }

    def to_json(self) -> bytes:
        try:
            encoded = json.dumps(
                self.to_dict(),
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except (TypeError, ValueError) as exc:
            raise EnvelopeError("payload must be JSON serializable") from exc
        return encoded.encode("utf-8")

    @classmethod
    def from_json(cls, body: bytes) -> Self:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EnvelopeError("message body must be a UTF-8 JSON object") from exc
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: object) -> Self:
        expected = {
            "message_id",
            "message_type",
            "message_kind",
            "schema_version",
            "occurred_at",
            "producer",
            "correlation_id",
            "causation_id",
            "workspace_id",
            "aggregate_type",
            "aggregate_id",
            "aggregate_version",
            "actor",
            "payload",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise EnvelopeError("message envelope has missing or unknown fields")

        try:
            occurred_at_raw = value["occurred_at"]
            if not isinstance(occurred_at_raw, str):
                raise TypeError
            occurred_at = datetime.fromisoformat(occurred_at_raw.replace("Z", "+00:00"))
            message_type = value["message_type"]
            producer = value["producer"]
            schema_version = value["schema_version"]
            payload = value["payload"]
            aggregate_type = value["aggregate_type"]
            aggregate_version = value["aggregate_version"]
            if not isinstance(message_type, str) or not isinstance(producer, str):
                raise TypeError
            if not isinstance(schema_version, int) or isinstance(schema_version, bool):
                raise TypeError
            if not isinstance(payload, dict):
                raise TypeError
            if aggregate_type is not None and not isinstance(aggregate_type, str):
                raise TypeError
            if aggregate_version is not None and (
                not isinstance(aggregate_version, int) or isinstance(aggregate_version, bool)
            ):
                raise TypeError
            return cls(
                message_id=UUID(str(value["message_id"])),
                message_type=message_type,
                message_kind=MessageKind(value["message_kind"]),
                schema_version=schema_version,
                occurred_at=occurred_at,
                producer=producer,
                correlation_id=UUID(str(value["correlation_id"])),
                causation_id=_optional_uuid(value["causation_id"]),
                workspace_id=_optional_uuid(value["workspace_id"]),
                aggregate_type=aggregate_type,
                aggregate_id=_optional_uuid(value["aggregate_id"]),
                aggregate_version=aggregate_version,
                actor=MessageActor.from_dict(value["actor"]),
                payload=dict(payload),
            )
        except (TypeError, ValueError) as exc:
            if isinstance(exc, EnvelopeError):
                raise
            raise EnvelopeError("message envelope contains invalid field values") from exc


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else UUID(str(value))
