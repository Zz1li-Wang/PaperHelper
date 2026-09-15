# 目录结构与仓库划分草案

## 依据与当前范围

本草案依据项目根目录的《Paper Helper需求说明》和《Paper Helper 技术架构与开发设计 v0.2》。目前只建立目录、说明文件、Git 忽略规则与目录占位文件，不添加应用代码、依赖配置或部署配置。

技术架构第 3.1 节推荐一个仓库中的多个应用与包。这里沿用该结构，额外预留 `apps/web/` 和文档目录。前端技术尚未确定。

## 应用目录

| 目录 | 职责 | 运行形态 |
| --- | --- | --- |
| `apps/web/` | Workspace、材料、聊天、研究状态审查和成果界面 | 前端应用，框架待定 |
| `apps/web_api/` | Research API、身份校验、业务用例入口与 SSE | 独立 API 进程 |
| `apps/paper_helper_agent/` | 科研任务路由、策略、提示词、上下文请求和输出校验 | 由 Agent Worker 加载的 Agent 应用 |
| `apps/mcp_server/` | 领域工具协议、工具参数校验、调用身份与后端客户端 | 独立 MCP 进程 |
| `apps/agent_worker/` | 长任务执行、科研 Agent 装配与任务队列入口 | 独立 Worker 进程 |
| `apps/ingestion_worker/` | 文献解析、标准化、分块与索引任务入口 | 独立 Worker 进程 |

## 包目录

| 目录 | 职责 |
| --- | --- |
| `packages/harness_core/` | 领域无关的 Agent Loop、模型和工具端口、运行事件、取消与重试 |
| `packages/harness_mcp/` | 将 MCP 工具接入 Harness 的通用适配器 |
| `packages/contracts/` | 跨进程 DTO、身份、错误和事件信封等稳定契约 |
| `packages/workspace/` | 研究项目、成员权限和当前研究焦点 |
| `packages/sources/` | 原始来源、文档版本、解析状态和可定位片段 |
| `packages/research/` | 研究判断、版本、证据、修改提议、审查和回滚 |
| `packages/artifacts/` | 结构化成果、版本和文件渲染请求 |
| `packages/conversations/` | 对话与消息持久化 |
| `packages/agent_runs/` | 业务 Run、步骤、关键事件、取消和重试状态 |

六个业务包后续按技术说明划分 `domain/`、`application/`、`infrastructure/`；需要时增加 `gateway/`。当前先保留包目录，内部结构在开始开发前细化。

Harness 保存通用运行概念；`agent_runs` 拥有与用户和 Workspace 关联的业务运行状态。两者的持久化衔接需通过接口明确。

## 公共目录

| 目录 | 用途 |
| --- | --- |
| `docs/requirements/` | 后续需求整理 |
| `docs/architecture/` | 架构、目录和接口边界说明 |
| `docs/decisions/` | 架构决策记录 |
| `migrations/` | 数据库迁移 |
| `tests/` | 跨模块集成、契约、端到端与全仓库架构测试 |
| `deploy/` | 本地与生产部署配置 |

外部论文搜索、内部混合检索、文件解析和成果渲染的具体目录，留到相关接口和责任归属讨论时细化。

## 测试归属

测试先按所属应用或包组织，再根据需要按测试类型细分。所有 `apps/` 和 `packages/` 下的模块都已建立自己的 `tests/` 目录。

```text
paper_helper/
├── apps/
│   ├── paper_helper_agent/
│   │   └── tests/           # 科研策略、上下文选择、输出校验与 Agent 评估
│   └── mcp_server/
│       └── tests/           # MCP 工具 Schema、身份传播、参数与后端适配
├── packages/
│   ├── harness_core/
│   │   └── tests/           # 通用运行循环、工具执行、取消与重试
│   └── research/
│       └── tests/           # 提议、版本、证据、审查、回滚与持久化
└── tests/
    ├── integration/        # Agent → MCP → API 等跨模块协作
    ├── contracts/          # 跨进程 HTTP、MCP、事件契约的兼容性
    ├── e2e/                # 上传材料 → 分析 → 审查 → 成果生成
    └── architecture/       # 全仓库依赖方向和模块隔离约束
```

上图展示部分模块；其余应用和包遵循相同规则。单个模块自身的集成或契约测试仍放在该模块的 `tests/`，例如 Research Repository 的数据库集成测试放在 `packages/research/tests/`。

`apps/mcp_server/tests/` 验证 Paper Helper 的领域工具服务；`packages/harness_mcp/tests/` 验证通用 MCP 客户端适配器，测试责任分别归属各自模块。

开始编写测试时，再按实际需要在模块内增加 `unit/`、`integration/`、`contracts/` 或 `evaluations/`。后续测试命令应支持单独运行一个模块，也支持在 CI 中统一收集整个 Monorepo 的测试。

当前测试目录仅包含 `.gitkeep` 占位文件，尚未编写测试用例或测试运行配置。

## 核心边界

- 前端通过 Research API 访问业务状态。
- 科研 Agent 依赖通用 Harness，并通过 MCP 工具调用后端。
- MCP Server 做协议适配，通过后端公开的应用接口执行业务操作。
- Harness 和 MCP Server 不直接访问业务数据库。
- 业务模块拥有各自的数据与事务规则，通过应用接口或稳定端口协作。
- 通用 Harness 不包含论文、Workspace 或研究状态等领域类型。

## 仓库组织方式

当前采用 Monorepo（单仓多包）目录结构：上述目录在一个 Git 仓库中共同提交和管理版本，各运行进程分别启动与部署。

如果通用 Harness 需要立即供其他项目使用，可以将 `harness_core` 与 `harness_mcp` 调整到独立仓库；主项目通过包依赖使用它们。目录调整应在 Git 初始化之前完成。

首版使用一个远端 Git 仓库管理整个项目。远端平台、账号或组织、仓库名和可见性在首次推送前确定。
