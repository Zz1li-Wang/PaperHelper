# Paper Helper 技术选型与基础设施基线

用于约束 MVP 阶段的语言、框架、中间件、协议和部署选择，并明确每个组件的职责边界。

| 文档属性 | 内容 |
|---|---|
| 版本 | v0.1 |
| 状态 | 开发基线 |
| 最后更新 | 2026-09-15 |
| 适用阶段 | MVP 到可演进模块化单体 |
| 关联文档 | Paper_Helper_技术架构与开发设计_v0.3.md |

# 1 选型结论

Paper Helper 采用双运行时结构。Agent Runtime、Paper Helper Agent 与 Harness Core 使用 TypeScript/Node.js；Paper Helper Backend、FastAPI、FastMCP 与 Ingestion 使用 Python。TypeScript 与 Python 不共享运行时代码，跨语言边界通过 MCP、HTTP/OpenAPI 和版本化消息契约连接。

Python Backend 是业务事实来源。FastAPI 与 FastMCP 是同一个 Backend 的并列 Gateway Adapter，都只能调用 Application Service，不直接访问 Repository，也不相互转发。MCP 的作用是定义 Agent 可调用的受控领域能力，而不是建立第二套 Backend。

PostgreSQL 是唯一权威业务数据库；RabbitMQ 是可靠跨进程消息通道；Redis 保存可丢失、可重建或短生命周期状态；S3 Compatible Object Storage 保存大对象。任何业务事实都不能只存在 RabbitMQ、Redis 或对象存储元数据之外。

# 2 技术基线

| 领域 | 选择 | 状态 | 边界 |
|---|---|---|---|
| Agent 语言 | TypeScript | Accepted | Paper Helper Agent、Harness Core、Agent Worker |
| Agent Runtime | Node.js LTS | Accepted | 不绑定 Bun/Deno 特性 |
| TS 包管理 | pnpm workspace | Accepted | 管理 Agent monorepo packages |
| Backend 语言 | Python | Accepted | Application、Domain、Infrastructure、Ingestion |
| HTTP Gateway | FastAPI + Pydantic v2 | Accepted | 只做 HTTP Adapter、认证入口、DTO 转换、SSE |
| MCP Gateway | FastMCP | Accepted | 只做 MCP 协议、Run Identity、Tool Schema、Application Service 适配 |
| ORM | SQLAlchemy 2 Async | Accepted | 仅 Infrastructure/Repository 使用 |
| Migration | Alembic | Accepted | PostgreSQL schema migration |
| 数据库 | PostgreSQL | Accepted | 唯一权威业务状态、事务、JSONB、FTS |
| 向量能力 | pgvector | Accepted | 与 PostgreSQL FTS 组成首版混合检索 |
| Message Broker | RabbitMQ | Accepted | 跨进程 Command/Event、ack、retry、DLQ、backpressure |
| Cache / Ephemeral | Redis | Accepted | cache、rate limit、短期 lease、Redis Stream 实时输出 |
| Object Storage | S3 Compatible | Accepted | PDF、DOCX、PPTX、网页快照、RenderResult |
| 本地对象存储 | MinIO | Accepted for local | 仅作为 S3 Compatible 的本地实现 |
| 浏览器实时通信 | SSE | Accepted | 服务器到浏览器单向流；普通操作继续 HTTP |
| Observability | OpenTelemetry + structured logging | Accepted | trace/request/run/event 关联 |
| 容器化 | Docker | Accepted | 各运行单元独立镜像 |
| 本地编排 | Docker Compose | Accepted | PostgreSQL、RabbitMQ、Redis、MinIO 与应用进程 |
| Kubernetes | 不引入 | Deferred | 出现多机调度和自动扩缩容需求后再评估 |
| 独立向量数据库 | 不引入 | Deferred | pgvector 无法满足规模或召回需求后再评估 |
| Elasticsearch/OpenSearch | 不引入 | Deferred | PostgreSQL FTS 不满足检索需求后再评估 |
| Kafka | 不引入 | Deferred | RabbitMQ 无法满足吞吐或日志流场景后再评估 |
| Temporal | 不引入 | Deferred | 长时 durable workflow、补偿和人工恢复成为稳定需求后评估 |
| Neo4j | 不引入 | Deferred | 产品验证知识图谱价值后再评估 |

前端框架当前不作为这份基线的强制决策。Web Client 与 Agent Runtime 都可以使用 TypeScript，但二者不应因此共享领域状态实现；可共享的只能是经过稳定契约定义的纯类型或生成代码。

# 3 运行单元

