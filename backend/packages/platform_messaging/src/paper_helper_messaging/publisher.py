"""Confirmed RabbitMQ publishing."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC
from typing import Any

import aio_pika

from paper_helper_messaging.envelope import MessageEnvelope, MessageKind
from paper_helper_messaging.topology import (
    COMMAND_EXCHANGE,
    EVENT_EXCHANGE,
    declare_platform_exchanges,
)

MAX_MESSAGE_BYTES = 256 * 1024


class PublishError(RuntimeError):
    """Raised when RabbitMQ does not confirm a publish."""


class MessageTooLargeError(PublishError):
    """Raised before publishing a message larger than the transport limit."""


class RabbitPublisher:
    """Publish persistent messages through a publisher-confirm channel."""

    def __init__(self, channel: Any, exchanges: Mapping[str, Any]) -> None:
        self._channel = channel
        self._exchanges = dict(exchanges)

    @classmethod
    async def create(cls, channel: Any) -> RabbitPublisher:
        exchanges = await declare_platform_exchanges(channel)
        return cls(channel, exchanges)

    async def publish(
        self,
        envelope: MessageEnvelope,
        *,
        headers: Mapping[str, object] | None = None,
    ) -> None:
        exchange_name = (
            COMMAND_EXCHANGE if envelope.message_kind is MessageKind.COMMAND else EVENT_EXCHANGE
        )
        exchange = self._exchanges[exchange_name]
        message = self._build_message(envelope, headers=headers)
        result = await exchange.publish(message, envelope.routing_key, mandatory=True)
        if result is False:
            raise PublishError(f"RabbitMQ did not confirm {envelope.routing_key}")

    async def publish_to_queue(
        self,
        envelope: MessageEnvelope,
        queue_name: str,
        *,
        headers: Mapping[str, object] | None = None,
    ) -> None:
        message = self._build_message(envelope, headers=headers)
        result = await self._channel.default_exchange.publish(
            message,
            queue_name,
            mandatory=True,
        )
        if result is False:
            raise PublishError(f"RabbitMQ did not confirm direct publish to {queue_name}")

    @staticmethod
    def _build_message(
        envelope: MessageEnvelope,
        *,
        headers: Mapping[str, object] | None,
    ) -> aio_pika.Message:
        body = envelope.to_json()
        if len(body) > MAX_MESSAGE_BYTES:
            raise MessageTooLargeError(
                f"message body is {len(body)} bytes; limit is {MAX_MESSAGE_BYTES}"
            )
        message_headers = dict(headers or {})
        message_headers["x-paper-helper-schema-version"] = envelope.schema_version
        return aio_pika.Message(
            body=body,
            content_type="application/json",
            content_encoding="utf-8",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            message_id=str(envelope.message_id),
            correlation_id=str(envelope.correlation_id),
            timestamp=envelope.occurred_at.astimezone(UTC),
            type=envelope.routing_key,
            app_id=envelope.producer,
            headers=message_headers,
        )
