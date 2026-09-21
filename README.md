# Paper Helper

面向持续科研活动的 AI Research Workspace。项目围绕研究材料、可追溯的研究状态、对话和研究成果组织功能。

当前阶段：建立双运行时 Monorepo、DDD 微服务边界和 FastMCP Gateway。Python Backend
使用 uv workspace，TypeScript Agent 使用 pnpm workspace。

## 项目说明

- [产品需求说明](docs/requirements/product-requirements.md)
- [技术架构与开发设计](docs/architecture/system-design.md)
- [技术选型与基础设施基线](docs/architecture/technology-baseline.md)
- [目录结构与仓库边界](docs/architecture/project-structure.md)

## 目录概览

```text
paper_helper/
├── backend/       # Python 业务微服务与无状态 Gateway
├── agent/         # TypeScript Agent Worker、Agent 与 Harness
├── contracts/     # 跨语言 OpenAPI、JSON Schema 与事件契约
├── docs/          # 需求、架构与决策说明
├── tests/         # 跨运行时集成、契约、端到端与架构测试
└── deploy/        # 部署配置预留
```

Backend 当前划分为 `research_core`、`knowledge_service` 和 `interaction_service` 三个数据
所有者服务，以及一个无状态 MCP Gateway。浏览器流量由反向代理路由到各服务的 HTTP
接口；服务之间不共享 Application、Domain、ORM 或数据库，只通过版本化 HTTP/消息契约
协作。

## Backend 快速开始

```bash
make backend-check

cd backend
uv run --package paper-helper-mcp-gateway python -m paper_helper_mcp_gateway
```

FastMCP 默认通过 Streamable HTTP 暴露在 `http://127.0.0.1:8001/mcp`。当前服务骨架尚未暴露业务工具。

## Agent 工作区

```bash
make agent-check
```

Agent 工作区当前只建立包边界，尚未添加运行时代码。

## 数据库迁移与 CI

数据库命令统一从仓库根目录执行：

```bash
make migration-heads
make migration-revision service=research_core m=add_workspace
make migration-upgrade
make migration-check
```

迁移命令要求为三个业务服务显式配置各自的数据库 URL。完整规则见
[数据库迁移规范](docs/architecture/database-migrations.md)。GitHub Actions 对每个
`main` Pull Request 执行 Backend、Agent 和数据库迁移三项检查。工作流首次在 GitHub
成功运行后，按 [`main` 分支保护说明](docs/development/main-branch-protection.md) 创建
团队仓库 ruleset。
