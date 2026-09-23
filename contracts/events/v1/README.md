# Event contracts v1

Every RabbitMQ message uses `envelope.schema.json`. Concrete command and event
schemas further constrain the envelope fields and payload.

The AMQP routing key is `<message_type>.v<schema_version>`. A new compatible
optional payload field can keep the current major version. Removing a field,
changing its meaning, or tightening accepted values requires a new major schema
and routing key so old and new consumers can overlap during deployment.
