# Interaction Service

Owns Conversation, Message, Agent Run, and durable Run Event state. It receives
versioned runtime events from the TypeScript Agent Worker and exposes persisted
history to the edge gateways.

Its Alembic chain and ORM metadata are private to this service.
