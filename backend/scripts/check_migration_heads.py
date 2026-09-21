"""Validate every service-owned Alembic revision graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SERVICES = ("research_core", "knowledge_service", "interaction_service")


def _check_service(service: str) -> None:
    service_root = BACKEND_ROOT / "services" / service
    config = Config(service_root / "alembic.ini")
    script_directory = ScriptDirectory.from_config(config)
    heads = script_directory.get_heads()
    revision_files = sorted((service_root / "migrations" / "versions").glob("*.py"))

    if not revision_files:
        if heads:
            raise SystemExit(f"{service}: expected no Alembic heads, found: {', '.join(heads)}")
        print(f"{service}: graph is empty; zero heads are allowed until the first revision.")
        return

    if len(heads) != 1:
        rendered_heads = ", ".join(heads) if heads else "none"
        raise SystemExit(f"{service}: expected exactly one head, found: {rendered_heads}")

    print(f"{service}: graph has one head: {heads[0]}")


def main() -> None:
    for service in SERVICES:
        _check_service(service)


if __name__ == "__main__":
    main()
