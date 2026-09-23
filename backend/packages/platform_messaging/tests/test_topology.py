from typing import Any

import pytest
from paper_helper_messaging.topology import (
    COMMAND_EXCHANGE,
    DEAD_LETTER_EXCHANGE,
    SubscriptionSpec,
    declare_subscription,
)


class FakeExchange:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeQueue:
    def __init__(self, name: str, arguments: dict[str, Any]) -> None:
        self.name = name
        self.arguments = arguments
        self.bindings: list[tuple[str, str]] = []

    async def bind(self, exchange: FakeExchange, *, routing_key: str) -> None:
        self.bindings.append((exchange.name, routing_key))


class FakeChannel:
    def __init__(self) -> None:
        self.exchanges: dict[str, FakeExchange] = {}
        self.queues: dict[str, FakeQueue] = {}
        self.prefetch_count: int | None = None

    async def declare_exchange(self, name: str, *_: object, **__: object) -> FakeExchange:
        exchange = FakeExchange(name)
        self.exchanges[name] = exchange
        return exchange

    async def declare_queue(
        self,
        name: str,
        *,
        arguments: dict[str, Any],
        **__: object,
    ) -> FakeQueue:
        queue = FakeQueue(name, arguments)
        self.queues[name] = queue
        return queue

    async def set_qos(self, *, prefetch_count: int) -> None:
        self.prefetch_count = prefetch_count


async def test_subscription_declares_main_retry_and_dead_letter_queues() -> None:
    channel = FakeChannel()
    spec = SubscriptionSpec(
        queue_name="paper_helper.knowledge.ingestion_worker",
        exchange_name=COMMAND_EXCHANGE,
        routing_keys=("knowledge.ingestion.requested.v1",),
        retry_delays_seconds=(10, 60, 300),
        prefetch_count=2,
    )

    declared = await declare_subscription(channel, spec)

    assert channel.prefetch_count == 2
    assert declared.main_queue.arguments == {
        "x-queue-type": "quorum",
        "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
        "x-dead-letter-routing-key": "paper_helper.knowledge.ingestion_worker.dead",
    }
    assert declared.main_queue.bindings == [
        (COMMAND_EXCHANGE, "knowledge.ingestion.requested.v1")
    ]
    assert [queue.arguments["x-message-ttl"] for queue in declared.retry_queues] == [
        10_000,
        60_000,
        300_000,
    ]
    assert all(queue.arguments["x-dead-letter-exchange"] == "" for queue in declared.retry_queues)
    assert declared.dead_letter_queue.bindings == [
        (DEAD_LETTER_EXCHANGE, "paper_helper.knowledge.ingestion_worker.dead")
    ]


def test_subscription_rejects_unversioned_routing_key() -> None:
    with pytest.raises(ValueError, match="routing keys"):
        SubscriptionSpec(
            queue_name="paper_helper.knowledge.ingestion_worker",
            exchange_name=COMMAND_EXCHANGE,
            routing_keys=("knowledge.ingestion.requested",),
        )