MVP 的主要应用进程为 `web_api`、`mcp_server`、`agent_worker` 和 `ingestion_worker`。`web_api` 与 `mcp_server` 虽然可独立部署，但都属于 Python Paper Helper Backend 的 composition root，并共享同一套 Application/Domain packages。`agent_worker` 属于 TypeScript Agent System；`ingestion_worker` 属于 Python Backend/Processing System。

```text
Web Client
    │ HTTP / SSE
    ▼
FastAPI Adapter ───────────────┐
                              │
TypeScript Agent              │
    │ MCP                     ▼
    └──────────────► FastMCP Adapter
                         │
                         ▼
                Application Services
                         │
                         ▼
                       Domain
                         │
                         ▼
              Repository / Infrastructure
                         │
                         ▼
                    PostgreSQL
```

这里不存在 `FastMCP -> FastAPI -> Application Service` 的链路。FastMCP 与 FastAPI 直接进入同一个 Application Service。

# 4 PostgreSQL

PostgreSQL 保存所有需要事务一致性、长期恢复、审计和业务查询的数据，包括 Workspace、Membership、Source、Document、Chunk、Research State、Revision、Evidence、Proposal、Artifact、Conversation、Message、AgentRun、关键 RunEvent、Outbox、Inbox 和 AuditLog。

PostgreSQL 是系统唯一权威状态源。Redis 中的缓存或流丢失不能改变业务结果；RabbitMQ 中的消息被重复投递不能产生重复 Revision 或重复 Artifact；S3 中的文件必须通过数据库中的对象元数据和业务引用访问。

首版检索使用 PostgreSQL metadata filter、全文检索和 pgvector，再执行融合排序。只有真实数据证明 PostgreSQL 在召回率、索引规模或延迟上不满足要求时，才拆出独立 Search Infrastructure。

# 5 RabbitMQ

RabbitMQ 负责所有需要可靠交付、消费确认、重试、死信和背压的跨进程消息。它既可以承载 Command，也可以承载 Event，但二者语义必须区分。

Command 表达“要求一个目标消费者执行动作”，例如 `agent.run.requested`、`ingestion.requested`、`artifact.render.requested`。Event 表达“业务事实已经发生”，例如 `document.ready`、`research_state.changed`、`artifact.rendered`。Command 与 Event 应使用不同 routing key 和 queue 拓扑，不能退化成一个无语义的通用 task queue。

Backend 在 PostgreSQL 本地事务中同时提交业务状态和 Outbox。Outbox Publisher 再把消息发布到 RabbitMQ。消费者只有在自己的本地事务成功提交后才 ack；重复投递通过 Inbox 或业务幂等键处理。RabbitMQ 的 delivery guarantee 不能替代业务幂等。

# 6 Redis

Redis 不作为 Paper Helper 的权威任务队列，也不保存不可恢复的业务事实。其用途限定为缓存、限流计数、短期 lease/协调、短生命周期 lookup，以及 Agent 实时输出的 Redis Stream。

高频 token 流、阶段提示等可以直接写 Redis Stream，因为这类数据允许在基础设施故障时损失。关键 Run 状态、错误、工具调用摘要、等待用户状态和最终状态必须最终进入 PostgreSQL。浏览器断线恢复时先读取 PostgreSQL 的关键事件，再连接 Redis 中仍然存在的实时流。

如果未来引入 Redis 分布式锁，锁只能用于降低并发碰撞概率，不能代替 PostgreSQL 唯一约束、乐观锁、CAS 或幂等键。

# 7 S3 Compatible Object Storage

原始 PDF、Word、PPT、网页快照、解析中间大对象和 RenderResult 均进入 S3 Compatible Object Storage。数据库只保存 object key、content hash、mime type、size、version、checksum 和业务引用。

本地开发使用 MinIO。生产环境可以替换为任意满足所需 S3 API 子集的托管对象存储，不允许让领域层依赖某个云厂商专有 SDK。对象删除需要遵循数据库引用和异步清理策略，不能在业务软删除时直接物理删除仍被 Evidence 或 Artifact Revision 引用的对象。

# 8 Agent 与 Harness

`harness-core` 是领域无关 TypeScript runtime。它负责 Agent Loop、ModelProvider、ToolProvider、Run lifecycle、cancel/retry、stream event 和 tracing，但不能出现 Workspace、Paper、Research State、Evidence 等 Paper Helper 领域模型。

`paper-helper-agent` 在 Harness 之上实现科研任务语义，包括任务分类、Research Strategy、Context Request、Tool whitelist、输出校验和 Proposal 形成策略。它不能直接访问 PostgreSQL、Python Repository 或 ORM。

`harness-mcp` 实现 ToolProvider，通过 MCP Client 与 FastMCP 通信。替换 MCP SDK 或模型 Provider 时，不应要求迁移 Paper Helper 的业务数据。

# 9 FastAPI 与 FastMCP

