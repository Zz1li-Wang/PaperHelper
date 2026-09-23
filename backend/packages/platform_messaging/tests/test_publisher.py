from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from paper_helper_messaging.envelope import MessageActor, MessageEnvelope, MessageKind
from paper_helper_messaging.publisher import (
    MAX_MESSAGE_BYTES,
    MessageTooLargeError,
    RabbitPublisher,
)
from paper_helper_messaging.topology import COMMAND_EXCHANGE


class FakeExchange:
    def __init__(self) -> None:
        self.published: list[tuple[Any, str, bool]] = []

    async def publish(self, message: Any, routing_key: str, *, mandatory: bool) -> bool:
        self.published.append((message, routing_key, mandatory))
        return True


class FakeChannel:
    def __init__(self) -> None:
        self.default_exchange = FakeExchange()


def _envelope(payload: dict[str, object] | None = None) -> MessageEnvelope:
    return MessageEnvelope(
        message_id=UUID("6cd58d29-a93b-41bc-bd4a-e2ac3360d30a"),
        message_type="agent.run.requested",
        message_kind=MessageKind.COMMAND,
        schema_version=1,
        occurred_at=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
        producer="interaction-service",
        correlation_id=UUID("b57a9b8f-2312-48f7-a360-19e40121dd91"),
        causation_id=None,
        workspace_id=None,
        aggregate_type="agent_run",
        aggregate_id=UUID("31fdbbd2-314f-4711-a147-fc0148a5d678"),
        aggregate_version=1,
        actor=MessageActor(type="user", id="user-123"),
        payload=payload or {"run_id": "31fdbbd2-314f-4711-a147-fc0148a5d678"},
    )


async def test_publish_uses_confirmed_persistent_message_properties() -> None:
    exchange = FakeExchange()
    publisher = RabbitPublisher(FakeChannel(), {COMMAND_EXCHANGE: exchange})

    await publisher.publish(_envelope(), headers={"traceparent": "00-trace-parent"})

    message, routing_key, mandatory = exchange.published[0]
    assert routing_key == "agent.run.requested.v1"
    assert mandatory is True
    assert message.delivery_mode.value == 2
    assert message.message_id == "6cd58d29-a93b-41bc-bd4a-e2ac3360d30a"
    assert message.headers["traceparent"] == "00-trace-parent"
    assert message.headers["x-paper-helper-schema-version"] == 1


async def test_publish_rejects_oversized_message_before_broker_call() -> None:
    exchange = FakeExchange()
    publisher = RabbitPublisher(FakeChannel(), {COMMAND_EXCHANGE: exchange})

    with pytest.raises(MessageTooLargeError):
        await publisher.publish(_envelope({"body": "x" * MAX_MESSAGE_BYTES}))

    assert exchange.published == []
