# Workspace 模块技术设计文档（TDD）

## 1. 概述

Workspace 模块属于 Research Core，负责：

- 项目生命周期：创建、更新、归档、恢复、删除、转移所有权
- 成员与权限：邀请、加入、移除、角色变更、离开、权限校验
- 当前研究焦点：设置、清除、查询
- 对外主要输出：`WorkspaceSnapshot`
- 协作场景下，所有写操作必须携带 `actorId`，并做权限校验

本文档基于已有接口、参数和输出定义，补充状态码，并为每个接口增加输入输出说明。

---

## 2. 领域模型

### 2.1 枚举

```text
WorkspaceStatus = active | archived | deleted
MemberRole = owner | admin | editor | viewer
MembershipStatus = invited | active | removed | left
FocusType = research_state | document | artifact | conversation | run
```

### 2.2 核心对象

#### Workspace

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | 项目 ID |
| name | string | 是 | 项目名称 |
| description | string | 否 | 项目描述 |
| visibility | string | 是 | private / team / public |
| status | WorkspaceStatus | 是 | 项目状态 |
| ownerId | string | 是 | 所有者 ID |
| version | number | 是 | 版本号 |
| createdAt | timestamp | 是 | 创建时间 |
| updatedAt | timestamp | 是 | 更新时间 |
| archivedAt | timestamp? | 否 | 归档时间 |

#### Membership

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| userId | string | 是 | 用户 ID |
| role | MemberRole | 是 | 角色 |
| status | MembershipStatus | 是 | 状态 |
| invitedBy | string? | 否 | 邀请人 |
| invitedAt | timestamp? | 否 | 邀请时间 |
| joinedAt | timestamp? | 否 | 加入时间 |
| updatedAt | timestamp | 是 | 更新时间 |

#### Focus

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| type | FocusType | 是 | 焦点类型 |
| targetId | string | 是 | 目标资源 ID |
| revision | string? | 否 | 目标版本 |
| setBy | string | 是 | 设置者 |
| updatedAt | timestamp | 是 | 设置时间 |

#### WorkspaceSnapshot

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspace | Workspace | 是 | 项目信息 |
| focus | Focus \| null | 是 | 当前焦点 |
| actor | ActorView | 是 | 当前操作者权限视图 |
| members | Membership[]? | 否 | 成员列表 |
| version | number | 是 | 快照版本 |

`ActorView`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| actorId | string | 是 | 操作者 ID |
| role | MemberRole | 是 | 角色 |
| permissions | string[] | 是 | 权限动作列表 |

---

## 3. 状态码规范

### 3.1 HTTP 状态码

| 状态码 | 含义 |
|---|---|
| 200 | 成功，返回数据 |
| 201 | 创建成功 |
| 204 | 成功，无返回内容 |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突，如版本冲突、成员已存在 |
| 422 | 业务规则校验失败 |
| 500 | 服务内部错误 |

### 3.2 业务错误码

| 错误码 | 含义 |
|---|---|
| VALIDATION_ERROR | 通用参数校验失败 |
| WORKSPACE_NOT_FOUND | 项目不存在 |
| WORKSPACE_ARCHIVED | 项目已归档，不可写 |
| WORKSPACE_DELETED | 项目已删除 |
| PERMISSION_DENIED | 无权限执行该动作 |
| VERSION_CONFLICT | 版本冲突，需刷新 |
| MEMBER_NOT_FOUND | 成员不存在 |
| MEMBER_ALREADY_EXISTS | 成员已存在 |
| INVALID_ROLE | 角色非法 |
| INVALID_FOCUS_REF | 焦点引用非法 |
| FOCUS_NOT_SET | 当前无焦点 |
| INVITATION_NOT_FOUND | 邀请不存在 |
| CANNOT_REMOVE_OWNER | 不能移除所有者 |
| CANNOT_TRANSFER_TO_SELF | 不能转移给自己 |
| INVALID_ACTION | 权限动作非法 |
| SERVICE_UNAVAILABLE | 依赖服务不可用 |

---

