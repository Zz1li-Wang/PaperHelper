from paper_helper.apps.mcp_server.server import mcp
from paper_helper.settings import get_settings


def main() -> None:
    settings = get_settings()
    mcp.run(
        transport="http",
        host=settings.mcp_host,
        port=settings.mcp_port,
        log_level=settings.mcp_log_level,
    )


if __name__ == "__main__":
    main()
