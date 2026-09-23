# ADR 002：RabbitMQ 消息可靠性与拓扑

- 状态：Accepted
- 日期：2026-09-22

## 背景

Paper Helper 需要在 Python 业务服务、Python Worker 和 TypeScript Agent Worker 之间传递
可靠的 Command/Event。消息链路必须允许服务独立部署，并正确处理发布进程崩溃、消费者
重复投递、临时故障、毒消息和契约演进。

RabbitMQ 不是业务状态来源。任务、幂等结果、关键 RunEvent 和恢复检查点仍由对应服务的
PostgreSQL 保存。

## 决策

### 投递语义

端到端采用 at-least-once，不承诺 exactly-once。业务服务通过 Transactional Outbox 发布；
Publisher 使用 mandatory routing、persistent message 和 publisher confirms。Consumer 使用
manual ack，并且只在本地事务成功后确认消息。消费者通过 Inbox 或业务唯一约束处理重复。

### Exchange 与 Routing Key

平台提供三个 durable topic exchange：

- `paper_helper.commands`
- `paper_helper.events`
- `paper_helper.dead_letters`

Routing key 使用 `<bounded-context>.<subject>.<verb>.v<major>`。Command 绑定到一个逻辑
消费队列，多实例竞争消费；Event 的每个订阅方拥有独立队列。Publisher 不知道 Queue 名称。

### Queue 所有权

Broker 部署层创建 vhost、exchange 和 policy。每个 Consumer 通过代码幂等声明自己的 main、
retry 和 dead-letter Quorum Queue 及 binding。所有队列以 `paper_helper.` 开头，从而统一应用
容量、delivery limit、reject-publish 和 at-least-once dead-letter policy。

### 重试

首版采用 Consumer 私有的 TTL Retry Queue，默认延迟为 10 秒、60 秒和 300 秒。Consumer 把
临时失败消息 confirmed publish 到下一条 Retry Queue 后，才 ack 原消息。Retry Queue 到期后
通过 default exchange 精确返回原 Main Queue，不重新广播 Event。

Schema 错误和确定性业务错误直接 reject 到 DLQ；超过最大重试次数的临时错误也进入 DLQ。
DLQ 不自动回放。需要长时间等待、外部限流或人工恢复的业务任务，应把 `next_attempt_at` 和
检查点写入权威数据库，而不是无限占用或循环 RabbitMQ delivery。

### 契约

消息使用根目录 `contracts/events/` 中的 JSON Schema。Envelope 至少包含 message identity、
kind、type、schema version、发生时间、producer、correlation/causation、actor、aggregate 和
payload。Routing key 的 major version 与 envelope 的 `schema_version` 一致。

单条消息上限为 256 KiB。凭据、论文全文和模型完整输入不得进入消息；大对象通过 S3 object
key、版本与 checksum 引用。

### 代码边界

Python 通用传输机制位于 `backend/packages/platform_messaging`，但业务 Handler、消息 Payload、
Outbox/Inbox ORM 和 Migration 留在数据所有者服务。TypeScript Agent Worker 使用自己的 AMQP
Adapter，只共享 JSON Schema，不共享 Python 运行时代码。

## 结果

系统接受重复投递，并要求所有副作用具备幂等保护。发布成功但 Outbox 尚未标记时可能重复发布；
Consumer 事务提交但 ack 丢失时也可能重复消费。这两种情况均不得产生重复业务结果。

每个 Consumer 会额外产生 Retry/DLQ Queue，换取事件重试时不影响其他订阅者。未来只有在队列
数量或延迟策略成为实际瓶颈时，才评估 RabbitMQ 4.3 delayed retry 或独立调度器。
