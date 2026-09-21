from paper_helper_mcp_gateway.server import mcp
from paper_helper_mcp_gateway.settings import get_settings


def main() -> None:
    settings = get_settings()
    mcp.run(
        transport="http",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
