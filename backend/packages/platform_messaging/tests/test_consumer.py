from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from paper_helper_messaging.consumer import MessageConsumer, PermanentMessageError
from paper_helper_messaging.envelope import MessageActor, MessageEnvelope, MessageKind
from paper_helper_messaging.topology import COMMAND_EXCHANGE, SubscriptionSpec


class FakeIncomingMessage:
    def __init__(
        self,
        envelope: MessageEnvelope,
        *,
        headers: dict[str, Any] | None = None,
        routing_key: str | None = None,
    ) -> None:
        self.body = envelope.to_json()
        self.headers = headers or {}
        self.routing_key = routing_key or envelope.routing_key
        self.acked = False
        self.rejected = False

    async def ack(self) -> None:
        self.acked = True

    async def reject(self, *, requeue: bool) -> None:
        assert requeue is False
        self.rejected = True


class FakePublisher:
    def __init__(self) -> None:
        self.retries: list[tuple[MessageEnvelope, str, dict[str, object]]] = []

    async def publish_to_queue(
        self,
        envelope: MessageEnvelope,
        queue_name: str,
        *,
        headers: dict[str, object],
    ) -> None:
        self.retries.append((envelope, queue_name, headers))


def _envelope() -> MessageEnvelope:
    return MessageEnvelope(
        message_id=UUID("6cd58d29-a93b-41bc-bd4a-e2ac3360d30a"),
        message_type="knowledge.ingestion.requested",
        message_kind=MessageKind.COMMAND,
        schema_version=1,
        occurred_at=datetime(2026, 9, 22, 10, 0, tzinfo=UTC),
        producer="knowledge-service",
        correlation_id=UUID("b57a9b8f-2312-48f7-a360-19e40121dd91"),
        causation_id=None,
        workspace_id=None,
        aggregate_type="source",
        aggregate_id=UUID("31fdbbd2-314f-4711-a147-fc0148a5d678"),
        aggregate_version=1,
        actor=MessageActor(type="system", id="knowledge-service"),
        payload={"source_id": "31fdbbd2-314f-4711-a147-fc0148a5d678"},
    )


def _spec() -> SubscriptionSpec:
    return SubscriptionSpec(
        queue_name="paper_helper.knowledge.ingestion_worker",
        exchange_name=COMMAND_EXCHANGE,
        routing_keys=("knowledge.ingestion.requested.v1",),
        retry_delays_seconds=(10, 60),
    )


async def test_successful_handler_is_acknowledged() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        return None

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(_envelope())

    await consumer.handle(incoming)

    assert incoming.acked is True
    assert incoming.rejected is False


async def test_handler_failure_is_confirmed_to_retry_queue_before_ack() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        raise TimeoutError("temporary dependency failure")

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(_envelope())

    await consumer.handle(incoming)

    _, queue_name, headers = publisher.retries[0]
    assert queue_name == "paper_helper.knowledge.ingestion_worker.retry.10s"
    assert headers["x-paper-helper-retry-attempt"] == 1
    assert headers["x-paper-helper-error-kind"] == "TimeoutError"
    assert incoming.acked is True


async def test_retry_delivery_accepts_consumer_queue_as_broker_routing_key() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        return None

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(
        _envelope(),
        headers={"x-paper-helper-retry-attempt": 1},
        routing_key="paper_helper.knowledge.ingestion_worker",
    )

    await consumer.handle(incoming)

    assert incoming.acked is True
    assert incoming.rejected is False


async def test_exhausted_retry_is_dead_lettered() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        raise TimeoutError

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(
        _envelope(),
        headers={"x-paper-helper-retry-attempt": 2},
    )

    await consumer.handle(incoming)

    assert incoming.rejected is True
    assert publisher.retries == []


async def test_permanent_failure_is_dead_lettered_without_retry() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        raise PermanentMessageError("invalid business input")

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(_envelope())

    await consumer.handle(incoming)

    assert incoming.rejected is True
    assert publisher.retries == []


@pytest.mark.parametrize(
    "routing_key",
    ["knowledge.ingestion.requested.v2", "agent.run.requested.v1"],
)
async def test_unexpected_routing_key_is_dead_lettered(routing_key: str) -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        raise AssertionError("handler must not be called")

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(_envelope(), routing_key=routing_key)

    await consumer.handle(incoming)

    assert incoming.rejected is True


async def test_invalid_retry_header_is_dead_lettered_before_handler() -> None:
    publisher = FakePublisher()

    async def handler(_: MessageEnvelope) -> None:
        raise AssertionError("handler must not be called")

    consumer = MessageConsumer(
        subscription=_spec(),
        publisher=publisher,  # type: ignore[arg-type]
        handler=handler,
    )
    incoming = FakeIncomingMessage(
        _envelope(),
        headers={"x-paper-helper-retry-attempt": "one"},
    )

    await consumer.handle(incoming)

    assert incoming.rejected is True
