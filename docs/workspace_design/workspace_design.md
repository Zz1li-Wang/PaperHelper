# Workspace 模块设计 v5

| 文档属性 | 内容 |
|---|---|
| 版本 | v5 |
| 状态 | P1 领域模型与副本生命周期规则已定稿（P0 工程约束与 P2 收敛项未完成，见 §21） |
| 最后更新 | 2026-09-28 |
| 主要读者 | 后端开发、Agent 开发 |

本版相对 v4 的定稿决策（1–6 领域模型，7–10 副本生命周期与合并规则，11 命名统一）：

| # | 决策 | 影响章节 |
|---|---|---|
| 1 | 焦点保留 FocusResource 实体，改用 ID 直指：`context.globalFocusId → FocusResource.id`、`Session.focusId → FocusResource.id`，去掉中间那层复用的 ResourceRef | §2 §3.3 §3.7 §3.8 §4 §5.4 §6.7–6.9 |
| 2 | 严格聚合边界：Session / FocusResource / ProducedResource 持 ownerId 为归属唯一真相源，工作空间不内嵌其列表，`Workspace.version` 不随其变更递增 | §3.3 §3.6 §3.7 §3.8 §13 §14 §19 |
| 3 | ResourceRef 版本原地更新：refId 稳定，历史由领域事件与审计承担 | §3.5 §15.4 §16.4 |
| 4 | 单一 type-specific status：删除 `LifecycleStatus`，active / inactive 视图由映射派生 | §3.1 §3.2 §5.2 §12 §13 |
| 5 | `RevisionStrategy` 收敛为 `follow / keep`；「锁定版本」= 显式写 `ref.revision` | §3.1 §3.11 §16 §17.4 |
| 6 | 状态 × 动作约束表定稿：归档只读、终态封禁 | §5.2 §7.4 §9 §10 §17.7 |
| 7 | 主体删除不连带处置副本：副本保持 active 可继续独立工作，关停由主体所有者显式 `RevokeReplica` | §6.4 §12 §17.7 |
| 8 | 合并冲突项留在 MergeRequest 内作为记录，MR 审查后恒为 approved / rejected；重复引用判定为幂等命中，不算冲突 | §5.1 §18.3 §18.4 |
| 9 | 删除 `SyncMode.replace`；重置副本通过新建 Share 实现 | §3.1 §3.11 §17.3 |
| 10 | `merged` 从副本状态降级为事件标记（mergedAt + lastMergeRequestId）；补 `replica:restore` 与 `RestoreReplica` | §3.1 §3.2 §5.1 §5.2 §6.1 §7.1 §7.3 §7.4 §9 §10 |
| 11 | `Container` 概念并入 `Workspace`：统一抽象改名为 Workspace（`SubjectWorkspace` / `ReplicaWorkspace` 分支），标识符统一 `workspaceId`（对齐 system-design 的跨服务主键），快照改 `WorkspaceSnapshot`，动作收敛为 `workspace:*` / `replica:*` | 全文档 |

## 1. 定位

Workspace 属于 Research Core，是研究项目的主体工作空间。本版核心：

- 统一 Workspace 抽象，type 区分 workspace / replica
- ResourceRef 独立引用，支持重复、追溯、失效
- 焦点指向引用：FocusResource 指向工作空间内的一条引用，工作空间与会话只保存焦点指针
- 显式同步：副本按需从主体拉取更新
- 焦点同步为可选：默认不同步，需显式开启
- 合并单向：副本产出通过 MergeRequest 回主体
- 版本归资源模块，Workspace 只存 revision

职责：

- 工作空间生命周期：创建、更新、归档、恢复、删除、转移所有权（workspace）；撤销、合并（replica）
- 主体上下文：资源引用与全局焦点指针
- 独立聚合：会话、焦点资源、产出资源各自持有归属工作空间，按 ownerId 查询
- 转发分享：生成副本与访问入口
- 副本管理：上下文隔离、资源可重复引用、副本产出
- 显式同步：副本按需从主体拉取更新（含可选焦点同步）
- 合并：副本产出请求合并回主体
- 会话：工作空间下可有多个 Session
- 权限：基于 owner / replica_visitor / public_visitor

核心原则：

1. 统一工作空间抽象，不统一语义约束。
2. 主体是权威上下文，持续演进；副本创建时复制，之后隔离。
3. 副本独立于主体存在。主体删除后，副本数据不被级联删除，副本可继续独立工作。
4. 资源可重复引用，通过 refId 区分。
5. 焦点指向引用，不复制资源：`FocusResource.refId` 指向本工作空间内的一条 ResourceRef，焦点不可嵌套焦点。
6. 引用独立于资源与工作空间。
7. 版本归资源模块，Workspace 只存 revision；revision 为整数版本号。
8. 同步显式化，副本不自动拉取。
9. 焦点同步为可选，默认关闭。
10. 合并单向。
11. 不引入用户管理：actorId 仅作标识保存，本模块不校验其存在性。
12. type-specific 字段不扁平化：meta 内联在各自分支类型，公共字段不出现可空 meta。
13. 子聚合只持 ownerId：Session / FocusResource / ProducedResource 的 ownerId 是归属的唯一真相源，工作空间不内嵌它们的列表。
14. 工作空间只有一个 type-specific status：粗粒度 active / inactive 视图由映射派生，不落库。
15. 引用版本原地更新：refId 稳定，历史由领域事件与审计承担。

---

## 2. 核心概念

| 概念 | 说明 |
|---|---|
| 工作空间（Workspace） | 统一抽象，type = workspace / replica |
| 主体（SubjectWorkspace） | type=workspace 的分支，下称主体 |
| 副本（ReplicaWorkspace） | type=replica 的分支，下称副本 |
| 工作空间上下文（WorkspaceContext） | 工作空间的资源引用与全局焦点指针 |
| 分享（Share） | 生成副本并提供访问入口，1 Share : 1 Replica |
| 资源引用（ResourceRef） | 对资源的一次引用记录，可重复、可追溯 |
| 引用来源（RefOrigin） | 引用的产生方式，可辨识联合：native / copied / merged |
| 产出资源（ProducedResource） | 工作空间内产出的资源，独立聚合 |
| 焦点资源（FocusResource） | 工作空间内的具名焦点，refId 指向本工作空间的一条引用 |
| 全局焦点指针（globalFocusId） | 工作空间当前焦点，指向 FocusResource.id |
| 会话焦点指针（focusId） | 会话当前焦点，指向 FocusResource.id |
| 会话（Session） | 工作空间内的会话单元，独立聚合 |
| 显式同步（Sync） | 副本按需从主体拉取更新，焦点同步为可选 |
| 合并请求（MergeRequest） | 副本产出请求合并回主体 |
| 合并项（MergeItem） | 合并请求中的单个产出 |

---

## 3. 领域模型

### 3.1 枚举

