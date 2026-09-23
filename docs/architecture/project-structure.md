# 目录结构与服务边界

## 总体原则

Paper Helper 使用一个 Monorepo 管理多个独立部署单元：

- `backend/services/` 是拥有业务数据的 Python 微服务。
- `backend/gateways/mcp_gateway/` 是无状态 MCP 协议网关，不拥有业务规则或业务表。
- `agent/` 是 TypeScript Agent Runtime workspace。
- `contracts/` 保存 OpenAPI、JSON Schema、MCP Schema 与版本化事件契约。

微服务边界由数据所有权和协议定义，而不是由目录名称定义。每个业务服务拥有独立
Python package、依赖声明、ORM metadata、Migration chain、测试和部署制品。服务之间
禁止源码依赖、跨库查询和跨库外键。

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

根目录 `tests/` 只保存跨运行时契约、集成、端到端和部署验收测试。服务内部测试放在
对应服务目录；Backend 的静态架构约束放在 `backend/tests/architecture/`。

## Python Backend workspace

```text
backend/
├── packages/
│   └── platform_messaging/         # 无业务语义的 Python RabbitMQ 传输能力
├── services/
│   ├── research_core/              # Workspace、Research、Artifacts
│   │   ├── src/research_core/
│   │   ├── migrations/
│   │   ├── alembic.ini
│   │   ├── tests/
│   │   └── pyproject.toml
│   ├── knowledge_service/          # Sources、Ingestion、Retrieval
│   └── interaction_service/        # Conversations、Agent Runs
├── gateways/
│   └── mcp_gateway/                # FastMCP、Run Identity、Tool Schema
├── scripts/
├── tests/architecture/
├── pyproject.toml                  # uv workspace 与统一开发工具
└── uv.lock
```

`research_core` 暂时把 Workspace、Research 和 Artifacts 放在同一部署边界，因为三者有
紧密的权限和事务约束。`knowledge_service` 统一拥有来源、文档、解析状态和检索索引；
HTTP 入口与 ingestion worker 是同一服务的不同进程。`interaction_service` 统一拥有
Conversation、Message、Agent Run 和持久化 Run Event。

MCP Gateway 没有自己的业务数据库，通过版本化 HTTP 或消息契约调用服务，不得 import
服务实现包。浏览器请求由部署层反向代理按路径转发到业务服务自己的 HTTP/SSE 入站
Adapter，不设置独立 Python Web Gateway。

## 服务内部 DDD 结构

服务中可以包含少量强耦合的业务模块，每个模块使用以下结构：

```text
research_core/
├── workspace/
│   ├── domain/                     # Aggregate、Entity、VO、领域事件、规则
│   ├── application/                # Command、Query、DTO、Port、用例事务
│   └── adapters/                   # 模块专属入站/出站 Adapter
├── research/
│   ├── domain/
│   ├── application/
│   └── adapters/
├── artifacts/
│   ├── domain/
│   ├── application/
│   └── adapters/
├── adapters/outbound/persistence/  # 服务私有 ORM Base 与基础持久化适配
└── bootstrap/                      # API、Worker 与依赖注入 composition root
```

依赖方向为：

```text
Inbound Adapter -> Application -> Domain
Outbound Adapter ---------> Application/Domain Port
Bootstrap ----------------> 所有层，仅负责装配
```

Domain 不得依赖 FastAPI、FastMCP、SQLAlchemy、RabbitMQ/Redis Client、Pydantic 或模型
SDK。Application Service 定义用例和单服务事务边界；Repository Protocol 位于 Domain
或 Application，具体实现位于 Outbound Adapter。

## 服务数据与通信边界

- `research_core` 只访问 Research Core 数据库。
- `knowledge_service` 只访问 Knowledge 数据库和其拥有的对象存储前缀、检索索引。
- `interaction_service` 只访问 Interaction 数据库和运行事件流。
- 跨服务引用只保存 UUID、版本号和必要的不可变快照，不建立数据库外键。
- 同步查询使用版本化 HTTP API；跨服务状态传播使用 Outbox 与幂等消费者。
- 一个服务不能 import 另一个服务的 Domain、Application、Repository 或 ORM。
- 可生成的客户端和类型来自根目录 `contracts/`，不能复制 DTO 后独立演化。

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

Agent Worker 只能通过 MCP、受限 Runtime API 和版本化消息与 Backend 协作，不能连接任一
业务数据库。`harness-core` 仍保持领域无关。

## 测试归属

- `backend/services/<service>/tests/unit/`：Domain 与 Application 测试。
- `backend/services/<service>/tests/integration/`：Repository、数据库和消息 Adapter。
- `backend/gateways/mcp_gateway/tests/`：MCP Schema、身份和错误映射。
- `backend/tests/architecture/`：服务隔离、Domain 纯度和数据所有权。
- `tests/contracts/`：OpenAPI、JSON Schema、MCP 与事件兼容性。
- `tests/integration/`：跨服务真实协议调用。
- `tests/e2e/`：用户业务验收链路。

## 共享代码规则

不要建立包含 Entity、DTO、Repository 或数据库模型的 `common` 包。只有日志、Tracing、
认证中间件和 Event Envelope 等纯技术能力在出现两个以上真实使用方后，才允许进入
版本化 platform library。共享业务含义必须进入契约，不能进入共享运行时代码。

RabbitMQ 的 Python 连接、publisher confirm、manual ack 与通用重试机制位于
`backend/packages/platform_messaging/`。具体消息 Payload、Consumer Handler、Outbox/Inbox
ORM 与幂等规则仍属于各业务服务；TypeScript Agent 只共享 `contracts/events/` 契约，不依赖
Python package。
