"""RabbitMQ transport primitives shared by Python deployment units."""

from paper_helper_messaging.connection import RabbitMQConnection
from paper_helper_messaging.consumer import (
    MessageConsumer,
    PermanentMessageError,
    RetryableMessageError,
)
from paper_helper_messaging.envelope import (
    EnvelopeError,
    MessageActor,
    MessageEnvelope,
    MessageKind,
)
from paper_helper_messaging.publisher import MessageTooLargeError, PublishError, RabbitPublisher
from paper_helper_messaging.topology import (
    COMMAND_EXCHANGE,
    DEAD_LETTER_EXCHANGE,
    EVENT_EXCHANGE,
    DeclaredSubscription,
    SubscriptionSpec,
    declare_platform_exchanges,
    declare_subscription,
)

__all__ = [
    "COMMAND_EXCHANGE",
    "DEAD_LETTER_EXCHANGE",
    "EVENT_EXCHANGE",
    "DeclaredSubscription",
    "EnvelopeError",
    "MessageActor",
    "MessageConsumer",
    "MessageEnvelope",
    "MessageKind",
    "MessageTooLargeError",
    "PermanentMessageError",
    "PublishError",
    "RabbitMQConnection",
    "RabbitPublisher",
    "RetryableMessageError",
    "SubscriptionSpec",
    "declare_platform_exchanges",
    "declare_subscription",
]
