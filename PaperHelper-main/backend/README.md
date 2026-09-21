# Paper Helper Backend

Paper Helper 的 Python 工作区，包含 FastAPI、FastMCP、Ingestion Worker 和共享的业务模块。

## 本地开发

```bash
uv sync
uv run pytest
uv run ruff check .
```

也可以从仓库根目录运行统一检查：

```bash
make backend-check
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

## 数据库迁移

复制 `.env.example` 并配置 `PAPER_HELPER_DATABASE_URL` 后，从仓库根目录使用：

```bash
make migration-heads
make migration-revision m=add_workspace
make migration-upgrade
make migration-check
```

当前迁移链保持为空，直到第一个 ORM 模型落地。Alembic 不会自动创建数据库，应用进程
启动时也不会自动执行 migration。
