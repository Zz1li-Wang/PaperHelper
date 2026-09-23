"""Executable dependency rules for the microservice workspace."""

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SERVICES_ROOT = BACKEND_ROOT / "services"
GATEWAYS_ROOT = BACKEND_ROOT / "gateways"
PLATFORM_PACKAGES_ROOT = BACKEND_ROOT / "packages"
SERVICE_PACKAGES = {"research_core", "knowledge_service", "interaction_service"}
DOMAIN_FORBIDDEN_IMPORTS = {
    "aio_pika",
    "alembic",
    "aiormq",
    "asyncpg",
    "fastapi",
    "fastmcp",
    "httpx",
    "pydantic",
    "paper_helper_messaging",
    "redis",
    "sqlalchemy",
}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])
    return imported


def test_services_do_not_import_other_service_packages() -> None:
    violations: list[str] = []
    for service in SERVICE_PACKAGES:
        service_root = SERVICES_ROOT / service / "src"
        forbidden = SERVICE_PACKAGES - {service}
        for path in service_root.rglob("*.py"):
            illegal = sorted(_imports(path) & forbidden)
            if illegal:
                violations.append(f"{path.relative_to(BACKEND_ROOT)} -> {', '.join(illegal)}")
    assert not violations, "Cross-service source imports are forbidden:\n" + "\n".join(violations)


def test_domain_code_is_framework_independent() -> None:
    violations: list[str] = []
    for path in SERVICES_ROOT.rglob("*.py"):
        if "domain" not in path.parts:
            continue
        illegal = sorted(_imports(path) & DOMAIN_FORBIDDEN_IMPORTS)
        if illegal:
            violations.append(f"{path.relative_to(BACKEND_ROOT)} -> {', '.join(illegal)}")
    assert not violations, "Domain framework imports are forbidden:\n" + "\n".join(violations)


def test_gateways_do_not_import_service_implementations() -> None:
    violations: list[str] = []
    for path in GATEWAYS_ROOT.rglob("*.py"):
        illegal = sorted(_imports(path) & SERVICE_PACKAGES)
        if illegal:
            violations.append(f"{path.relative_to(BACKEND_ROOT)} -> {', '.join(illegal)}")
    message = "Gateways must use service contracts or clients:\n" + "\n".join(violations)
    assert not violations, message


def test_platform_packages_do_not_import_service_implementations() -> None:
    violations: list[str] = []
    for path in PLATFORM_PACKAGES_ROOT.rglob("*.py"):
        illegal = sorted(_imports(path) & SERVICE_PACKAGES)
        if illegal:
            violations.append(f"{path.relative_to(BACKEND_ROOT)} -> {', '.join(illegal)}")
    message = "Platform packages must remain business-agnostic:\n" + "\n".join(violations)
    assert not violations, message


def test_each_service_owns_migrations_and_metadata() -> None:
    for service in SERVICE_PACKAGES:
        service_root = SERVICES_ROOT / service
        package_root = service_root / "src" / service
        assert (service_root / "alembic.ini").is_file()
        assert (service_root / "migrations" / "env.py").is_file()
        assert (
            package_root / "adapters" / "outbound" / "persistence" / "database.py"
        ).is_file()
