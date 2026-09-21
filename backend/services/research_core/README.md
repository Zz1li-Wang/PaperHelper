# Research Core

Owns Workspace, Research State, Proposal, Evidence, and Artifact data. These
modules remain one deployment while they share strong transactional invariants.

Each module uses `domain/`, `application/`, and `adapters/`. The service-level
`bootstrap/` directory is the only composition root. Its Alembic chain and ORM
metadata are private to this service.