## 4. 接口设计

格式：`接口名 (输入) -> (权限动作) -> 输出 | 状态码`

### 4.1 项目生命周期

#### CreateWorkspace

```text
CreateWorkspace (actorId, name, description, visibility, initialMembers?) -> (workspace:create) -> WorkspaceSnapshot | 201
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| actorId | string | 是 | 创建者用户 ID |
| name | string | 是 | 项目名称 |
| description | string | 否 | 项目描述 |
| visibility | string | 是 | 可见性：private / team / public |
| initialMembers | object[] | 否 | 初始成员列表，每项含 `userId`、`role` |

**输出说明**

返回 `WorkspaceSnapshot`，包含新建项目信息、焦点（初始为 `null`）、当前操作者权限视图、成员列表、版本号。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 400 | VALIDATION_ERROR | 参数缺失或非法 |
| 403 | PERMISSION_DENIED | 无创建权限 |
| 422 | INVALID_ROLE | initialMembers 角色非法 |
| 500 | SERVICE_UNAVAILABLE | 内部错误或依赖不可用 |

---

#### UpdateWorkspace

```text
UpdateWorkspace (workspaceId, actorId, patch, expectedVersion?) -> (workspace:update) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| patch | object | 是 | 部分更新字段，如 `{ name?, description?, visibility? }` |
| expectedVersion | number | 否 | 期望版本，用于乐观锁 |

**输出说明**

返回更新后的 `WorkspaceSnapshot`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 400 | VALIDATION_ERROR | patch 非法 |
| 403 | PERMISSION_DENIED | 无更新权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | expectedVersion 不匹配 |
| 422 | WORKSPACE_ARCHIVED | 项目已归档不可更新 |

---

#### ArchiveWorkspace

```text
ArchiveWorkspace (workspaceId, actorId, reason?, expectedVersion?) -> (workspace:archive) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| reason | string | 否 | 归档原因 |
| expectedVersion | number | 否 | 期望版本 |

**输出说明**

返回归档后的 `WorkspaceSnapshot`，项目 `status` 变为 `archived`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无归档权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |
| 422 | WORKSPACE_ARCHIVED | 已归档 |

---

#### RestoreWorkspace

```text
RestoreWorkspace (workspaceId, actorId, expectedVersion?) -> (workspace:restore) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| expectedVersion | number | 否 | 期望版本 |

**输出说明**

返回恢复后的 `WorkspaceSnapshot`，项目 `status` 变为 `active`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无恢复权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |
| 422 | WORKSPACE_DELETED | 已删除不可恢复 |

---

#### DeleteWorkspace

```text
DeleteWorkspace (workspaceId, actorId, expectedVersion?) -> (workspace:delete) -> WorkspaceDeleted | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| expectedVersion | number | 否 | 期望版本 |

**输出说明**

返回 `WorkspaceDeleted`，包含 `workspaceId`、`actorId`、`deletedAt`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无删除权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |

---

#### TransferOwnership

```text
TransferOwnership (workspaceId, actorId, newOwnerId, expectedVersion?) -> (workspace:transfer_ownership) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 当前操作者 ID |
| newOwnerId | string | 是 | 新所有者用户 ID |
| expectedVersion | number | 否 | 期望版本 |

**输出说明**

返回更新后的 `WorkspaceSnapshot`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 非所有者 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |
| 422 | CANNOT_TRANSFER_TO_SELF | 转移给自己 |
| 422 | MEMBER_NOT_FOUND | 新所有者不是成员 |

---

### 4.2 成员与权限

#### InviteMember

```text
InviteMember (workspaceId, actorId, userId, role) -> (member:invite) -> Membership | 201
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 邀请者 ID |
| userId | string | 是 | 被邀请用户 ID |
| role | MemberRole | 是 | 邀请角色 |

**输出说明**

返回 `Membership`，包含 `workspaceId`、`userId`、`role`、`status`、`invitedBy`、`invitedAt`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无邀请权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | MEMBER_ALREADY_EXISTS | 已是成员 |
| 422 | INVALID_ROLE | 角色非法 |

---

#### AcceptInvitation

```text
AcceptInvitation (workspaceId, actorId, invitationId) -> (member:accept) -> Membership | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 接受邀请的用户 ID |
| invitationId | string | 是 | 邀请 ID |

