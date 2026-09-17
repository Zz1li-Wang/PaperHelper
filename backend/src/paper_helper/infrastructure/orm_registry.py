"""Explicit import registry used by Alembic autogeneration."""


def import_orm_models() -> None:
    """Import every ORM model module so it registers with shared metadata.

    Keep imports explicit here as infrastructure modules are introduced. This
    makes the metadata used by Alembic reviewable and avoids package-walking
    side effects.
    """