```text
WorkspaceType = workspace | replica

WorkspaceStatus = active | archived | deleted
ReplicaStatus   = active | archived | revoked

ShareStatus = active | expired | revoked

SessionStatus = active | archived | deleted
FocusStatus   = active | archived

ProducedResourceStatus = draft | ready | merge_requested | merged

MergeRequestStatus = pending | approved | rejected | merged
MergeItemStatus    = pending | approved | rejected | conflicted

ResourceType = research_state | document | artifact | conversation | run

Visibility = private | shared | public

Relation = owner | replica_visitor | public_visitor

ResourceRefStatus = active | stale | removed

RevisionStrategy = follow | keep
SyncMode = merge | selective
```

派生视图（不落库）：

```text
inactive(workspace) =
  workspace: archived | deleted
  replica:   archived | revoked
```

### 3.2 Workspace（discriminated union）

```text
Workspace = SubjectWorkspace | ReplicaWorkspace

SubjectWorkspace = 公共字段 + { type: "workspace", workspaceMeta: WorkspaceMeta }
ReplicaWorkspace = 公共字段 + { type: "replica",   replicaMeta: ReplicaMeta }
```

公共字段（两分支共有，**不含 meta**）：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 工作空间 ID |
| type | WorkspaceType | 是 | 判别字段 |
| name | string | 是 | 名称 |
| description | string? | 否 | 描述 |
| version | number | 是 | 工作空间聚合版本，仅工作空间自身与 context 变更递增（见 §13） |
| context | WorkspaceContext | 是 | 工作空间上下文 |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间 |

WorkspaceMeta：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ownerId | string | 是 | 所有者 ID |
| visibility | Visibility | 是 | private / shared / public |
| status | WorkspaceStatus | 是 | 细粒度状态 |
| archivedAt | timestamp? | 否 | 归档时间 |

ReplicaMeta：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| shareId | string | 是 | 所属分享 ID |
| sourceWorkspaceId | string | 是 | 来源主体 ID，允许已删除 |
| sourceContextVersion | number | 是 | 复制时主体上下文版本 |
| status | ReplicaStatus | 是 | 细粒度状态 |
| lastSyncedAt | timestamp? | 否 | 最近一次显式同步时间 |
| lastSyncedSourceVersion | number? | 否 | 同步时主体上下文版本 |
| lastSyncOptions | SyncOptions? | 否 | 最近一次同步选项（含 includeFocus） |
| archivedAt | timestamp? | 否 | 归档时间 |
| mergedAt | timestamp? | 否 | 最近一次合并完成时间（事件标记，非终态） |
| lastMergeRequestId | string? | 否 | 最近一次合并的 MergeRequest.id |
| revokedAt | timestamp? | 否 | 撤销时间 |

不变式：

```text
type = workspace => workspaceMeta 必填，replicaMeta 不存在
type = replica   => replicaMeta 必填，workspaceMeta 不存在

由分支类型内联 meta 保证：公共字段不出现 workspaceMeta? / replicaMeta? 这类可空字段。
```

### 3.3 WorkspaceContext

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| ownerType | WorkspaceType | 是 | 与工作空间 type 恒等，由聚合根写入 |
| ownerId | string | 是 | 与工作空间 id 恒等，由聚合根写入 |
| resourceRefs | ResourceRef[] | 是 | 资源引用，可重复 |
| globalFocusId | string? | 否 | 指向本工作空间内 FocusResource.id |
| version | number | 是 | 上下文版本 |
| updatedAt | timestamp | 是 | 更新时间 |

说明：

- WorkspaceContext 不是独立聚合，它随 Workspace 一起加载与保存，ownerType / ownerId 与工作空间恒等、不可独立变更。
- 会话、焦点资源、产出资源**不内嵌**于 context。它们各自持有 ownerType / ownerId，由工作空间 id 查询得到（见 §3.6 / §3.7 / §3.8）。
- `globalFocusId` 是唯一指针，不再经过一层 ResourceRef（v4 的 globalFocusRef 已废弃）。

### 3.4 Share

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 分享 ID |
| workspaceId | string | 是 | 来源主体 ID（type=workspace） |
| createdBy | string | 是 | 创建者 |
| shareToken | string | 是 | 分享令牌 |
| replicaId | string | 是 | 生成的副本 ID（1:1） |
| status | ShareStatus | 是 | active / expired / revoked |
| expiresAt | timestamp? | 否 | 可选过期时间 |
| createdAt | timestamp | 是 | 创建时间 |
| revokedAt | timestamp? | 否 | 撤销时间 |
| revokedBy | string? | 否 | 撤销者 |

说明：ShareStatus 只约束访问入口（AccessShare）。Share 过期或被撤销不驱动 ReplicaStatus，副本继续独立工作（见 §12）。

### 3.5 ResourceRef

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| refId | string | 是 | 引用 ID，工作空间内唯一 |
| type | ResourceType | 是 | 目标资源类型 |
| targetId | string | 是 | 目标资源 ID |
| revision | number? | 否 | 目标版本号；null = 跟随最新（见 §16） |
| origin | RefOrigin | 是 | 引用来源，见下 |
| status | ResourceRefStatus | 是 | active / stale / removed |
| staleReason | string? | 否 | 失效原因 |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间（revision 原地升级时刷新） |

RefOrigin（可辨识联合）：

```text
RefOrigin =
  | { kind: "native" }                                                    // 本工作空间内直接新增
  | { kind: "copied", sourceWorkspaceId: string }                         // 复制 / 同步自主体，允许主体已删除
  | { kind: "merged", sourceReplicaId: string, mergeRequestId: string }    // 由副本合并回主体产生
```

来源追溯：

| 场景 | 所在工作空间 | origin |
|---|---|---|
| 主体直接引入 | workspace | `native` |
| 副本创建时复制主体引用 | replica | `copied { sourceWorkspaceId: ws_1 }` |
| 副本显式同步拉取 | replica | `copied { sourceWorkspaceId: ws_1 }` |
| 副本内新增 | replica | `native` |
| 合并回主体 | workspace | `merged { sourceReplicaId: rp_1, mergeRequestId: mr_1 }` |

说明：

- 复制与同步拉取产生的引用在来源语义上等价（都是主体引用的快照），不做区分；若需区分时间，见 `replicaMeta.lastSyncedAt`。
- v4 表中「副本显式同步拉取焦点」一行属于 FocusResource 场景，已移入 §3.7 与 §5.4。
- 副本内新增的引用在合并回主体前不影响主体；合并后主体侧产生一条 `merged` 引用，副本侧原引用保持 `native` 不变。

### 3.6 ProducedResource

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 产出 ID |
| ownerType | WorkspaceType | 是 | workspace / replica |
| ownerId | string | 是 | 归属工作空间 ID（唯一真相源） |
| type | ResourceType | 是 | 资源类型 |
| targetId | string | 是 | 产出资源 ID |
| summary | string? | 否 | 摘要 |
| status | ProducedResourceStatus | 是 | draft / ready / merge_requested / merged |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间 |

说明：

- 独立的工作空间级聚合，工作空间不内嵌产出列表。
- 合并回主体时，主体侧只新增一条 `origin.kind = merged` 的 ResourceRef，**不复制 ProducedResource 实体**；产出实体始终归属产生它的工作空间。

