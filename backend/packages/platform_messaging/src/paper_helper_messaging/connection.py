"""RabbitMQ connection lifecycle."""

from __future__ import annotations

from typing import Any

import aio_pika


class RabbitMQConnection:
    """Own one robust AMQP connection for a single application process."""

    def __init__(self, url: str, *, connection_name: str) -> None:
        if not url:
            raise ValueError("RabbitMQ URL must not be empty")
        if not connection_name:
            raise ValueError("connection_name must not be empty")
        self._url = url
        self._connection_name = connection_name
        self._connection: Any | None = None

    @property
    def is_connected(self) -> bool:
        return self._connection is not None and not self._connection.is_closed

    async def connect(self) -> None:
        if self.is_connected:
            return
        self._connection = await aio_pika.connect_robust(
            self._url,
            client_properties={"connection_name": self._connection_name},
        )

    async def channel(
        self,
        *,
        publisher_confirms: bool = True,
        on_return_raises: bool = True,
    ) -> Any:
        if not self.is_connected:
            raise RuntimeError("RabbitMQ connection has not been opened")
        return await self._connection.channel(
            publisher_confirms=publisher_confirms,
            on_return_raises=on_return_raises,
        )

    async def close(self) -> None:
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
        self._connection = None

    async def __aenter__(self) -> RabbitMQConnection:
        await self.connect()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
