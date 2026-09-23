# Paper Helper Messaging

Shared Python transport primitives for RabbitMQ. This package owns AMQP connection
management, publisher confirms, the common message envelope, topology declaration,
and transport-level retry handling.

It deliberately does not contain business message payloads, service handlers,
Outbox/Inbox ORM models, or service-specific idempotency rules. Those remain in the
service that owns the use case.