**输出说明**

返回 `Membership`，`status` 变为 `active`，并填充 `joinedAt`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 404 | INVITATION_NOT_FOUND | 邀请不存在 |
| 422 | WORKSPACE_ARCHIVED | 项目已归档 |

---

#### RemoveMember

```text
RemoveMember (workspaceId, actorId, userId) -> (member:remove) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| userId | string | 是 | 被移除成员 ID |

**输出说明**

返回更新后的 `WorkspaceSnapshot`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无移除权限 |
| 404 | MEMBER_NOT_FOUND | 成员不存在 |
| 422 | CANNOT_REMOVE_OWNER | 不能移除所有者 |

---

#### ChangeMemberRole

```text
ChangeMemberRole (workspaceId, actorId, userId, newRole) -> (member:change_role) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| userId | string | 是 | 目标成员 ID |
| newRole | MemberRole | 是 | 新角色 |

**输出说明**

返回更新后的 `WorkspaceSnapshot`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无修改权限 |
| 404 | MEMBER_NOT_FOUND | 成员不存在 |
| 422 | INVALID_ROLE | 角色非法 |
| 422 | CANNOT_REMOVE_OWNER | 不能改所有者角色 |

---

#### LeaveWorkspace

```text
LeaveWorkspace (workspaceId, actorId) -> (member:leave) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 离开者 ID |

**输出说明**

返回更新后的 `WorkspaceSnapshot`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 422 | CANNOT_REMOVE_OWNER | 所有者不能直接离开 |

---

#### ListMembers

```text
ListMembers (workspaceId, actorId, page?, pageSize?) -> (member:list) -> Membership[] | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 查询者 ID |
| page | number | 否 | 页码，从 1 开始 |
| pageSize | number | 否 | 每页数量 |

**输出说明**

返回 `Membership[]`，可分页。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 400 | VALIDATION_ERROR | 分页参数非法 |
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

#### GetMembership

```text
GetMembership (workspaceId, userId, actorId?) -> (member:read) -> Membership | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| userId | string | 是 | 要查询的成员 ID |
| actorId | string | 否 | 发起查询者，用于权限校验 |

**输出说明**

返回 `Membership`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | MEMBER_NOT_FOUND | 成员不存在 |

---

#### CheckPermission

```text
CheckPermission (workspaceId, actorId, action, resourceRef?) -> (internal) -> PermissionDecision | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| action | string | 是 | 权限动作，如 `focus:set` |
| resourceRef | object | 否 | 可选资源引用，如 `{ type, id }` |

**输出说明**

返回 `PermissionDecision`：

```json
{
  "allowed": true,
  "reason": "string?",
  "effectiveRole": "MemberRole?",
  "constraints": "object?"
}
```

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 400 | INVALID_ACTION | action 非法 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

#### GetActorPermissions

```text
GetActorPermissions (workspaceId, actorId) -> (member:read) -> PermissionSet | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |

**输出说明**

返回 `PermissionSet`：

```json
{
  "actorId": "string",
  "role": "MemberRole",
  "permissions": ["string"]
}
```

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

### 4.3 当前研究焦点

#### SetFocus

```text
SetFocus (workspaceId, actorId, focusRef, expectedVersion?) -> (focus:set) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| focusRef | object | 是 | 焦点引用，结构见下方 |
| expectedVersion | number | 否 | 期望版本 |

`focusRef` 结构：

```json
{
  "type": "research_state | document | artifact | conversation | run",
  "targetId": "string",
  "revision": "string?",
  "updatedAt": "timestamp"
}
```

**输出说明**

返回更新后的 `WorkspaceSnapshot`，其中 `focus` 为新的焦点。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无设置权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |
| 422 | INVALID_FOCUS_REF | 焦点引用非法 |
| 422 | WORKSPACE_ARCHIVED | 项目已归档 |

