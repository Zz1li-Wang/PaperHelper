# Paper Helper Backend

Paper Helper 的 Python 微服务 workspace。业务服务独立拥有数据和 Migration；MCP
Gateway 是面向 Agent 的无状态协议适配器。

## Workspace members

- `services/research_core`：Workspace、Research State、Proposal、Evidence、Artifact。
- `services/knowledge_service`：Source、Document、Chunk、Ingestion、Retrieval。
- `services/interaction_service`：Conversation、Message、Agent Run、Run Event。
- `gateways/mcp_gateway`：面向 Agent 的 FastMCP Gateway。

浏览器请求由反向代理按路径转发到各业务服务自己的 HTTP/SSE 入站接口，不设置独立的
Python Web Gateway。

## 本地开发

```bash
uv sync --locked --all-packages --dev
uv run --locked ruff check .
uv run --locked pytest
```

也可以从仓库根目录运行：

```bash
make backend-check
```

启动 MCP Gateway：

```bash
uv run --package paper-helper-mcp-gateway python -m paper_helper_mcp_gateway
```

默认地址为 `http://127.0.0.1:8001/mcp`。当前骨架尚未暴露业务工具；后续工具必须通过
生成的客户端或版本化契约调用业务服务，不能 import 服务实现。

## 数据库迁移

复制 `.env.example` 并为三个服务分别配置数据库 URL：

```bash
make migration-heads
make migration-revision service=research_core m=add_workspace
make migration-upgrade
make migration-check
```

Migration chain 当前保持为空，直到对应服务的第一个 ORM model 落地。详细规则见
[`docs/architecture/database-migrations.md`](../docs/architecture/database-migrations.md)。
