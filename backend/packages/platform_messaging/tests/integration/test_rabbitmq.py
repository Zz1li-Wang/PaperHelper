import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from aio_pika.exceptions import DeliveryError
from paper_helper_messaging import (
    COMMAND_EXCHANGE,
    MessageActor,
    MessageEnvelope,
    MessageKind,
    RabbitMQConnection,
    RabbitPublisher,
    SubscriptionSpec,
    declare_subscription,
)

RABBITMQ_TEST_URL = os.getenv("PAPER_HELPER_RABBITMQ_TEST_URL")

pytestmark = pytest.mark.skipif(
    not RABBITMQ_TEST_URL,
    reason="PAPER_HELPER_RABBITMQ_TEST_URL is not configured",
)


async def test_publish_retry_and_dead_letter_round_trip() -> None:
    suffix = uuid4().hex
    queue_name = f"paper_helper.test.retry_{suffix}"
    connection = RabbitMQConnection(
        RABBITMQ_TEST_URL or "",
        connection_name=f"platform-messaging-test-{suffix}",
    )
    await connection.connect()
    channel = await connection.channel()
    spec = SubscriptionSpec(
        queue_name=queue_name,
        exchange_name=COMMAND_EXCHANGE,
        routing_keys=("knowledge.ingestion.requested.v1",),
        retry_delays_seconds=(1,),
        prefetch_count=1,
    )
    declared = await declare_subscription(channel, spec)
    publisher = await RabbitPublisher.create(channel)
    envelope = MessageEnvelope(
        message_id=uuid4(),
        message_type="knowledge.ingestion.requested",
        message_kind=MessageKind.COMMAND,
        schema_version=1,
        occurred_at=datetime.now(UTC),
        producer="platform-messaging-test",
        correlation_id=uuid4(),
        causation_id=None,
        workspace_id=UUID("a6a44285-99df-41c6-92af-b54fa61907c9"),
        aggregate_type="source",
        aggregate_id=UUID("31fdbbd2-314f-4711-a147-fc0148a5d678"),
        aggregate_version=1,
        actor=MessageActor(type="system", id="platform-messaging-test"),
        payload={"source_id": "31fdbbd2-314f-4711-a147-fc0148a5d678"},
    )

    try:
        unroutable = MessageEnvelope.new(
            message_type="knowledge.unroutable.requested",
            message_kind=MessageKind.COMMAND,
            producer="platform-messaging-test",
            actor=MessageActor(type="system", id="platform-messaging-test"),
            payload={},
        )
        with pytest.raises(DeliveryError):
            await publisher.publish(unroutable)

        await publisher.publish(envelope)
        initial = await declared.main_queue.get(timeout=5)
        assert MessageEnvelope.from_json(initial.body) == envelope

        await publisher.publish_to_queue(
            envelope,
            spec.retry_queue_name(1),
            headers={"x-paper-helper-retry-attempt": 1},
        )
        await initial.ack()

        retried = await _get_eventually(declared.main_queue)
        assert retried.routing_key == queue_name
        assert retried.headers["x-paper-helper-retry-attempt"] == 1
        await retried.reject(requeue=False)

        dead = await _get_eventually(declared.dead_letter_queue)
        assert MessageEnvelope.from_json(dead.body) == envelope
        await dead.ack()
    finally:
        for queue in (*declared.retry_queues, declared.dead_letter_queue, declared.main_queue):
            await queue.delete(if_unused=False, if_empty=False)
        await connection.close()


async def _get_eventually(queue: object) -> object:
    deadline = asyncio.get_running_loop().time() + 5
    while asyncio.get_running_loop().time() < deadline:
        message = await queue.get(timeout=1, fail=False)  # type: ignore[attr-defined]
        if message is not None:
            return message
    raise AssertionError("message did not arrive before the deadline")
