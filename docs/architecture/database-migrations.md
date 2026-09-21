# Database migration policy

Paper Helper 的每个数据所有者服务维护独立、只前进的 Alembic revision chain。不存在
Backend 全局 metadata 或全局 migration head。

| 服务 | 配置 | 数据库环境变量 |
|---|---|---|
| Research Core | `services/research_core/alembic.ini` | `PAPER_HELPER_RESEARCH_CORE_DATABASE_URL` |
| Knowledge Service | `services/knowledge_service/alembic.ini` | `PAPER_HELPER_KNOWLEDGE_DATABASE_URL` |
| Interaction Service | `services/interaction_service/alembic.ini` | `PAPER_HELPER_INTERACTION_DATABASE_URL` |

每个 URL 必须显式使用 `postgresql+asyncpg`。应用进程不会创建数据库，也不会在启动时
自动执行 Migration。

## Developer workflow

命令从仓库根目录执行：

```bash
make migration-heads
make migration-revision service=research_core m=add_workspace
make migration-upgrade
make migration-check
```

`migration-heads` 检查所有服务。创建或合并 revision 时必须通过 `service=` 明确数据
所有者：

```bash
make migration-merge service=knowledge_service m=merge_document_heads
```

当前合法服务名是 `research_core`、`knowledge_service` 和 `interaction_service`。

## Ownership rules

- Revision 只能修改所属服务的表、索引、扩展和 schema。
- 服务不能在 migration 中连接其他服务数据库。
- 禁止创建跨服务外键、视图或直接读取其他服务表的触发器。
- 跨服务数据修复通过版本化 API、事件重放或显式运营任务完成。
- Revision 不得 import 可变的 Domain、Application Service、ORM model 或 initializer。
- 已合并的 revision 不可修改；使用新的 forward revision 修正。

每个自动生成的 revision 都必须检查表所有权、约束名、索引、默认值、锁行为和数据丢失
风险。大规模或外部可见的 backfill 应作为可观测、可恢复的独立 job 执行。

## Revision graph

服务尚未添加 ORM model 时允许零个 head。第一个 revision 产生后，每个服务必须恰好有
一个 head。并行开发产生多个 head 时，只能在同一服务内部显式 merge；不同服务的 head
彼此无关。

## Compatibility and deployment

生产变更使用 expand/contract：

1. 添加向后兼容结构。
2. 部署兼容新旧结构的代码。
3. 执行有界、可观测的 backfill。
4. 在后续版本收紧约束并删除旧结构。

部署时，每个服务由自己的 pre-start migration job 执行 `alembic upgrade head`。一个服务
Migration 失败只阻止该服务的新版本启动，不允许由 MCP Gateway 或其他服务代为迁移。

Downgrade 不是生产回滚机制。优先回滚到兼容的应用版本，再发布纠正性的 forward
revision。
