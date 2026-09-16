# Paper Helper Backend

Paper Helper 的 Python 工作区，包含 FastAPI、FastMCP、Ingestion Worker 和共享的业务模块。

## 本地开发

```bash
uv sync
uv run pytest
uv run ruff check .
```

启动 FastMCP 服务：

```bash
uv run fastmcp run fastmcp.json --skip-env
```

默认 MCP 地址为 `http://127.0.0.1:8001/mcp`。

也可以通过 Python 模块入口启动：

```bash
uv run python -m paper_helper.apps.mcp_server
```