---

#### ClearFocus

```text
ClearFocus (workspaceId, actorId, expectedVersion?) -> (focus:clear) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 是 | 操作者 ID |
| expectedVersion | number | 否 | 期望版本 |

**输出说明**

返回更新后的 `WorkspaceSnapshot`，其中 `focus` 为 `null`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无清除权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |
| 409 | VERSION_CONFLICT | 版本冲突 |
| 422 | FOCUS_NOT_SET | 当前无焦点 |

---

#### GetFocus

```text
GetFocus (workspaceId, actorId?) -> (focus:read) -> Focus | null | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 否 | 查询者，可选，用于权限过滤 |

**输出说明**

返回 `Focus` 对象或 `null`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

### 4.4 查询与快照

#### GetWorkspace

```text
GetWorkspace (workspaceId, actorId?) -> (workspace:read) -> Workspace | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 否 | 查询者，可选 |

**输出说明**

返回 `Workspace` 对象。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

#### GetWorkspaceSnapshot

```text
GetWorkspaceSnapshot (workspaceId, actorId?) -> (workspace:read) -> WorkspaceSnapshot | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| workspaceId | string | 是 | 项目 ID |
| actorId | string | 否 | 查询者，可选，用于返回该操作者的权限视图 |

**输出说明**

返回 `WorkspaceSnapshot`，结构见领域模型。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 403 | PERMISSION_DENIED | 无查看权限 |
| 404 | WORKSPACE_NOT_FOUND | 项目不存在 |

---

#### ListWorkspaces

```text
ListWorkspaces (actorId, filter?, page?, pageSize?) -> (workspace:list) -> Workspace[] | 200
```

**输入说明**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| actorId | string | 是 | 查询者 ID |
| filter | object | 否 | 过滤条件，如状态、关键字、角色 |
| page | number | 否 | 页码 |
| pageSize | number | 否 | 每页数量 |

**输出说明**

返回 `Workspace[]`。

**失败状态码**

| 状态码 | 错误码 | 场景 |
|---|---|---|
| 400 | VALIDATION_ERROR | 分页参数非法 |
| 403 | PERMISSION_DENIED | 无列表权限 |

---

## 5. 事件输出

事件不涉及用户权限动作，统一使用事件信封。

### 5.1 事件信封

| 字段 | 类型 | 说明 |
|---|---|---|
| eventId | string | 事件 ID |
| eventType | string | 事件类型 |
| workspaceId | string | 项目 ID |
| actorId | string | 触发者 |
| occurredAt | timestamp | 发生时间 |
| version | number | 事件版本 |
| payload | object | 事件负载 |

### 5.2 事件列表

| 事件 | payload |
|---|---|
| WorkspaceCreated | snapshot: WorkspaceSnapshot |
| WorkspaceUpdated | patch: object, snapshot: WorkspaceSnapshot |
| WorkspaceArchived | reason?: string, snapshot: WorkspaceSnapshot |
| WorkspaceRestored | snapshot: WorkspaceSnapshot |
| WorkspaceDeleted | workspaceId: string, deletedAt: timestamp |
| MemberInvited | userId, role, invitationId |
| MemberAdded | userId, role |
| MemberRemoved | userId |
| MemberRoleChanged | userId, oldRole, newRole |
| OwnershipTransferred | oldOwnerId, newOwnerId |
| FocusChanged | oldFocus, newFocus |
| FocusCleared | oldFocus |

事件发布失败不阻塞主流程，记录日志并进入重试队列。

---

## 6. 权限动作汇总

| 权限动作 | 说明 |
|---|---|
| workspace:create | 创建项目 |
| workspace:read | 读取项目 |
| workspace:update | 更新项目 |
| workspace:archive | 归档项目 |
| workspace:restore | 恢复项目 |
| workspace:delete | 删除项目 |
| workspace:transfer_ownership | 转移所有权 |
| workspace:list | 列出项目 |
| member:invite | 邀请成员 |
| member:accept | 接受邀请 |
| member:remove | 移除成员 |
| member:change_role | 修改角色 |
| member:leave | 离开项目 |
| member:list | 列出成员 |
| member:read | 读取成员 |
| focus:set | 设置焦点 |
| focus:clear | 清除焦点 |
| focus:read | 读取焦点 |

