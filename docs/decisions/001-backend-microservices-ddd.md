# ADR 001: Backend 采用数据所有权明确的 DDD 微服务

- 状态：Accepted
- 日期：2026-09-22

## 背景

早期方案将所有 Python 业务模块放在一个 distribution 和一个数据库 migration chain
中，并让 FastAPI 与 FastMCP 进程内调用共享 Application Service。该方案适合模块化单体，
但不能提供独立数据所有权、发布和故障隔离。

## 决策

Backend 改为 uv workspace 管理的微服务 Monorepo：

- Research Core 拥有 Workspace、Research State 与 Artifact。
- Knowledge Service 拥有 Source、Document、Ingestion 与 Retrieval。
- Interaction Service 拥有 Conversation、Agent Run 与持久化 Run Event。
- 各业务服务提供自己的 HTTP/SSE 入站接口，反向代理只负责路由。
- MCP Gateway 无状态，不承载领域规则。
- 每个业务服务拥有独立 package、ORM metadata、Migration chain 和数据库。
- 服务间只能通过版本化 HTTP、消息和根目录契约通信，禁止源码依赖和跨库访问。

服务内部采用 DDD 与 Ports and Adapters。Domain 保持框架无关，Application 负责用例和
本地事务，Adapters 处理协议与基础设施，Bootstrap 只负责装配。

## 结果

优点是数据所有权、发布边界和扩容模型明确，Knowledge ingestion 与 Agent runtime 可独立
扩容。代价是必须处理契约兼容、最终一致性、Outbox/Inbox、分布式可观测性和更多部署制品。

Workspace、Research 与 Artifact 暂时共处 Research Core；Conversation 与 Agent Run 暂时
共处 Interaction Service。只有出现稳定 API、不同扩容或故障模型、独立团队所有权时才
继续拆分，避免形成微服务数量与领域名词一一对应的分布式单体。