### 3.7 FocusResource

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 焦点资源 ID |
| ownerType | WorkspaceType | 是 | 仅 workspace / replica |
| ownerId | string | 是 | 归属工作空间 ID（唯一真相源） |
| refId | string | 是 | 指向本工作空间内 status=active 的 ResourceRef.refId |
| sourceFocusId | string? | 否 | 同步复制来源的 FocusResource.id；本工作空间自建为 null |
| createdBy | string | 是 | 创建者 |
| status | FocusStatus | 是 | active / archived |
| version | number | 是 | 版本号 |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间 |

不变式：

```text
refId 必须指向同工作空间内 status = active 的 ResourceRef，跨工作空间引用一律拒绝。
refId 不指向 FocusResource（ResourceType 不含 focus），因此焦点天然不可嵌套。
ownerId 是归属唯一真相源，工作空间不内嵌 focusResources 列表。
```

### 3.8 Session

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 会话 ID |
| ownerType | WorkspaceType | 是 | workspace / replica |
| ownerId | string | 是 | 归属工作空间 ID（唯一真相源） |
| title | string | 是 | 会话标题 |
| createdBy | string | 是 | 创建者 |
| status | SessionStatus | 是 | active / archived / deleted |
| focusId | string? | 否 | 指向同工作空间内 FocusResource.id |
| version | number | 是 | 版本号 |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间 |
| archivedAt | timestamp? | 否 | 归档时间 |

不变式：`focusId` 必须指向同工作空间的 FocusResource。

### 3.9 MergeRequest

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 合并请求 ID |
| replicaId | string | 是 | 来源副本 |
| targetWorkspaceId | string | 是 | 目标主体（type=workspace，执行时必须 active） |
| targetWorkspaceVersion | number | 是 | 创建时目标主体的 Workspace.version，执行时比对 |
| items | MergeItem[] | 是 | 合并项列表 |
| status | MergeRequestStatus | 是 | pending / approved / rejected / merged |
| requestedBy | string | 是 | 请求者 |
| requestedAt | timestamp | 是 | 请求时间 |
| reviewedBy | string? | 否 | 审查者 |
| reviewedAt | timestamp? | 否 | 审查时间 |
| mergedAt | timestamp? | 否 | 合并时间 |

### 3.10 MergeItem

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| producedResourceId | string | 是 | 产出资源 ID |
| status | MergeItemStatus | 是 | pending / approved / rejected / conflicted |
| conflictReason | string? | 否 | 冲突原因 |

### 3.11 SyncOptions

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| mode | SyncMode | 是 | merge | merge / selective |
| resourceRefIds | string[]? | 否 | — | 选择性同步的 refId |
| targetIds | string[]? | 否 | — | 选择性同步的 targetId |
| revisionStrategy | RevisionStrategy | 是 | keep | follow / keep，见 §16 |
| includeFocus | boolean | 否 | false | 是否同步 FocusResource（含 globalFocusId 指针） |

说明：Session 焦点不参与同步，本版不支持 `includeSessionFocus`。如需支持，须先设计 Session 映射模型（见 §21）。

### 3.12 SyncResult

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| added | ResourceRef[] | 是 | 新增引用 |
| updated | ResourceRef[] | 是 | revision 原地更新 |
| skipped | ResourceRef[] | 是 | 跳过（keep） |
| conflicts | SyncConflict[] | 是 | 冲突项 |
| focusAdded | FocusResource[]? | 否 | 新增焦点（includeFocus=true 时，带 sourceFocusId） |
| focusUpdated | FocusResource[]? | 否 | 焦点 status 或 refId 变更 |
| focusSkipped | FocusResource[]? | 否 | 跳过焦点 |
| globalFocusUpdated | boolean? | 否 | 副本 globalFocusId 是否变化 |
| sourceVersion | number | 是 | 同步时主体上下文版本 |
| syncedAt | timestamp | 是 | 同步时间 |

焦点相关字段仅在 `includeFocus = true` 时出现。

### 3.13 SyncConflict

| 字段 | 类型 | 说明 |
|---|---|---|
| refId | string | 副本引用 ID |
| targetId | string | 目标资源 |
| reason | string | revision 冲突 / 资源不可用 / 来源已删除 |

### 3.14 WorkspaceSnapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspace | Workspace | 是 | 工作空间信息 |
| context | WorkspaceContext | 是 | 工作空间上下文（resourceRefs + globalFocusId） |
| sessions | Session[]? | 否 | 会话列表，按 ownerId 查询组装 |
| focusResources | FocusResource[]? | 否 | 焦点资源列表，按 ownerId 查询组装 |
| actor | ActorView | 是 | 当前操作者视图 |
| availableActions | string[] | 是 | 权限矩阵 × 状态约束下的允许动作（见 §7.4） |
| version | number | 是 | 快照版本 |

ActorView：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| actorId | string | 是 | 操作者 ID |
| relation | Relation | 是 | owner / replica_visitor / public_visitor |
| permissions | string[] | 是 | 权限动作列表 |
| shareId | string? | 否 | 通过分享访问时填 |
| replicaId | string? | 否 | 通过副本访问时填 |

---

## 4. 数据流

```text
Workspace (type=workspace)
├── workspaceMeta: { ownerId, visibility, status, ... }
├── context: WorkspaceContext
│   ├── resourceRefs: ResourceRef[]           // 每条带 origin
│   └── globalFocusId -> FocusResource.id
├── sessions: Session[]                       // 按 ownerId 查询
│   └── focusId -> FocusResource.id
├── focusResources: FocusResource[]           // 按 ownerId 查询
│   └── refId -> context.resourceRefs[].refId
├── producedResources: ProducedResource[]     // 按 ownerId 查询
└── shares: Share[]
    └── replica: Workspace (type=replica)   // 1:1
        ├── replicaMeta: { shareId, sourceWorkspaceId, sourceContextVersion,
        │                   lastSyncedAt, lastSyncedSourceVersion, lastSyncOptions, ... }
        ├── context: WorkspaceContext
        ├── sessions / focusResources / producedResources
        └── mergeRequests

副本产出
└── ProducedResource
      └── MergeRequest (replicaId -> targetWorkspaceId, 目标主体须 active)
            └── MergeItem
                  └── MergeIntoWorkspace
                        └── 主体 context.resourceRefs 新增一条 origin.kind = merged 的引用

主体 -> 副本 显式同步
└── SyncFromSource (replicaId, options)
      ├── mode: merge | selective
      ├── revisionStrategy: follow | keep
      ├── includeFocus: false (default)
      └── 结果: added / updated / skipped / conflicts / focusAdded / globalFocusUpdated
```

---

## 5. 状态流转

### 5.1 MergeRequest / MergeItem / ProducedResource / Replica

