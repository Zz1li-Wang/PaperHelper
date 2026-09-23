"""Declarative RabbitMQ topology owned by message consumers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from aio_pika import ExchangeType

COMMAND_EXCHANGE = "paper_helper.commands"
EVENT_EXCHANGE = "paper_helper.events"
DEAD_LETTER_EXCHANGE = "paper_helper.dead_letters"

_QUEUE_NAME_PATTERN = re.compile(r"^paper_helper\.[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_ROUTING_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*(?:\.[a-z0-9_-]+)+\.v[1-9][0-9]*$")


@dataclass(frozen=True, slots=True)
class SubscriptionSpec:
    """A consumer-owned queue and its transport retry policy."""

    queue_name: str
    exchange_name: str
    routing_keys: tuple[str, ...]
    retry_delays_seconds: tuple[int, ...] = (10, 60, 300)
    prefetch_count: int = 10

    def __post_init__(self) -> None:
        if not _QUEUE_NAME_PATTERN.fullmatch(self.queue_name):
            raise ValueError(
                "queue_name must start with paper_helper and use stable lowercase segments"
            )
        if self.exchange_name not in {COMMAND_EXCHANGE, EVENT_EXCHANGE}:
            raise ValueError("subscriptions must use the command or event exchange")
        if not self.routing_keys:
            raise ValueError("at least one routing key is required")
        if any(not _ROUTING_KEY_PATTERN.fullmatch(key) for key in self.routing_keys):
            raise ValueError("routing keys must end in a positive .v<major> segment")
        if not self.retry_delays_seconds or any(delay <= 0 for delay in self.retry_delays_seconds):
            raise ValueError("retry delays must contain positive seconds")
        if tuple(sorted(set(self.retry_delays_seconds))) != self.retry_delays_seconds:
            raise ValueError("retry delays must be unique and increasing")
        if self.prefetch_count < 1:
            raise ValueError("prefetch_count must be positive")

    @property
    def dead_letter_queue_name(self) -> str:
        return f"{self.queue_name}.dlq"

    @property
    def dead_letter_routing_key(self) -> str:
        return f"{self.queue_name}.dead"

    def retry_queue_name(self, attempt: int) -> str:
        if attempt < 1 or attempt > len(self.retry_delays_seconds):
            raise ValueError("retry attempt is outside the configured retry policy")
        delay = self.retry_delays_seconds[attempt - 1]
        return f"{self.queue_name}.retry.{delay}s"


@dataclass(frozen=True, slots=True)
class DeclaredSubscription:
    main_queue: Any
    retry_queues: tuple[Any, ...]
    dead_letter_queue: Any


async def declare_platform_exchanges(channel: Any) -> dict[str, Any]:
    """Idempotently declare stable platform-owned exchanges."""

    exchanges: dict[str, Any] = {}
    for name in (COMMAND_EXCHANGE, EVENT_EXCHANGE, DEAD_LETTER_EXCHANGE):
        exchanges[name] = await channel.declare_exchange(
            name,
            ExchangeType.TOPIC,
            durable=True,
            auto_delete=False,
        )
    return exchanges


async def declare_subscription(channel: Any, spec: SubscriptionSpec) -> DeclaredSubscription:
    """Declare one consumer's main, retry, and dead-letter queues."""

    exchanges = await declare_platform_exchanges(channel)
    await channel.set_qos(prefetch_count=spec.prefetch_count)

    main_queue = await channel.declare_queue(
        spec.queue_name,
        durable=True,
        auto_delete=False,
        arguments={
            "x-queue-type": "quorum",
            "x-dead-letter-exchange": DEAD_LETTER_EXCHANGE,
            "x-dead-letter-routing-key": spec.dead_letter_routing_key,
        },
    )
    for routing_key in spec.routing_keys:
        await main_queue.bind(exchanges[spec.exchange_name], routing_key=routing_key)

    dead_letter_queue = await channel.declare_queue(
        spec.dead_letter_queue_name,
        durable=True,
        auto_delete=False,
        arguments={"x-queue-type": "quorum"},
    )
    await dead_letter_queue.bind(
        exchanges[DEAD_LETTER_EXCHANGE],
        routing_key=spec.dead_letter_routing_key,
    )

    retry_queues: list[Any] = []
    for attempt, delay in enumerate(spec.retry_delays_seconds, start=1):
        retry_queue = await channel.declare_queue(
            spec.retry_queue_name(attempt),
            durable=True,
            auto_delete=False,
            arguments={
                "x-queue-type": "quorum",
                "x-message-ttl": delay * 1000,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": spec.queue_name,
            },
        )
        retry_queues.append(retry_queue)

    return DeclaredSubscription(
        main_queue=main_queue,
        retry_queues=tuple(retry_queues),
        dead_letter_queue=dead_letter_queue,
    )
