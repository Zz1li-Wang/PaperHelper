# RabbitMQ deployment configuration

This directory configures the broker, not application message handlers.

- `rabbitmq.conf` configures listeners, management, definitions import, and the
  consumer timeout.
- `definitions.json` creates the stable exchanges and applies safety policies to
  consumer-owned quorum queues.
- Consumers declare their own main, retry, and dead-letter queues through
  `paper-helper-messaging`.

Start the local broker from the repository root:

```bash
docker compose up -d --wait rabbitmq
```

The AMQP endpoint defaults to `amqp://paper_helper:paper_helper@127.0.0.1:5672/paper_helper`.
The management UI is available only on localhost at <http://127.0.0.1:15672>.

The account above is a fixed development-only administrator whose password is stored
as a RabbitMQ password hash in `definitions.json`. RabbitMQ skips its default-user
bootstrap whenever boot-time definitions are imported, so changing
`RABBITMQ_DEFAULT_USER` or `RABBITMQ_DEFAULT_PASS` would have no effect here.

Production deployments must provision separate least-privilege users through their
secret/IaC system, enable TLS, and use an odd-sized cluster for quorum queues. They
must not import this local user definition.
