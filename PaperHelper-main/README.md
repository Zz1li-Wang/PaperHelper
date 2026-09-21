# Paper Helper

面向持续科研活动的 AI Research Workspace。项目围绕研究材料、可追溯的研究状态、对话和研究成果组织功能。

当前阶段：建立双运行时 Monorepo 骨架和 FastMCP Gateway。Python Backend 使用 uv，TypeScript Agent 使用 pnpm workspace。

## 项目说明

- [产品需求说明](<Paper Helper需求说明.md>)
- [技术架构与开发设计](Paper_Helper_技术架构与开发设计.md)
- [技术选型与基础设施基线](Paper_Helper_技术选型与基础设施基线.md)
- [目录结构与仓库边界](docs/architecture/project-structure.md)

## 目录概览

```text
paper_helper/
├── backend/       # Python Backend、FastAPI、FastMCP 与 Ingestion
├── agent/         # TypeScript Agent Worker、Agent 与 Harness
├── contracts/     # 跨语言 OpenAPI、JSON Schema 与事件契约
├── docs/          # 需求、架构与决策说明
├── tests/         # 跨运行时集成、契约、端到端与架构测试
└── deploy/        # 部署配置预留
```

FastAPI 与 FastMCP 是同一 Python Backend 的并列 Gateway Adapter，共享 Application/Domain 模块，但可以作为独立进程运行。FastMCP 不通过 FastAPI 转发业务调用。

## Backend 快速开始

```bash
make backend-check

cd backend
uv run fastmcp run fastmcp.json --skip-env
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
make migration-revision m=add_workspace
make migration-upgrade
make migration-check
```

迁移命令要求显式配置 `PAPER_HELPER_DATABASE_URL`。完整规则见
[数据库迁移规范](docs/architecture/database-migrations.md)。GitHub Actions 对每个
`main` Pull Request 执行 Backend、Agent 和数据库迁移三项检查。工作流首次在 GitHub
成功运行后，按 [`main` 分支保护说明](docs/development/main-branch-protection.md) 创建
团队仓库 ruleset。