| 阶段 | MergeRequest | MergeItem | ProducedResource | Replica |
|---|---|---|---|---|
| 创建请求 | pending | pending | merge_requested | active |
| 创建时检出真冲突 | pending | conflicted | ready | active |
| 创建时命中重复 | pending | approved（幂等命中） | merged | active |
| 审查通过 | approved | approved | merge_requested | active |
| 审查拒绝 | rejected | rejected | ready | active |
| 执行合并 | merged | approved | merged | active（刷新 mergedAt） |
| 副本撤销 | — | — | — | revoked |

规则：

- 每次合并成功刷新 ReplicaMeta.mergedAt 与 lastMergeRequestId，副本保持 active；merged 不是副本状态。
- MergeRequest.status = approved 不改变 Replica 状态。
- MergeItem.status = conflicted 的项不参与合并，其 ProducedResource 回到 ready，解决后可重新发起合并请求。
- 主体已有等价引用时判定为幂等命中，不视为冲突（见 §18.3）。
- MergeIntoWorkspace 执行时只要求目标主体 active，并按 targetWorkspaceVersion 复核（见 §18.4）。

### 5.2 工作空间生命周期

```text
workspace: active -> archived -> active
           active -> deleted
           archived -> deleted

replica:   active -> archived -> active
           active -> revoked
           archived -> revoked
```

规则：

- 终态：workspace = deleted；replica = revoked。合并不是状态（见 §5.1）。
- 无独立 lifecycle 字段；粗粒度视图由派生映射得到：

```text
inactive = workspace: archived | deleted
           replica:   archived | revoked
```

### 5.3 ResourceRef 状态

```text
active -> stale -> removed
active -> removed
```

### 5.4 焦点同步（可选）

```text
includeFocus = false（默认）:
  不同步 FocusResource，不修改副本 globalFocusId
  副本焦点完全自治

includeFocus = true:
  1. 主体新增 FocusResource 复制到副本（新 id，ownerId=副本，sourceFocusId=主体焦点 id，
     refId 指向副本内对应引用）
  2. 副本 globalFocusId 按 revisionStrategy 处理
  3. 主体已归档 FocusResource 在副本中标记 archived
  4. 不删除副本已有 FocusResource
  5. 不覆盖副本自建的 FocusResource（sourceFocusId = null）
  6. 不修改副本 Session 的 focusId（Session 焦点不参与同步）
```

revisionStrategy 对焦点的影响：

| 策略 | 行为 |
|---|---|
| follow | 副本 globalFocusId 对齐主体全局焦点（映射到副本侧对应 FocusResource） |
| keep | 不修改副本 globalFocusId，只同步主体新增 FocusResource |

---

## 6. 接口总览

### 6.1 工作空间生命周期

```text
CreateWorkspace (actorId, name, description, visibility) -> (workspace:create) -> WorkspaceSnapshot | 201
UpdateWorkspace (workspaceId, actorId, patch, expectedVersion?) -> (workspace:update) -> WorkspaceSnapshot | 200
ArchiveWorkspace (workspaceId, actorId, reason?, expectedVersion?) -> (workspace:archive) -> WorkspaceSnapshot | 200
RestoreWorkspace (workspaceId, actorId, expectedVersion?) -> (workspace:restore) -> WorkspaceSnapshot | 200
DeleteWorkspace (workspaceId, actorId, expectedVersion?) -> (workspace:delete) -> WorkspaceDeleted | 200
TransferOwnership (workspaceId, actorId, newOwnerId, expectedVersion?) -> (workspace:transfer_ownership) -> WorkspaceSnapshot | 200
RestoreReplica (replicaId, actorId, expectedVersion?) -> (replica:restore) -> WorkspaceSnapshot | 200
RevokeReplica (replicaId, actorId) -> (replica:revoke) -> WorkspaceSnapshot | 200
```

### 6.2 分享

```text
CreateShare (workspaceId, actorId, resourceRefs, expiresAt?) -> (share:create) -> Share | 201
GetShare (shareId, actorId?) -> (share:read) -> Share | 200
ListShares (workspaceId, actorId, status?, page?, pageSize?) -> (share:list) -> Share[] | 200
RevokeShare (shareId, actorId) -> (share:revoke) -> Share | 200
AccessShare (shareToken, actorId?) -> (share:access) -> WorkspaceSnapshot | 200
```

### 6.3 副本与资源引用

```text
GetReplica (replicaId, actorId?) -> (replica:read) -> WorkspaceSnapshot | 200
AddResourceRef (workspaceId, actorId, resourceRef) -> (workspace:add_ref) -> WorkspaceSnapshot | 200
RemoveResourceRef (workspaceId, actorId, refId, expectedVersion?) -> (workspace:remove_ref) -> WorkspaceSnapshot | 200
UpdateResourceRefRevision (workspaceId, actorId, refId, revision, expectedVersion?) -> (workspace:update_ref_revision) -> WorkspaceSnapshot | 200
CreateProducedResource (workspaceId, actorId, type, targetId, summary?) -> (workspace:produce) -> ProducedResource | 201
ListProducedResources (workspaceId, actorId, status?, page?, pageSize?) -> (workspace:list_produced) -> ProducedResource[] | 200
```

### 6.4 显式同步

```text
SyncFromSource (replicaId, actorId, options: SyncOptions) -> (replica:sync) -> SyncResult | 200
```

options 默认值：

```text
{
  mode: "merge",
  revisionStrategy: "keep",
  includeFocus: false
}
```

同步规则：

- 主体已删除 -> 返回 SOURCE_NOT_FOUND，副本继续独立工作。
- 主体已归档 -> 返回 WORKSPACE_ARCHIVED，副本继续独立工作。
- 主体引用已移除 -> 副本保留自己的引用，不级联删除。
- revision 冲突 -> 记入 conflicts，不自动解决。
- 权限：仅 owner 或 replica_visitor 可触发。
- 同步后更新 replicaMeta.lastSyncedAt / lastSyncedSourceVersion / lastSyncOptions。
- includeFocus = false 时，不返回 focusAdded / focusUpdated / globalFocusUpdated。

### 6.5 合并

```text
CreateMergeRequest (replicaId, actorId, producedResourceIds) -> (merge:create) -> MergeRequest | 201
ListMergeRequests (workspaceId, actorId, status?, page?, pageSize?) -> (merge:list) -> MergeRequest[] | 200
ReviewMergeRequest (mergeRequestId, actorId, decision, comment?) -> (merge:review) -> MergeRequest | 200
MergeIntoWorkspace (mergeRequestId, actorId) -> (merge:execute) -> WorkspaceSnapshot | 200
```

规则：

- CreateMergeRequest：来源副本与目标主体都必须 active。
- MergeIntoWorkspace：只要求目标主体 active（合并是主体侧动作，副本是否归档不阻断主体所有者的既有决策）。
- MergeRequest 记录创建时的 targetWorkspaceVersion，执行时比对，不一致返回 VERSION_CONFLICT。

### 6.6 会话

