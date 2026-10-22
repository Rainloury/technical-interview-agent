# 共享内部资料与管理员权限设计

| 项目 | 内容 |
| --- | --- |
| 状态 | `draft`，等待项目负责人审阅 |
| 日期 | 2026-10-22 |
| 关联决策 | `DR-08`、ADR-0009 |
| 影响范围 | 数据库、鉴权、资料 API、RAG、Worker、前端、CLI、审计、部署文档 |

## 1. 目标

内部资料分为两种可见范围：

- **个人资料**：普通用户和管理员都可上传；只有上传者本人可见、可删除、可检索。
- **共享资料**：只有管理员可上传和删除；所有处于 `active` 状态的登录账号可见，并自动参与问答检索。

管理员不因为角色升级而获得其他用户个人资料的访问权。个人资料仍然严格按
`owner_user_id` 隔离。

## 2. 非目标

- 不提供注册时选择管理员角色。
- 不提供 Web 管理后台、用户列表或角色变更页面。
- 不允许共享资料按部门、租户或用户组配置可见范围。
- 不把共享资料放入现有系统知识源 allowlist；两者使用独立来源标识。
- 不允许普通用户上传、删除或修改共享资料。
- 不改变个人资料的 90 天保留期和账号删除规则。

## 3. 角色模型

### 3.1 用户角色

`users` 增加：

```text
role text not null default 'user'
check (role in ('user', 'admin'))
```

角色只决定是否能管理共享资料，不代表更高的个人数据访问权。

所有现有用户迁移后都是 `user`。首个管理员由服务器运维人员执行一次性 CLI：

```bash
uv run technical-interview-agent set-role \
  --email owner@example.com \
  --role admin
```

CLI 必须：

- 只接受已存在的 `active` 用户；
- 只允许 `user` 或 `admin`；
- 输出变更前后的角色，不输出密码、会话或其他敏感数据；
- 写入审计事件 `user_role_changed`，资源标识使用邮箱哈希。

撤销管理员同样执行 `--role user`。至少一个管理员存在不设为数据库硬约束；防止误删最后
管理员由运维流程负责，本次不引入复杂的锁表检查。

### 3.2 会话返回

`UserSummary` 增加 `role: "user" | "admin"`。前端根据该字段决定是否展示共享资料上传
和删除操作。前端隐藏不是授权边界，所有写接口必须再次校验数据库中的当前角色。

## 4. 数据模型

### 4.1 独立共享资料表

新建 `shared_documents`，结构与 `user_documents` 的生命周期字段保持一致，但不含
`owner_user_id`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID PK | 共享资料 ID |
| `created_by_user_id` | UUID FK users | 上传者；`ondelete=SET NULL`，删除账号不删除共享资料 |
| `title` | text | 展示标题 |
| `original_filename` | text | 原始文件名 |
| `detected_mime` | text | 检测后的 MIME |
| `size_bytes` | bigint | 1 到 10 MB |
| `sha256` | text | 内容哈希 |
| `object_key` | text unique | 私有对象地址 |
| `state` | text | `uploaded/processing/ready/failed/deleted` |
| `failure_code` / `error_message` | text nullable | 失败诊断 |
| `chunk_count` | integer | 分块数 |
| `index_version` / `embedding_model` / `embedding_dimensions` | | 索引元数据 |
| `idempotency_key` | text nullable | 幂等键，全表唯一 |
| `request_fingerprint` | text nullable | 请求指纹 |
| `deletion_state` | text nullable | `pending/deleted/failed` |
| `created_at` / `updated_at` | timestamptz | 时间戳 |
| `completed_at` / `deleted_at` | timestamptz nullable | 生命周期 |

唯一约束：

- 未删除资料的 `sha256` 全表唯一；
- 非空 `idempotency_key` 全表唯一；
- 索引 `created_at, id` 用于稳定分页。

共享资料没有 90 天默认过期时间；管理员显式删除前长期可用。此差异写入数据模型文档。

### 4.2 共享分块表

新建 `shared_document_chunks`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | UUID PK | 共享分块 ID |
| `document_id` | UUID FK shared_documents | `ondelete=CASCADE` |
| `chunk_index` | integer | 文件内顺序 |
| `section_path` | text | 分块位置 |
| `content` / `content_hash` / `search_text` | text | 文本与检索内容 |
| `search_vector` | tsvector generated | PostgreSQL `simple` 配置 |
| `token_count` | integer | 预算 |
| `embedding` | vector(1024) | embedding |
| `created_at` | timestamptz | 创建时间 |

约束和索引与 `user_document_chunks` 相同：

- `unique(document_id, chunk_index)`；
- GIN 索引 `search_vector`；
- HNSW cosine 索引 `embedding`。

### 4.3 问答证据

`qa_evidence` 增加：

```text
shared_document_chunk_id uuid null references shared_document_chunks(id)
```

`source_kind` 扩展为：

```text
source_kind in ('system', 'user_document', 'shared_document')
```

