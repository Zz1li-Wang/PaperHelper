"""Manual-ack consumer behavior with bounded transport retries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from paper_helper_messaging.envelope import EnvelopeError, MessageEnvelope
from paper_helper_messaging.publisher import RabbitPublisher
from paper_helper_messaging.topology import SubscriptionSpec

_RETRY_ATTEMPT_HEADER = "x-paper-helper-retry-attempt"
_ERROR_KIND_HEADER = "x-paper-helper-error-kind"


class RetryableMessageError(RuntimeError):
    """A handler failure that is expected to succeed after a short retry."""


class PermanentMessageError(RuntimeError):
    """A handler failure that must go directly to the dead-letter queue."""


MessageHandler = Callable[[MessageEnvelope], Awaitable[None]]


class MessageConsumer:
    """Decode, dispatch, and acknowledge messages according to one subscription."""

    def __init__(
        self,
        *,
        subscription: SubscriptionSpec,
        publisher: RabbitPublisher,
        handler: MessageHandler,
    ) -> None:
        self._subscription = subscription
        self._publisher = publisher
        self._handler = handler

    async def consume(self, queue: Any) -> str:
        return await queue.consume(self.handle, no_ack=False)

    async def handle(self, incoming: Any) -> None:
        try:
            envelope = MessageEnvelope.from_json(incoming.body)
            attempt = self._retry_attempt(incoming.headers)
            self._validate_delivery(envelope, incoming.routing_key, attempt)
        except EnvelopeError:
            await incoming.reject(requeue=False)
            return

        try:
            await self._handler(envelope)
        except PermanentMessageError:
            await incoming.reject(requeue=False)
        except Exception as exc:
            await self._retry_or_reject(incoming, envelope, exc, attempt)
        else:
            await incoming.ack()

    def _validate_delivery(
        self,
        envelope: MessageEnvelope,
        routing_key: str,
        retry_attempt: int,
    ) -> None:
        if envelope.routing_key not in self._subscription.routing_keys:
            raise EnvelopeError("message envelope has an unconfigured routing key")
        initial_delivery = retry_attempt == 0 and routing_key == envelope.routing_key
        retried_delivery = retry_attempt > 0 and routing_key == self._subscription.queue_name
        if not initial_delivery and not retried_delivery:
            raise EnvelopeError("AMQP routing key does not match the delivery state")

    async def _retry_or_reject(
        self,
        incoming: Any,
        envelope: MessageEnvelope,
        error: Exception,
        attempt: int,
    ) -> None:
        if attempt >= len(self._subscription.retry_delays_seconds):
            await incoming.reject(requeue=False)
            return

        next_attempt = attempt + 1
        headers = dict(incoming.headers or {})
        headers[_RETRY_ATTEMPT_HEADER] = next_attempt
        headers[_ERROR_KIND_HEADER] = type(error).__name__
        try:
            await self._publisher.publish_to_queue(
                envelope,
                self._subscription.retry_queue_name(next_attempt),
                headers=headers,
            )
        except Exception:
            # An unroutable retry is a topology defect. Keep the original message
            # inspectable instead of entering an immediate requeue loop.
            await incoming.reject(requeue=False)
            raise
        await incoming.ack()

    @staticmethod
    def _retry_attempt(headers: dict[str, Any] | None) -> int:
        value = (headers or {}).get(_RETRY_ATTEMPT_HEADER, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise EnvelopeError("retry attempt header must be a non-negative integer")
        return value