```text
CreateSession (ownerType, ownerId, actorId, title) -> (session:create) -> Session | 201
GetSession (ownerType, ownerId, sessionId, actorId?) -> (session:read) -> Session | 200
ListSessions (ownerType, ownerId, actorId, status?, page?, pageSize?) -> (session:list) -> Session[] | 200
UpdateSession (ownerType, ownerId, sessionId, actorId, patch, expectedVersion?) -> (session:update) -> Session | 200
ArchiveSession (ownerType, ownerId, sessionId, actorId, expectedVersion?) -> (session:archive) -> Session | 200
DeleteSession (ownerType, ownerId, sessionId, actorId, expectedVersion?) -> (session:delete) -> SessionDeleted | 200
```

### 6.7 焦点资源

```text
CreateFocusResource (ownerType, ownerId, actorId, refId) -> (focus:create) -> FocusResource | 201
GetFocusResource (focusId, actorId?) -> (focus:read) -> FocusResource | 200
ListFocusResources (ownerType, ownerId, actorId, status?, page?, pageSize?) -> (focus:list) -> FocusResource[] | 200
ArchiveFocusResource (focusId, actorId) -> (focus:archive) -> FocusResource | 200
```

`refId` 必须指向同工作空间内 active 的 ResourceRef，否则返回 INVALID_RESOURCE_REF。

### 6.8 全局焦点

```text
SetGlobalFocus (ownerType, ownerId, actorId, focusId) -> (focus:set_global) -> WorkspaceSnapshot | 200
ClearGlobalFocus (ownerType, ownerId, actorId, expectedVersion?) -> (focus:clear_global) -> WorkspaceSnapshot | 200
```

### 6.9 Session 焦点

```text
SetSessionFocus (ownerType, ownerId, sessionId, actorId, focusId) -> (focus:set_session) -> Session | 200
ClearSessionFocus (ownerType, ownerId, sessionId, actorId, expectedVersion?) -> (focus:clear_session) -> Session | 200
```

### 6.10 查询与快照

```text
GetWorkspace (workspaceId, actorId?) -> (workspace:read) -> Workspace | 200
GetWorkspaceSnapshot (workspaceId, actorId?) -> (workspace:read) -> WorkspaceSnapshot | 200
ListWorkspaces (actorId, filter?: { type?, status?, includeDeleted? }, page?, pageSize?) -> (workspace:list) -> Workspace[] | 200
```

### 6.11 权限校验

```text
CheckPermission (workspaceId, actorId, action, sessionId?, resourceRef?) -> (internal) -> PermissionDecision | 200
```

---

## 7. 权限

### 7.1 动作

```text
workspace:create / read / update / archive / restore / delete / transfer_ownership / list

share:create / read / list / revoke / access

replica:read / add_ref / remove_ref / update_ref_revision / produce / list_produced / archive / restore / revoke / sync

merge:create / list / review / execute

session:create / read / list / update / archive / delete

focus:create / read / list / archive / set_global / clear_global / set_session / clear_session
```

### 7.2 relation

```text
Relation = owner | replica_visitor | public_visitor
```

### 7.3 权限矩阵

| action | owner | replica_visitor | public_visitor |
|---|---|---|---|
| workspace:read | 是 | 否 | 是 |
| workspace:update | 是 | 否 | 否 |
| workspace:archive | 是 | 否 | 否 |
| workspace:restore | 是 | 否 | 否 |
| workspace:delete | 是 | 否 | 否 |
| workspace:transfer_ownership | 是 | 否 | 否 |
| share:create | 是 | 否 | 否 |
| share:read | 是 | 是 | 否 |
| share:list | 是 | 否 | 否 |
| share:revoke | 是 | 否 | 否 |
| share:access | 是 | 是 | 是 |
| replica:read | 是 | 是 | 是 |
| replica:add_ref | 否 | 是 | 否 |
| replica:remove_ref | 否 | 是 | 否 |
| replica:update_ref_revision | 否 | 是 | 否 |
| replica:produce | 否 | 是 | 否 |
| replica:list_produced | 是 | 是 | 否 |
| replica:archive | 否 | 是 | 否 |
| replica:restore | 否 | 是 | 否 |
| replica:revoke | 是 | 否 | 否 |
| replica:sync | 是 | 是 | 否 |
| merge:create | 否 | 是 | 否 |
| merge:list | 是 | 是 | 否 |
| merge:review | 是 | 否 | 否 |
| merge:execute | 是 | 否 | 否 |
| session:create | 是 | 是 | 否 |
| session:read | 是 | 是 | 是 |
| session:list | 是 | 是 | 是 |
| session:update | 是 | 是 | 否 |
| session:archive | 是 | 是 | 否 |
| session:delete | 是 | 是 | 否 |
| focus:create | 是 | 是 | 否 |
| focus:read | 是 | 是 | 是 |
| focus:list | 是 | 是 | 是 |
| focus:archive | 是 | 是 | 否 |
| focus:set_global | 是 | 是 | 否 |
| focus:clear_global | 是 | 是 | 否 |
| focus:set_session | 是 | 是 | 否 |
| focus:clear_session | 是 | 是 | 否 |

relation 与访问对象的对应：

- 访问**主体**（type=workspace）时：`owner` = 主体所有者；`public_visitor` = 通过分享入口进入的公共访问者。
- 访问**副本**（type=replica）时：`replica_visitor` = 副本使用者（分享接收者）；`owner` = 主体所有者，在副本上保留治理权（replica:read / list_produced / revoke / sync），内容写动作归 replica_visitor。

### 7.4 状态 × 动作约束

实际允许 = 7.3 权限矩阵 ∩ 本节状态约束。relation 与 status 正交，二者都必须通过。

```text
workspace active    : 全部动作
workspace archived  : workspace:read / restore / delete / transfer_ownership
                      share:read / list / revoke
                      session:read / list，focus:read / list
                      其余写动作返回 WORKSPACE_ARCHIVED
workspace deleted   : 全部动作返回 WORKSPACE_DELETED
                      （ListWorkspaces 可通过 includeDeleted 查看，见 §12）

replica active      : 按 7.3 权限矩阵
replica archived    : replica:read / archive / restore / revoke
                      session:read / list，focus:read / list
                      其余写动作返回 REPLICA_ARCHIVED
replica revoked     : 全部动作返回 REPLICA_REVOKED
```

说明：

- `share:access` 要求来源主体处于 active；主体归档或删除后拒绝新的分享访问。
- `sync` 要求来源主体 active：主体已删除返回 SOURCE_NOT_FOUND，已归档返回 WORKSPACE_ARCHIVED；副本自身状态仍按上表判定。
- `merge:create` 要求来源副本与目标主体都 active；`merge:execute` 只要求目标主体 active，并按 targetWorkspaceVersion 复核（见 §18.4）。
- `replica:revoke` 是主体所有者的治理动作，不受主体自身状态限制。

---

## 8. 事件

### 8.1 工作空间生命周期

```text
WorkspaceCreated / WorkspaceUpdated / WorkspaceArchived / WorkspaceRestored / WorkspaceDeleted
OwnershipTransferred
ReplicaRevoked
```

### 8.2 分享与副本

```text
ShareCreated / ShareRevoked / ShareExpired / ShareAccessed
ReplicaCreated
WorkspaceResourceRefAdded / WorkspaceResourceRefRemoved / WorkspaceResourceRefRevisionUpdated / WorkspaceResourceRefMarkedStale
ProducedResourceCreated
```