共享资料删除后，引用它的历史证据立即标记为 `source_deleted`，文件和历史引用本身
不会因为删除管理员账号而消失。

## 5. API

共享资料使用独立接口，避免让 `/api/v1/documents` 的语义在不同角色下变化：

```text
POST   /api/v1/shared-documents          管理员，单文件上传
POST   /api/v1/shared-documents/batch    管理员，批量上传
GET    /api/v1/shared-documents          所有登录用户，列表
GET    /api/v1/shared-documents/{id}     所有登录用户，详情
DELETE /api/v1/shared-documents/{id}     管理员，删除
```

行为：

- 上传和删除要求 `role=admin`、有效 CSRF 和 `Idempotency-Key`。
- 普通用户调用写接口返回 `403 admin_required`。
- 未登录用户统一返回现有 `401 authentication_required`。
- 列表和详情不返回 `object_key`、创建者 ID、邮箱、原始内容或 embedding。
- 列表按 `created_at DESC, id DESC` 稳定分页，只返回 `state != deleted` 的记录。
- 普通用户删除返回 `403 admin_required`；不能把它做成 `404` 来掩盖共享资料存在。
- 共享资料 ID 对其他用户的详情读取可见，因为列表本身对所有登录用户可见。

`DocumentItem` 扩展：

```text
visibility: "private" | "shared"
can_delete: boolean
```

个人资料接口返回 `visibility=private`；共享资料接口返回 `visibility=shared`。
`can_delete` 只用于前端操作提示，后端仍独立鉴权。

## 6. 权限矩阵

| 操作 | 未登录 | 普通用户 | 管理员 |
| --- | --- | --- | --- |
| 上传个人资料 | 401 | 允许 | 允许 |
| 列出个人资料 | 401 | 仅自己 | 仅自己 |
| 查看个人资料详情 | 401 | 仅自己 | 仅自己 |
| 删除个人资料 | 401 | 仅自己 | 仅自己 |
| 上传共享资料 | 401 | 403 | 允许 |
| 列出共享资料 | 401 | 允许 | 允许 |
| 查看共享资料详情 | 401 | 允许 | 允许 |
| 删除共享资料 | 401 | 403 | 允许 |
| 问答检索个人资料 | 401 | 仅自己 | 仅自己 |
| 问答检索共享资料 | 401 | 所有 ready 共享资料 | 所有 ready 共享资料 |

## 7. RAG 与证据

检索仍然使用现有两路候选和 RRF：

1. 个人资料候选：仅查询当前用户 `ready`、未删除的资料。
2. 共享资料候选：查询所有 `shared_documents` 中 `ready`、未删除的资料。
3. 系统资料候选：保持现有 allowlist/published 逻辑。

余弦和词法各保留 Top 20 候选，RRF 后统一取 Top 5。共享资料与个人资料拥有独立的
candidate ID 空间，融合排序使用“来源类型、标题、分块 ID”作为稳定决胜项。

冻结证据时：

- 个人证据写入 `user_document_chunk_id`；
- 共享证据写入 `shared_document_chunk_id`；
- `source_kind` 分别为 `user_document` 和 `shared_document`。

`source_state` 的判断必须能同时覆盖两类资料。删除共享资料时只更新引用共享分块的
证据，不影响个人资料证据。

## 8. Worker 与异步索引

沿用 `process_document` 任务类型，但资源类型区分：

```text
resource_type: "user_document" | "shared_document"
```

Worker 在拿到任务后按 `resource_type` 选择表和处理分支；不得根据上传者角色推断表。

索引行为：

- 只允许管理员上传的共享资料进入 `shared_document` 资源队列；
- 提取、分块和 Ollama embedding 逻辑复用现有函数；
- embedding 不可用时重试，耗尽后把共享资料置为 `failed`；
- 进程崩溃或租约失效时不能写入部分共享资料分块；
- 同一共享文件重复上传按内容哈希和幂等键复用已有记录，不产生重复索引。

删除 Worker：

- 删除共享资料与删除个人资料使用独立资源类型；
- 删除事务先设置 `state=deleted`、`deletion_state=pending`、`deleted_at`；
- 历史共享证据立即变为 `source_deleted`；
- 异步删除对象和分块，失败进入现有重试和 dead-letter 机制；
- 管理员账号删除不能级联删除共享资料，只把 `created_by_user_id` 置空。

## 9. 账号删除与保留

共享资料是系统级资料，不属于个人数据删除范围。普通用户删除账号时：

- 只删除该用户的个人资料；
- 不删除任何共享资料；
- 不影响其他账号看到的共享资料或历史证据。

管理员删除账号时：

- 同样只删除其个人资料；
- 共享资料保留，创建者引用置空；
- 共享资料删除必须由管理员在账号删除前显式操作。

## 10. 文件与对象存储

共享资料对象 key 采用：

```text
shared/{shared_document_id.hex}/{uuid4().hex}
```

