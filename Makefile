SHELL := /usr/bin/env bash
PNPM ?= corepack pnpm
MIGRATION_SERVICES := research_core knowledge_service interaction_service

.DEFAULT_GOAL := help

.PHONY: help backend-sync backend-check agent-check rabbitmq-up rabbitmq-down rabbitmq-config
.PHONY: rabbitmq-test
.PHONY: migration-heads
.PHONY: migration-upgrade migration-check migration-revision migration-merge ci

help:
	@echo "Available targets:"
	@echo "  backend-check       Sync locked Python dependencies, lint, and test"
	@echo "  agent-check         Verify the pnpm workspace installs from its lockfile"
	@echo "  rabbitmq-config     Validate the local RabbitMQ Compose configuration"
	@echo "  rabbitmq-up         Start the local RabbitMQ broker and wait until healthy"
	@echo "  rabbitmq-test       Run the real publish, retry, and dead-letter integration test"
	@echo "  rabbitmq-down       Stop the local RabbitMQ broker (data is retained)"
	@echo "  migration-heads     Validate the Alembic revision graph"
	@echo "  migration-upgrade   Upgrade the configured database to head"
	@echo "  migration-check     Validate graph, replay, idempotence, and ORM drift"
	@echo "  migration-revision  Create a revision: make migration-revision service=name m=change"
	@echo "  migration-merge     Merge heads: make migration-merge service=name m=change"
	@echo "  ci                   Run all required checks (requires a test database)"

backend-sync:
	cd backend && uv sync --locked --all-packages --dev

backend-check: backend-sync
	cd backend && uv run --locked ruff check . ../tests/contracts
	cd backend && uv run --locked pytest

agent-check:
	cd agent && $(PNPM) install --frozen-lockfile

rabbitmq-config:
	docker compose config --quiet

rabbitmq-up: rabbitmq-config
	docker compose up -d --wait rabbitmq

rabbitmq-test: rabbitmq-up backend-sync
	cd backend && PAPER_HELPER_RABBITMQ_TEST_URL=amqp://paper_helper:paper_helper@127.0.0.1:5672/paper_helper \
		uv run --locked pytest packages/platform_messaging/tests/integration/test_rabbitmq.py

rabbitmq-down:
	docker compose stop rabbitmq

migration-heads: backend-sync
	cd backend && uv run --locked python scripts/check_migration_heads.py

migration-upgrade: backend-sync
	@set -e; for service in $(MIGRATION_SERVICES); do \
		cd backend && uv run --locked alembic -c services/$$service/alembic.ini upgrade head; \
		cd ..; \
	done

migration-check: migration-heads
	@set -e; for service in $(MIGRATION_SERVICES); do \
		cd backend && uv run --locked alembic -c services/$$service/alembic.ini upgrade head && \
		uv run --locked alembic -c services/$$service/alembic.ini upgrade head && \
		uv run --locked alembic -c services/$$service/alembic.ini check; \
		cd ..; \
	done

migration-revision: backend-sync
	@test -n "$(service)" || (echo "service is required: $(MIGRATION_SERVICES)" >&2; exit 2)
	@case " $(MIGRATION_SERVICES) " in *" $(service) "*) ;; *) echo "unknown service: $(service)" >&2; exit 2;; esac
	@test -n "$(m)" || (echo "m is required: make migration-revision service=research_core m=add_workspace" >&2; exit 2)
	cd backend && uv run --locked alembic -c services/$(service)/alembic.ini revision --autogenerate -m "$(m)"

migration-merge: backend-sync
	@test -n "$(service)" || (echo "service is required: $(MIGRATION_SERVICES)" >&2; exit 2)
	@case " $(MIGRATION_SERVICES) " in *" $(service) "*) ;; *) echo "unknown service: $(service)" >&2; exit 2;; esac
	@test -n "$(m)" || (echo "m is required: make migration-merge service=research_core m=merge_workspace_heads" >&2; exit 2)
	cd backend && uv run --locked alembic -c services/$(service)/alembic.ini merge heads -m "$(m)"

ci: backend-check agent-check migration-check