### 8.3 显式同步

```text
ReplicaSyncRequested { replicaId, options }
ReplicaSyncCompleted { replicaId, added, updated, skipped, conflicts,
                      focusAdded?, focusUpdated?, focusSkipped?, globalFocusUpdated?,
                      sourceVersion }
ReplicaSyncFailed { replicaId, reason }
```

### 8.4 合并

```text
MergeRequestCreated / MergeRequestReviewed / ReplicaMerged
```

### 8.5 会话

```text
SessionCreated / SessionUpdated / SessionArchived / SessionDeleted
```

### 8.6 焦点

```text
FocusResourceCreated / FocusResourceArchived
GlobalFocusSet / GlobalFocusCleared
SessionFocusSet / SessionFocusCleared
```

### 8.7 接口 -> 事件映射

| 接口 | 事件 |
|---|---|
| CreateWorkspace | WorkspaceCreated |
| UpdateWorkspace | WorkspaceUpdated |
| ArchiveWorkspace | WorkspaceArchived |
| RestoreWorkspace | WorkspaceRestored |
| DeleteWorkspace | WorkspaceDeleted |
| TransferOwnership | OwnershipTransferred |
| RevokeReplica | ReplicaRevoked |
| CreateShare | ShareCreated, ReplicaCreated |
| RevokeShare | ShareRevoked |
| AccessShare | ShareAccessed |
| AddResourceRef | WorkspaceResourceRefAdded |
| RemoveResourceRef | WorkspaceResourceRefRemoved |
| UpdateResourceRefRevision | WorkspaceResourceRefRevisionUpdated |
| SyncFromSource | ReplicaSyncRequested, ReplicaSyncCompleted / ReplicaSyncFailed |
| CreateProducedResource | ProducedResourceCreated |
| CreateMergeRequest | MergeRequestCreated |
| ReviewMergeRequest | MergeRequestReviewed |
| MergeIntoWorkspace | ReplicaMerged, WorkspaceUpdated |
| CreateSession | SessionCreated |
| UpdateSession | SessionUpdated |
| ArchiveSession | SessionArchived |
| DeleteSession | SessionDeleted |
| CreateFocusResource | FocusResourceCreated |
| ArchiveFocusResource | FocusResourceArchived |
| SetGlobalFocus | GlobalFocusSet |
| ClearGlobalFocus | GlobalFocusCleared |
| SetSessionFocus | SessionFocusSet |
| ClearSessionFocus | SessionFocusCleared |

---

## 9. 错误码

```text
VALIDATION_ERROR
WORKSPACE_NOT_FOUND
WORKSPACE_ARCHIVED
WORKSPACE_DELETED
PERMISSION_DENIED
VERSION_CONFLICT
INVALID_WORKSPACE_TYPE
INVALID_ACTION_FOR_TYPE

SHARE_NOT_FOUND
SHARE_EXPIRED
SHARE_REVOKED
INVALID_EXPIRES_AT

REPLICA_NOT_FOUND
REPLICA_ARCHIVED
REPLICA_REVOKED
SOURCE_NOT_FOUND
SYNC_CONFLICT
INVALID_SYNC_OPTIONS

RESOURCE_REF_NOT_FOUND
RESOURCE_REF_IN_USE
INVALID_RESOURCE_REF
REVISION_NOT_FOUND

PRODUCED_RESOURCE_NOT_FOUND
MERGE_REQUEST_NOT_FOUND
MERGE_REQUEST_ALREADY_REVIEWED
MERGE_REQUEST_NOT_APPROVED
INVALID_DECISION

SESSION_NOT_FOUND

FOCUS_NOT_FOUND

INVALID_ACTION
SERVICE_UNAVAILABLE
```

`OWNER_NOT_FOUND` 已移除：本模块不校验用户存在性（原则 11）。

---

## 10. 状态码汇总

| 接口 | 成功码 | 主要失败码 |
|---|---|---|
| CreateWorkspace | 201 | 400, 403, 422, 500 |
| UpdateWorkspace | 200 | 400, 403, 404, 409, 422 |
| ArchiveWorkspace | 200 | 403, 404, 409, 422 |
| RestoreWorkspace | 200 | 403, 404, 409, 422 |
| DeleteWorkspace | 200 | 403, 404, 409 |
| TransferOwnership | 200 | 403, 404, 409, 422 |
| RestoreReplica | 200 | 403, 404, 409 |
| RevokeReplica | 200 | 403, 404, 409 |
| CreateShare | 201 | 400, 403, 404, 422 |
| GetShare | 200 | 403, 404, 410 |
| ListShares | 200 | 400, 403, 404 |
| RevokeShare | 200 | 403, 404, 410 |
| AccessShare | 200 | 404, 410 |
| GetReplica | 200 | 403, 404, 410 |
| AddResourceRef | 200 | 403, 404, 409, 422 |
| RemoveResourceRef | 200 | 403, 404, 409, 422 |
| UpdateResourceRefRevision | 200 | 403, 404, 409, 422 |
| SyncFromSource | 200 | 400, 403, 404, 409, 422 |
| CreateProducedResource | 201 | 403, 404, 409, 422 |
| ListProducedResources | 200 | 400, 403, 404 |
| CreateMergeRequest | 201 | 400, 403, 404, 422 |
| ListMergeRequests | 200 | 400, 403, 404 |
| ReviewMergeRequest | 200 | 403, 404, 409, 422 |
| MergeIntoWorkspace | 200 | 403, 404, 409, 422 |
| CreateSession | 201 | 400, 403, 404, 422 |
| GetSession | 200 | 403, 404 |
| ListSessions | 200 | 400, 403, 404 |
| UpdateSession | 200 | 403, 404, 409 |
| ArchiveSession | 200 | 403, 404, 409 |
| DeleteSession | 200 | 403, 404, 409 |
| CreateFocusResource | 201 | 400, 403, 404, 422 |
| GetFocusResource | 200 | 403, 404 |
| ListFocusResources | 200 | 400, 403, 404 |
| ArchiveFocusResource | 200 | 403, 404, 409 |
| SetGlobalFocus | 200 | 403, 404, 409, 422 |
| ClearGlobalFocus | 200 | 403, 404, 409 |
| SetSessionFocus | 200 | 403, 404, 409, 422 |
| ClearSessionFocus | 200 | 403, 404, 409 |
| GetWorkspace | 200 | 403, 404 |
| GetWorkspaceSnapshot | 200 | 403, 404 |
| ListWorkspaces | 200 | 400, 403 |
| CheckPermission | 200 | 400, 404 |

说明：

- 410 对应：SHARE_EXPIRED / SHARE_REVOKED / REPLICA_REVOKED。
- 所有写接口在工作空间处于 inactive 时返回 409，错误码按 §7.4 取 WORKSPACE_ARCHIVED / WORKSPACE_DELETED / REPLICA_ARCHIVED / REPLICA_REVOKED，上表不再逐行标注。