---

## 7. 依赖

### 7.1 强依赖

无。Workspace 拥有 `workspace / membership / focus`，核心功能不依赖其他模块。

### 7.2 可选只读依赖

用于校验焦点引用或聚合摘要：

| 模块 | 接口 | 用途 |
|---|---|---|
| Research | GetStateItemRef | 校验焦点 |
| Sources | GetDocumentRef | 校验焦点 |
| Artifacts | GetArtifactRef | 校验焦点 |
| Conversations | GetConversationRef | 校验焦点 |
| Agent Runs | GetRunRef | 校验焦点 |

依赖失败时可降级：仅保存引用，不校验有效性。

### 7.3 不依赖

Search：无独立权威数据，不参与 Workspace 生命周期、成员权限和焦点管理。

---

## 8. 并发与版本

- 所有写操作支持 `expectedVersion`。
- 若传入 `expectedVersion` 与当前 `version` 不一致，返回 `409 VERSION_CONFLICT`。
- 未传 `expectedVersion` 时，采用最后写入胜出，但记录审计日志。
- `WorkspaceSnapshot.version` 用于缓存失效和乐观锁。

---

## 9. 错误处理约定

- 业务错误统一返回：

```json
{
  "code": "PERMISSION_DENIED",
  "message": "无权执行该操作",
  "details": {}
}
```

- HTTP 状态码与业务错误码配合使用。
- 依赖服务不可用时返回 `500 SERVICE_UNAVAILABLE`，可重试。
- 权限校验失败返回 `403 PERMISSION_DENIED`。
- 资源不存在返回 `404` + 对应错误码。
- 版本冲突返回 `409 VERSION_CONFLICT`。
- 通用参数校验失败返回 `400 VALIDATION_ERROR`。

---

## 10. 状态码汇总表

| 接口 | 成功码 | 主要失败码 |
|---|---|---|
| CreateWorkspace | 201 | 400, 403, 422, 500 |
| UpdateWorkspace | 200 | 400, 403, 404, 409, 422 |
| ArchiveWorkspace | 200 | 403, 404, 409, 422 |
| RestoreWorkspace | 200 | 403, 404, 409, 422 |
| DeleteWorkspace | 200 | 403, 404, 409 |
| TransferOwnership | 200 | 403, 404, 409, 422 |
| InviteMember | 201 | 403, 404, 409, 422 |
| AcceptInvitation | 200 | 404, 422 |
| RemoveMember | 200 | 403, 404, 422 |
| ChangeMemberRole | 200 | 403, 404, 422 |
| LeaveWorkspace | 200 | 404, 422 |
| ListMembers | 200 | 400, 403, 404 |
| GetMembership | 200 | 403, 404 |
| CheckPermission | 200 | 400, 404 |
| GetActorPermissions | 200 | 403, 404 |
| SetFocus | 200 | 403, 404, 409, 422 |
| ClearFocus | 200 | 403, 404, 409, 422 |
| GetFocus | 200 | 403, 404 |
| GetWorkspace | 200 | 403, 404 |
| GetWorkspaceSnapshot | 200 | 403, 404 |
| ListWorkspaces | 200 | 400, 403 |

---

## 11. 总结

本 TDD 基于已有 Workspace 接口、参数和输出定义，补充了状态码与错误码，并为每个接口提供了输入输出说明。设计遵循：

- 写操作必须携带 `actorId` 并做权限校验
- 并发敏感操作使用 `expectedVersion`
- 焦点仅保存引用，不复制其他模块数据
- `WorkspaceSnapshot` 作为协作上下文主要输出
- 状态码与业务错误码分离，便于调用方处理
- 通用参数校验统一使用 `VALIDATION_ERROR`
- 不过度设计，不引入额外模块或复杂机制