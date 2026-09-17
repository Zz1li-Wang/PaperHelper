"""Validate the Paper Helper Alembic revision graph."""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_ROOT / "migrations" / "versions"


def main() -> None:
    config = Config(BACKEND_ROOT / "alembic.ini")
    script_directory = ScriptDirectory.from_config(config)
    heads = script_directory.get_heads()
    revision_files = sorted(VERSIONS_DIR.glob("*.py"))

    if not revision_files:
        if heads:
            raise SystemExit(f"Expected no Alembic heads, found: {', '.join(heads)}")
        print("Alembic graph is empty; zero heads are allowed until the first revision.")
        return

    if len(heads) != 1:
        rendered_heads = ", ".join(heads) if heads else "none"
        raise SystemExit(f"Expected exactly one Alembic head, found: {rendered_heads}")

    print(f"Alembic graph has one head: {heads[0]}")


if __name__ == "__main__":
    main()

