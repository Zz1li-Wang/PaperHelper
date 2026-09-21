SHELL := /usr/bin/env bash
PNPM ?= corepack pnpm

.DEFAULT_GOAL := help

.PHONY: help backend-sync backend-check agent-check migration-heads
.PHONY: migration-upgrade migration-check migration-revision migration-merge ci

help:
	@echo "Available targets:"
	@echo "  backend-check       Sync locked Python dependencies, lint, and test"
	@echo "  agent-check         Verify the pnpm workspace installs from its lockfile"
	@echo "  migration-heads     Validate the Alembic revision graph"
	@echo "  migration-upgrade   Upgrade the configured database to head"
	@echo "  migration-check     Validate graph, replay, idempotence, and ORM drift"
	@echo "  migration-revision  Create a revision: make migration-revision m=name"
	@echo "  migration-merge     Merge heads: make migration-merge m=name"
	@echo "  ci                   Run all required checks (requires a test database)"

backend-sync:
	cd backend && uv sync --locked --dev

backend-check: backend-sync
	cd backend && uv run --locked ruff check .
	cd backend && uv run --locked pytest

agent-check:
	cd agent && $(PNPM) install --frozen-lockfile

migration-heads: backend-sync
	cd backend && uv run --locked python scripts/check_migration_heads.py

migration-upgrade: backend-sync
	cd backend && uv run --locked alembic upgrade head

migration-check: migration-heads
	cd backend && uv run --locked alembic upgrade head
	cd backend && uv run --locked alembic upgrade head
	cd backend && uv run --locked alembic check

migration-revision: backend-sync
	@test -n "$(m)" || (echo "m is required: make migration-revision m=add_workspace" >&2; exit 2)
	cd backend && uv run --locked alembic revision --autogenerate -m "$(m)"

migration-merge: backend-sync
	@test -n "$(m)" || (echo "m is required: make migration-merge m=merge_workspace_heads" >&2; exit 2)
	cd backend && uv run --locked alembic merge heads -m "$(m)"

ci: backend-check agent-check migration-check