---

## 11. 依赖

强依赖：无。

可选只读依赖：

| 模块 | 接口 | 用途 |
|---|---|---|
| Research | GetStateItemRef | 校验 research_state 引用 |
| Sources | GetDocumentRef | 校验 document 引用 |
| Artifacts | GetArtifactRef | 校验 artifact 引用 |
| Conversations | GetConversationRef | 校验 conversation 引用 |
| Agent Runs | GetRunRef | 校验 run 引用 |

依赖失败可降级：仅保存引用，不校验有效性。

资源模块契约（建议）：

| 能力 | 说明 |
|---|---|
| 历史版本保留 | 资源模块保存 revision 历史 |
| 引用保护 | 被 ResourceRef 锁定的 revision 不清理 |
| stale 报告 | 资源不可用时通知 Workspace 标记 stale |

---

## 12. 删除语义

- 软删除。WorkspaceMeta.status = deleted（无独立 lifecycle 字段）。
- 不级联删除下游资源。
- 关联对象处理：
  - Share -> 自动 revoked
  - Replica -> 不自动 revoked。副本数据保留，可继续读写；对已删除主体的同步返回 SOURCE_NOT_FOUND，指向该主体的合并请求不可创建或执行。
  - Session -> 自动 deleted
  - FocusResource -> 自动 archived
- 副本独立。主体删除后，副本的 ResourceRef、globalFocusId、producedResources 仍然有效。
- 可追溯。ReplicaMeta.sourceWorkspaceId 保留，允许指向已删除主体。
- 已删除工作空间默认不出现在 ListWorkspaces 结果中；owner 可通过 includeDeleted 参数查看。

主体状态对副本的可联动性（已定稿）：

| 主体状态 | Share | Replica | sync | merge |
|---|---|---|---|---|
| active | 正常 | 正常 | 允许 | 允许 |
| archived | 不新建，拒绝新 access | 保持 active，可本地工作 | 拒绝（WORKSPACE_ARCHIVED） | 拒绝（WORKSPACE_ARCHIVED） |
| deleted | 自动 revoked | 保持 active，可本地工作 | 拒绝（SOURCE_NOT_FOUND） | 拒绝（WORKSPACE_DELETED） |

> 与 v4 的差异：v4 写「Replica -> 自动 revoked」，与本版原则 3 及 §6.4 / §17.7 的「主体已删除 → 副本继续独立工作」相互矛盾。本版取后者：关停副本由主体所有者显式执行 RevokeReplica。

---

## 13. 版本语义

- Workspace.version：工作空间聚合版本。仅工作空间自身字段与 context（含 resourceRefs 增删与 revision 升级）变更递增；**不随** Session / FocusResource / ProducedResource 变更递增。
- WorkspaceContext.version：仅 context 自身变更递增。
- Session.version / FocusResource.version / ProducedResource.version：各自独立。
- WorkspaceSnapshot.version：快照生成时的 Workspace.version。
- expectedVersion 默认针对聚合版本：工作空间级接口针对 Workspace.version，session / focus 级接口针对各自 version。

---

## 14. 建模约束（实现前提）

1. discriminated union 建模，meta 内联在分支类型；公共字段不出现可空 meta，禁止扁平可空字段。
2. 工厂方法创建，禁止裸构造 Workspace。
3. schema 校验（Zod / Pydantic / JSON Schema）按 type 校验 meta 必填与互斥。
4. type x action 允许表作为唯一权威，CheckPermission 直接查表；实际允许 = 该表 ∩ §7.4 状态约束。
5. 数据库 check constraint 按 type 校验字段非空。
6. 测试覆盖 type x action x status 组合，status 取值与约束见 §7.4。
7. 子聚合归属唯一真相源：Session / FocusResource / ProducedResource 只存 ownerType / ownerId，工作空间不内嵌其列表。
8. 焦点不变式：FocusResource.refId 必须指向同工作空间 status=active 的 ResourceRef；跨工作空间引用一律拒绝。
9. ResourceRef 版本原地升级：refId 稳定，禁止以新增引用表达 revision 升级。

---

## 15. ResourceRef 生命周期

### 15.1 创建

```text
AddResourceRef (workspaceId, actorId, resourceRef)
```

- 可选校验目标资源存在。
- 校验失败可降级保存。
- 生成新 refId。
- 初始 status = active。
- origin 固定为 `native`（本工作空间直接新增）。

### 15.2 复制（副本创建时）

- 主体引用复制到副本。
- 生成新 refId。
- origin = `copied { sourceWorkspaceId }`。
- 保留 targetId / revision。
- 不依赖主体记录存在。

### 15.3 新增（副本内）

- origin = `native`。
- 该引用被合并回主体时，主体侧产生新的 `merged` 引用，副本侧本条引用不变。

### 15.4 revision 更新

```text
UpdateResourceRefRevision (workspaceId, actorId, refId, revision)
```

- 原地更新：`ref.revision = revision`，refId 不变，刷新 updatedAt。
- 写入具体版本号 = 锁定该版本；写 null = 回到跟随最新。
- 历史由领域事件 WorkspaceResourceRefRevisionUpdated 与审计承担。
- 禁止以「新增引用 + 原引用 removed」表达升级。

### 15.5 移除

```text
RemoveResourceRef (workspaceId, actorId, refId)
```

- 移除前校验：
  - 是否被同工作空间 status=active 的 FocusResource.refId 引用
- ProducedResource 通过 targetId 引用资源而非 refId，不构成对某条 ref 的依赖，不阻塞移除。
- 若被引用：
  - 默认拒绝，返回 RESOURCE_REF_IN_USE
  - 或按策略级联清理（需显式声明，见 §21）
- 移除后 status = removed，保留记录可追溯。

### 15.6 失效

- 资源模块报告目标资源或 revision 不可用。
- Workspace 标记 status = stale，记录 staleReason。
- stale 引用保留，可追溯，不参与正常渲染。
- stale 引用可被显式移除。

### 15.7 状态机

```text
active -> stale -> removed
active -> removed
```

---

## 16. revision 策略

### 16.1 语义

| revision | 含义 |
|---|---|
| null | 跟随最新版本 |
| 非空 | 锁定某个版本（整数版本号，由资源模块提供） |

### 16.2 策略

| 策略 | 行为 |
|---|---|
| follow | 同步时副本引用对齐主体当前 revision（含焦点指针） |
| keep | 同步时不动已有引用，只补主体新增引用 |

「锁定版本」不是同步策略，而是引用自身的状态：通过 UpdateResourceRefRevision 显式写入 ref.revision。

### 16.3 校验时机

| 时机 | 行为 |
|---|---|
| 创建引用 | 校验目标资源与 revision 存在性，失败可降级 |
| 读取快照 | 可选校验，标记 stale |
| 合并 | 强制校验，失败记入 MergeItem.conflictReason |
| 显式同步 | 按 revisionStrategy 处理，冲突记入 SyncConflict |

### 16.4 升级

- 升级 revision 原地更新引用，refId 不变。
- 历史由领域事件与审计承担，不通过新增引用表达。
- 保留历史便于追溯与合并冲突检测。