对象不放入任何用户目录；本地存储和 OSS 都必须使用私有读权限。上传前先检测
PDF/DOCX 内容，单文件上限仍为 10 MB。共享资料不使用个人资料的 owner 目录规则。

## 11. 前端

内部资料页拆为两个清晰区域：

- **我的资料**：现有上传、列表、删除和个人可见状态；
- **共享资料**：管理员可见上传入口，所有用户可见列表和详情；普通用户不展示删除按钮。

管理员上传区需要明确标记“共享给所有账号”。普通用户上传区继续标记“仅自己可见”。

前端不新增独立的管理后台页面。`DocumentsPage` 根据会话中的 `role` 渲染共享上传入口，
但所有服务端接口仍以数据库当前角色为准。角色变更后已经打开的旧页面不得因缓存而绕过
后端权限。

移动端：

- 两个资料区域纵向排列；
- 上传表单、文件选择器和删除按钮不得横向溢出；
- 共享资料标识和上传权限标记必须在手机视口可读。

## 12. 审计与日志

共享资料写操作写入最小审计事件：

- `shared_document_uploaded`
- `shared_document_deleted`
- `user_role_changed`

审计只记录操作类型、结果、请求 ID 和哈希化资源标识，不记录原始内容、文件名或
embedding。结构化日志不得出现文件正文、对象 key 或凭据。

## 13. 数据库迁移

新增一个 Alembic 迁移：

- 为 `users` 添加 `role` 并设置默认 `user`；
- 创建 `shared_documents` 和 `shared_document_chunks`；
- 为 `qa_evidence` 添加 `shared_document_chunk_id`；
- 调整 `source_kind` 检查约束；
- 添加 GIN、HNSW 和唯一约束；
- 保持向下兼容：现有个人资料、系统资料和问答证据的数据不需要回填。

迁移在 PostgreSQL 16 + pgvector 上验证 upgrade、downgrade、再次 upgrade 和
`alembic check`。

## 14. 安全与失败模式

必须覆盖以下失败模式：

- 普通用户直接调用共享上传/删除 API：403，不产生对象、记录或任务；
- 普通用户直接访问其他用户个人资料：404，角色提升不改变此行为；
- 管理员查看其他用户个人资料：仍然 404；
- 伪造 `role=admin` 的前端请求：服务端按数据库角色拒绝；
- 共享资料删除后：立即从列表和未来检索消失，历史证据显示 `source_deleted`；
- embedding 不可用：个人资料与共享资料都不写入部分向量，索引失败可重试；
- 共享上传批量中任一文件失败：整个批次回滚，不能留下半批记录；
- 管理员账号删除：共享资料保留，个人资料仍按账号删除流程清理；
- 同内容重复上传：幂等复用已有共享记录，不产生重复分块；
- 已删除的共享资料：不出现在列表、详情或问答检索。

## 15. 验收测试

### 15.1 后端

- 角色迁移默认值和 CLI `set-role` 成功/失败；
- 普通用户上传共享资料返回 403；
- 管理员上传共享资料返回 202，并创建 `shared_document` 任务；
- 普通用户能列出/查看管理员上传的共享资料；
- 普通用户不能删除共享资料；
- 个人资料跨用户仍然 404；
- 共享资料跨账号可见，个人资料跨账号不可见；
- 共享资料进入问答检索，证据带 `shared_document` 来源；
- 共享资料删除后停止检索，历史证据标记 `source_deleted`；
- 共享资料 embedding 失败无部分分块，重试后可达 `ready`；
- 账号删除不删除共享资料；
- 管理员角色变更写入审计且不泄露敏感值；
- `alembic upgrade`、`downgrade`、`upgrade` 和 `alembic check` 通过。

### 15.2 前端

- 普通用户看到共享资料列表，但看不到共享上传/删除入口；
- 管理员看到共享上传表单和删除按钮；
- 共享上传与个人上传分别调用正确接口；
- 权限错误的提示可见且可理解；
- 手机和桌面视口无横向溢出，文件选择器和操作按钮不重叠；
- 角色变更后页面重新获取会话并不再展示旧的管理能力。

### 15.3 评测

新增至少一条确定性 RAG 评测：

- 共享资料和管理员上传路径可被问答引用；
- 共享资料不会被错误标记成个人资料；
- 普通用户无法通过检索上下文看到其他用户的个人资料。

## 16. 文档更新

实现时同步更新：

- `docs/api-contract.md`：共享资料接口、权限和 DTO；
- `docs/data-model.md`：用户角色、共享资料、共享分块、证据字段；
- `docs/adr/0010-shared-documents-and-admin-role.md`：独立共享表、角色边界和审计；
- `docs/decision-register.md`：共享资料权限决策；
- 中英文 README 的内部资料能力说明；
- `docs/release-runbook.md`：首个管理员任命和回滚步骤。

## 17. 开放问题

当前设计不保留未决问题。若产品后续需要“指定用户组可见”或“多管理员审批”，另立规格，
不把它塞进本切片。
