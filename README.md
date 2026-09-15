# Paper Helper

面向持续科研活动的 AI Research Workspace。项目围绕研究材料、可追溯的研究状态、对话和研究成果组织功能。

当前阶段：项目骨架与模块边界整理。仓库内容包括目录结构、产品需求和架构说明，尚未添加应用代码。

## 项目说明

- [产品需求说明](<Paper Helper需求说明.pdf>)
- [技术架构与开发设计 v0.2](Paper_Helper_技术架构与开发设计_v0.2.docx)
- [目录结构与仓库划分草案](docs/architecture/project-structure.md)

原始说明文件暂时保留在项目根目录。

## 目录概览

```text
paper_helper/
├── apps/          # 前端、API、科研 Agent、MCP 与 Worker
├── packages/      # 通用运行库、跨进程契约与业务模块
├── docs/          # 需求、架构与决策说明
├── migrations/    # 数据库迁移预留
├── tests/         # 跨模块集成、契约、端到端与架构测试
└── deploy/        # 部署配置预留
```

当前目录采用 Monorepo（单仓多包）结构；各应用可以独立运行与部署。

每个应用和包都有自己的 `tests/`，例如 `apps/paper_helper_agent/tests/` 和 `apps/mcp_server/tests/`。单个模块的测试放在模块目录中；根目录的 `tests/` 用于验证跨模块协作和全仓库边界。

预留目录使用 `.gitkeep` 占位，使 Git 能保存目录结构；后续添加实际文件后可移除对应占位文件。