---

## 17. 显式同步详细规则

### 17.1 触发

```text
SyncFromSource (replicaId, actorId, options)
```

### 17.2 权限

- owner：可同步自己主体的副本（如有）。
- replica_visitor：可同步当前副本。
- public_visitor：不可同步。

### 17.3 mode

| mode | 行为 |
|---|---|
| merge | 主体新增引用复制到副本，已有引用按 revisionStrategy 处理 |
| selective | 只同步指定 refId 或 targetId |

「重置副本」不通过同步实现：新建 Share 生成新副本（干净快照），旧副本保留自身引用与产出。

### 17.4 revisionStrategy

| 策略 | 行为 |
|---|---|
| follow | 副本引用对齐主体当前 revision（含焦点指针） |
| keep | 只同步主体新增引用，不修改已有引用 |

### 17.5 includeFocus

- false（默认）：不同步焦点资源，不修改 globalFocusId。
- true：
  1. 主体新增 FocusResource 复制到副本（新 id，ownerId=副本，sourceFocusId=主体焦点 id，refId 指向副本内对应引用）。
  2. 副本 globalFocusId 按 revisionStrategy 处理。
  3. 主体已归档 FocusResource 在副本中标记 archived。
  4. 不删除副本已有 FocusResource。
  5. 不覆盖副本自建的 FocusResource（sourceFocusId = null）。
  6. 不修改副本 Session 的 focusId。

### 17.6 Session 焦点

Session 焦点不参与同步，本版不支持。如需支持，须先设计 Session 映射模型（见 §21）。

### 17.7 边界

| 情况 | 行为 |
|---|---|
| 主体已删除 | 返回 SOURCE_NOT_FOUND，副本继续独立工作 |
| 主体已归档 | 返回 WORKSPACE_ARCHIVED，副本继续独立工作 |
| 主体引用已移除 | 副本保留自己的引用，不级联删除 |
| revision 冲突 | 记入 conflicts，不自动解决 |
| 资源不可用 | 记入 conflicts，标记 stale |
| 副本 archived | 返回 REPLICA_ARCHIVED |
| 副本 revoked | 返回 REPLICA_REVOKED |

### 17.8 同步后更新

- replicaMeta.lastSyncedAt
- replicaMeta.lastSyncedSourceVersion
- replicaMeta.lastSyncOptions

### 17.9 事件

```text
ReplicaSyncRequested
ReplicaSyncCompleted
ReplicaSyncFailed
```

---

## 18. 合并详细规则

### 18.1 流程

```text
CreateMergeRequest -> ReviewMergeRequest -> MergeIntoWorkspace
```

### 18.2 合并项状态

| 状态 | 含义 |
|---|---|
| pending | 待审查 |
| approved | 审查通过 |
| rejected | 审查拒绝 |
| conflicted | 冲突 |

### 18.3 冲突检测

- 按 type + targetId + revision 比较。
- 主体已有等价引用时判定为**幂等命中**，不视为冲突：对应 MergeItem 直接记为 approved 并标注 idempotentHit，ProducedResource 置 merged。
- 真冲突（revision 冲突 / 资源不可用 / 来源已删除）标记 conflicted，其 ProducedResource 回到 ready，解决后可重新发起。
- 检测在 CreateMergeRequest 时执行一次；MergeIntoWorkspace 执行时按 targetWorkspaceVersion 复核，不一致返回 VERSION_CONFLICT 要求重新审查。
- 当前检测只覆盖引用层；内容层冲突（研究状态、Evidence、Artifact revision）待定（见 §21）。

### 18.4 合并执行

- 前置：目标主体必须 active，且 Workspace.version 等于 MergeRequest.targetWorkspaceVersion（compare-and-set，不一致返回 VERSION_CONFLICT 要求重新审查）。
- 仅 approved 的 MergeItem 执行；conflicted 项跳过。
- 主体新增 ResourceRef，origin = `merged { sourceReplicaId, mergeRequestId }`，不覆盖已有引用。
- 主体不复制 ProducedResource 实体，产出仍归属来源副本。
- ProducedResource.status -> merged。
- MergeRequest.status -> merged。
- 刷新 ReplicaMeta.mergedAt 与 lastMergeRequestId；副本 status 不变（合并不是终态）。

### 18.5 事件

```text
MergeRequestCreated
MergeRequestReviewed
ReplicaMerged
```

---

## 19. 快照语义

### 19.1 WorkspaceSnapshot

- 包含 workspace、context、sessions、focusResources、actor、availableActions、version。
- sessions 与 focusResources 由 ownerId 查询组装，不是 context 的内嵌字段；context 只含 resourceRefs 与 globalFocusId。
- 按 type 渲染不同视图。
- actor.relation 与工作空间 status 共同决定 availableActions。

### 19.2 快照版本

- 等于生成时的 Workspace.version。
- 客户端可用 expectedVersion 做乐观锁。

### 19.3 可用动作

- 由 type x relation 权限矩阵（§7.3）∩ 状态约束（§7.4）推导。
- 前端不自行推导，直接使用 availableActions。

---

## 20. 一句话总结

Workspace 是统一抽象，type 区分主体与副本；公共逻辑共用，语义约束按 type 显式分离；ResourceRef 独立于资源与工作空间，refId 区分多次引用，origin 追溯出处，targetId + revision 定位目标；焦点由 FocusResource 指向工作空间内的一条引用，工作空间与会话只保存指针（globalFocusId / focusId），焦点不可嵌套；工作空间只持有 context（引用 + 焦点指针），会话、焦点、产出各自持有 ownerId 独立演进；副本创建时复制引用，之后独立演进；主体删除不影响副本数据与副本继续工作；副本通过 SyncFromSource 显式同步主体更新，焦点同步为可选（includeFocus 默认 false），Session 焦点不同步；副本产出通过 MergeRequest 单向合并回主体，合并是事件不是副本终态，重复引用按幂等命中处理；版本归资源模块，Workspace 只存 revision，引用版本原地更新。

---

## 21. 待补充事项

1. RemoveResourceRef 级联策略最终确定。
2. 资源模块 stale 报告协议。
3. 反向索引（资源 -> 引用列表）是否实现。
4. 事件 payload 完整字段定义。
5. 权限矩阵 relation 推导规则文档化。
6. 测试矩阵：type x action x status（status 维度见 §7.4）。
7. Session 焦点同步：本版明确不支持；如需支持，先设计 Session 映射模型。
8. 合并的内容层冲突检测（研究状态 / Evidence / Artifact revision）。
9. 副本是否应设独立 ownerId（分享接收者）：当前副本不设 ownerId，主体所有者以 `owner` 关系保留治理权（§7.3）。若改为「副本 ownerId = 接收者」，需新增 relation（如 source_owner）并重写 §7.3 矩阵。
10. 主体归档的连带效果按 §12 表执行，待产品复核。
11. P0 工程约束（幂等键、事务与 Outbox 边界、expectedVersion 规则表、审计）尚未写入本文档。
