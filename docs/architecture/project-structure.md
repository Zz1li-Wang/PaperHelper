# 目录结构与仓库边界

## 总体原则

Paper Helper 使用一个仓库中的两个运行时工作区：

- `backend/` 是 uv 管理的 Python 项目，包含业务模块、FastAPI、FastMCP 和 Ingestion Worker。
- `agent/` 是 pnpm 管理的 TypeScript workspace，包含 Agent Worker、Paper Helper Agent 与通用 Harness。
- 两个运行时不共享源码类型，只通过根目录 `contracts/`、MCP、HTTP/OpenAPI 和版本化消息契约协作。

## 根目录

```text
paper_helper/
├── backend/
├── agent/
├── contracts/
├── deploy/
├── docs/
└── tests/
```

`tests/` 只保存跨运行时集成、契约、端到端和架构边界测试。Python 模块自身的测试统一放在 `backend/tests/`；TypeScript 包的测试放在对应 workspace package 中。

## Python Backend

```text
backend/
├── src/paper_helper/
│   ├── apps/
│   │   ├── web_api/
│   │   ├── mcp_server/
│   │   └── ingestion_worker/
│   ├── workspace/
│   ├── sources/
│   ├── research/
│   ├── artifacts/
│   ├── conversations/
│   ├── agent_runs/
│   └── infrastructure/             # 共享 ORM Base 与显式模型注册入口
├── migrations/
├── tests/
├── fastmcp.json
├── pyproject.toml
└── uv.lock
```

Backend 是一个 Python distribution 和一个 uv 环境。业务模块不是独立发布的 Python 包，避免在 MVP 阶段引入内部包发布和多锁文件成本。

所有模块的 ORM 模型共享 `paper_helper.infrastructure.database.OrmBase`，并在显式注册入口中
登记，确保 Alembic autogenerate 与 drift check 能加载完整 metadata。数据库 migration
使用单一 revision chain；具体规则见[数据库迁移规范](database-migrations.md)。

每个业务模块按需要建立以下分层：

```text
research/
├── domain/
├── application/
├── infrastructure/
└── gateway/
    ├── http/
    └── mcp/
```

`apps/mcp_server` 只负责创建 FastMCP Server、注册各业务模块提供的 MCP Adapter，以及装配运行依赖。工具实现属于对应业务模块的 `gateway/mcp`，不能在 composition root 中堆积业务规则。

## TypeScript Agent

```text
agent/
├── apps/
│   └── agent-worker/
├── packages/
│   ├── paper-helper-agent/
│   ├── harness-core/
│   └── harness-mcp/
├── package.json
├── pnpm-workspace.yaml
└── tsconfig.json
```

- `harness-core` 是领域无关的 Agent runtime。
- `harness-mcp` 实现 Harness 的 MCP ToolProvider。
- `paper-helper-agent` 实现科研任务语义、策略和工具白名单。
- `agent-worker` 是消息消费、运行装配和任务生命周期入口。

## 核心依赖方向

- Web Client 通过 FastAPI 访问业务状态。
- Agent Worker 通过 MCP Client 调用 FastMCP。
- FastAPI 与 FastMCP 都直接调用 Python Application Service，二者不互相转发。
- Gateway 可以依赖 Application；Application 可以依赖 Domain 与 Port。
- Domain 不得依赖 FastAPI、FastMCP、SQLAlchemy、消息客户端或模型 SDK。
- FastMCP Tool 不得直接访问 Repository 或 ORM，也不得自行提交事务。
- `harness-core` 不得依赖任何 Paper Helper 领域模块。

## 测试归属

- `backend/tests/apps/mcp_server/`：MCP 列表、调用、Schema、身份传播与错误映射。
- `backend/tests/<module>/`：Python 领域、Application 和 Repository 测试。
- `agent/**/tests/`：Agent 策略、Harness 和 MCP Client Adapter 测试。
- `tests/contracts/`：跨语言 Schema 与兼容性。
- `tests/integration/`：Agent → MCP → Application 等跨工作区调用。
- `tests/e2e/`：用户业务验收链路。
- `tests/architecture/`：依赖方向和模块隔离规则。