FastAPI 和 FastMCP 都属于 Gateway Adapter。FastAPI 面向 Web/外部 HTTP Client，FastMCP 面向 Agent MCP Client。它们可以使用不同进程、端口和限流策略，但共享 Python Backend packages。

FastAPI Router 和 FastMCP Tool 都不得自行 commit，不得直接访问 ORM，不得复制业务校验。`web_api` 与 `mcp_server` 的 composition root 可以为了依赖注入装配 Repository、Unit of Work 和其他 infrastructure adapter，但 wiring 代码不得承载业务规则。权限、版本冲突、Evidence 归属、Proposal 状态机和事务边界统一放在 Application Service/Domain。

MCP Tool 集合应小于或等于 Backend 的业务能力集合。Backend 定义系统能做什么，MCP 定义 Agent 被允许做什么。管理员操作、强制修复、成员管理等能力不应因为 Backend 存在就自动暴露为 MCP Tool。

# 10 跨语言契约

TypeScript 与 Python 之间不共享源码类型。根目录 `contracts/` 保存语言中立契约。HTTP 接口以 OpenAPI 为基线；RabbitMQ 消息以版本化 JSON Schema/Event Envelope 为基线；MCP 能力以 Tool Schema 为基线。

契约至少携带 `schema_version`。RabbitMQ Envelope 建议统一包含 `event_id/message_id`、`message_type`、`message_kind`、`occurred_at`、`correlation_id`、`causation_id`、`actor` 和 `payload`。新增可选字段视为兼容变更；删除字段、修改枚举含义或改变字段语义必须升级版本。

禁止在 Python 中手写一份 DTO、在 TypeScript 中再独立维护一份同名 interface 并依赖人工保持同步。能够生成的类型应从 OpenAPI/JSON Schema 生成；无法生成时必须通过 contract test 检测漂移。

# 11 实时链路

Web Client 与 Web API 使用 SSE。用户请求、提交消息和状态修改继续走普通 HTTP。SSE 只承担服务端到浏览器的事件流，因此首版不需要 WebSocket。

推荐链路为：关键 RunEvent 从 Agent Worker 经 RabbitMQ 进入 Backend 并持久化 PostgreSQL；高频临时输出进入 Redis Stream；Web API 向浏览器发送 SSE。断线恢复依赖 PostgreSQL 的 sequence/last_event_id，而不是依赖 Redis 永久保存流。

# 12 可观测性

OpenTelemetry 从第一版进入基础设施，但不要求第一版同时部署完整观测平台。所有入口和异步消息至少传播 `trace_id`、`request_id`、`run_id`、`event_id/message_id`、`correlation_id`。日志输出结构化字段，不记录长期 Token、完整论文正文或未脱敏模型请求。

后续可以根据部署环境接入 Grafana/Tempo/Loki、Jaeger 或云厂商 Observability；这些后端产品不是当前架构契约的一部分。

# 13 本地开发与部署

```bash
docker compose up -d postgres rabbitmq redis minio

cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn apps.web_api.main:app --reload
uv run python -m apps.mcp_server
uv run python -m apps.ingestion_worker

cd ../agent
pnpm install
pnpm --filter agent-worker dev
```

本地基础设施统一由 Docker Compose 管理。应用可在容器外以开发模式运行，以保留热重载和调试体验。生产部署可以把四个应用进程分别容器化；是否进入 Kubernetes 不由“容器数量”决定，而由多机调度、自动扩缩容、发布和故障隔离需求决定。

# 14 当前仍需后续细化的决策

RabbitMQ 还需要形成 exchange、queue、routing key、retry、TTL、DLQ 和消费者并发策略；Redis Stream 需要确定 key 结构、MAXLEN、保留窗口和断线恢复规则；Agent Run 的 checkpoint 粒度与 Runtime API 还需要通过第一个长任务薄切片验证；pgvector 索引类型和参数必须由真实论文语料的召回/延迟评估确定；前端框架、反向代理和生产 Observability backend 当前不作为核心架构约束。

# 15 反向风险检查

这套方案最大的工程风险不是组件不足，而是同时维护 TypeScript 与 Python 两套运行时带来的契约、CI、构建和调试成本。因此双语言边界只有在保持协议清晰时才有价值。如果开发过程中出现大量跨语言同步 DTO、MCP Adapter 开始复制业务规则、或者 Agent Runtime 频繁需要直接读取数据库，就说明边界设计出了问题，而不是应该继续增加中间件。

RabbitMQ 与 Redis 同时存在也有职责重叠风险。判断原则是：需要可靠消费和业务重试的消息进入 RabbitMQ；允许丢失、可重建、面向实时体验的数据进入 Redis；需要长期正确性的状态进入 PostgreSQL。任何模糊场景优先回到这一原则判断。
