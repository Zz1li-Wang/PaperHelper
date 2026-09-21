# PaperHelper 

### `domain/`

保存纯业务模型和不变量，不依赖框架或外部服务：

- Entity：具有稳定身份的业务对象。
- Aggregate Root：聚合对外修改的入口；聚合根也是 Entity，不必重复放入两个目录。
- Value Object：无独立身份、按值比较的概念。
- Domain Service：无法自然归属某个实体的纯业务规则；仅在需要时创建。
- Domain Event：已经发生的业务事实。
- Repository 接口：以聚合根为单位定义持久化能力，不暴露 ORM。

### `application/`

保存用例编排和事务边界：

- `commands/`：表达业务意图的写用例，例如接受 Proposal。
- `queries/`：读取和组合查询，例如获取 Research Context。
- `handlers/` 或 `services/`：协调聚合、Repository、Port 和事务。
- `dto.py`：对外返回的稳定数据结构，不返回 ORM 对象。
- `ports.py`：外部能力或其他模块能力的抽象。
- `facade.py`：供其他业务模块调用的公开入口。

### `infrastructure/`

保存技术实现，例如 SQLAlchemy ORM、Repository 实现、Mapper、对象存储、消息、解析器和外部检索适配器。Repository 实现不得自行提交业务事务，也不得向上层返回 ORM 对象。


