# Knowledge Service

Owns Source, Document, Chunk, ingestion state, and retrieval indexes. HTTP and
ingestion-worker processes are separate entrypoints built from this same service
because they operate on one data model.

Its Alembic chain and ORM metadata are private to this service.
