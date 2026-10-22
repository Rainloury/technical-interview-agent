# 共享内部资料与管理员权限实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或
> executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 增加管理员角色和共享内部资料，使管理员可上传、普通用户可查看并检索，
同时保持所有个人资料严格按 owner 隔离。

**架构：** 用户增加 `role`；共享资料使用独立的 `shared_documents` 和
`shared_document_chunks` 表，沿用现有提取、分块、embedding、Worker 租约、幂等和
RRF 检索能力；问答证据增加共享分块引用，检索时合并“当前用户个人资料 + 所有 ready
共享资料 + 系统 allowlist”。

**技术栈：** Python 3.11/3.12、FastAPI、Pydantic v2、SQLAlchemy 2.0 async、
PostgreSQL 16 + pgvector、Alembic、React 19 + TypeScript、pytest、Vitest、
Playwright。

**规格：** `docs/superpowers/specs/2026-10-22-shared-documents-design.md`

## 全局约束

- 角色只允许 `user` 和 `admin`，默认 `user`；注册接口不能接收角色字段。
- 管理员不能读取、修改或删除其他用户的个人资料。
- 共享资料只能由管理员上传和删除；所有 active 登录用户可列表、详情和检索。
- 所有写接口必须服务端鉴权，不能信任前端传入或缓存的 `role`。
- 共享资料没有 90 天默认过期时间；个人资料保留策略不变。
- 共享资料对象使用 `shared/{document_id.hex}/{uuid4().hex}`，存储桶保持私有。
- 共享资料删除后立即从列表和检索消失，历史证据标记 `source_deleted`。
- 管理员账号删除不得级联删除共享资料；`created_by_user_id` 置空。
- 批量上传必须原子提交；任一文件失败时不得留下对象、资料记录或任务。
- 新依赖非必要不加；优先复用现有 `filetype`、`pypdf`、`python-docx`、pgvector。
- 修改对外行为时同步更新 API、数据模型、ADR、决策登记、README 和运行手册。
- 不改个人资料现有 API 路径、owner 语义或 90 天保留策略。

## 审查重点（Review Focus）

- 普通用户绕过前端，直接向共享资料上传/删除接口发送请求时，必须得到 403 且不产生
  对象、资料、任务或审计成功记录。
- 管理员访问其他用户的个人资料详情/删除接口时，必须仍然得到 404；角色提升不能扩大
  个人资料的 owner 边界。
- 已删除或 embedding 失败的共享资料不得进入列表、详情或问答检索；问答团队不得用
  `state=ready` 之外的共享资料回填证据。
- 共享资料和历史证据在管理员注销后必须保留，`created_by_user_id` 置空，且不能因外键
  级联删除对象或分块。
- 批量共享上传中后一个文件失败时，前一个文件的数据库记录、存储对象和索引任务都必须
  回滚，不能形成半批可见资料。

---

### 任务 1：角色模型、会话 DTO 与管理员 CLI

**文件：**
- 修改：`app/db/models.py`
- 修改：`migrations/versions/<new>_add_user_roles_and_shared_documents.py`
- 修改：`app/schemas/auth.py`
- 修改：`app/schemas/dashboard.py`
- 修改：`app/services/auth.py`
- 修改：`app/services/dashboard.py`
- 修改：`app/cli.py`
- 修改：`app/config.py`
- 修改：`tests/conftest.py`
- 修改：`tests/test_account_api.py`
- 修改：`tests/test_worker_runtime.py`

**接口：**
- 产出 `User.role: str`，值域 `user|admin`，默认 `user`。
- 产出 `UserSummary.role: Literal["user", "admin"]`，并同步所有 `UserSummary`
  构造点（登录、会话和 dashboard）。
- 产出 CLI 命令 `technical-interview-agent set-role --email <email> --role <role>`。
- 产出服务函数 `set_user_role(session, *, email, role, request_id) -> RoleChange`。
- 产出一个一次性 Alembic 迁移，初始角色全部为 `user`。

- [ ] **步骤 1：编写失败的模型、会话和 CLI 测试**

测试要覆盖：

```python
def test_new_user_defaults_to_user_role() -> None: ...
def test_session_includes_role() -> None: ...
def test_set_role_updates_active_user_and_writes_audit() -> None: ...
def test_set_role_rejects_unknown_or_inactive_user() -> None: ...
def test_cli_set_role_requires_email_and_valid_role() -> None: ...
```

预期：新增测试先失败，因为 `User.role` 和 CLI 命令尚不存在。

- [ ] **步骤 2：运行测试确认失败**

运行：

```bash
uv run pytest tests/test_account_api.py tests/test_worker_runtime.py -q
```

预期：FAIL，报 `AttributeError` 或 CLI 选项缺失。

- [ ] **步骤 3：实现角色字段、DTO、服务函数和 CLI**

要求：

- `users.role` 使用 `server_default='user'`，并添加数据库 check constraint；
- 迁移可 downgrade，现有用户不需要回填；
- `UserSummary` 只返回 `role`，不返回邮箱、密码哈希或其他凭证；
- `set_user_role` 写审计 `user_role_changed`，资源哈希使用规范化邮箱；
- CLI 使用现有 argparse 入口，增加 `set-role` 子命令，不复用会删除数据的路径。

- [ ] **步骤 4：运行测试验证通过**

```bash
uv run pytest tests/test_account_api.py tests/test_worker_runtime.py -q
```

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add app/db/models.py app/schemas/auth.py app/services/auth.py app/cli.py app/config.py migrations/versions tests/conftest.py tests/test_account_api.py tests/test_worker_runtime.py
git commit -m "feat: add user roles and administrator CLI"
```

### 任务 2：共享资料与共享分块数据库模型

**文件：**
- 修改：`app/db/models.py`
- 修改：`migrations/versions/<new>_add_user_roles_and_shared_documents.py`
- 修改：`tests/test_database_constraints.py`
- 修改：`tests/conftest.py`

**接口：**
- 产出 `SharedDocument`。
- 产出 `SharedDocumentChunk`。
- `QaEvidence` 增加 `shared_document_chunk_id`。
- `QaEvidence.source_kind` 允许 `shared_document`。

- [ ] **步骤 1：编写失败的数据库约束测试**

覆盖：

```python
def test_shared_document_requires_admin_creator_role() -> None: ...
def test_shared_document_content_hash_is_unique_while_active() -> None: ...
def test_shared_document_chunks_are_isolated_by_document() -> None: ...
def test_qa_evidence_accepts_shared_document_source() -> None: ...
```

预期：FAIL，表和列尚不存在。

- [ ] **步骤 2：实现模型和迁移**

要求：

- 共享资料字段按规格表实现；
- 创建者使用 `ForeignKey("users.id", ondelete="SET NULL")`；
- 共享分块使用 GIN `search_vector` 和 HNSW cosine `embedding`；
- 调整 evidence 检查约束，不破坏已有 `system/user_document` 数据；
- 迁移 upgrade/downgrade 都覆盖新表、列和约束。

- [ ] **步骤 3：运行数据库约束测试**

```bash
RUN_INTEGRATION=1 uv run pytest tests/test_database_constraints.py -q
```

预期：PASS。

- [ ] **步骤 4：验证迁移往返**

```bash
DATABASE_URL=<test-db> uv run alembic upgrade head
DATABASE_URL=<test-db> uv run alembic downgrade -1
DATABASE_URL=<test-db> uv run alembic upgrade head
DATABASE_URL=<test-db> uv run alembic check
```

预期：全部 exit 0，`alembic check` 无漂移。

- [ ] **步骤 5：提交**

```bash
git add app/db/models.py migrations/versions tests/test_database_constraints.py tests/conftest.py
git commit -m "feat: add shared document storage schema"
```

### 任务 3：共享资料服务与管理员 API

**文件：**
- 创建：`app/services/shared_documents.py`
- 创建：`app/api/v1/shared_documents.py`
- 修改：`app/api/v1/router.py`
- 修改：`app/schemas/documents.py`
- 修改：`app/api/dependencies.py`
- 修改：`tests/test_documents_api.py`
- 创建：`tests/test_shared_documents_api.py`

**接口：**
- `shared_documents.upload_document(...)`
- `shared_documents.upload_documents(...)`
- `shared_documents.list_documents(...)`
- `shared_documents.get_document(...)`
- `shared_documents.delete_document(...)`
- `require_admin(auth) -> None`
- `DocumentItem.visibility: Literal["private", "shared"]`
- `DocumentItem.can_delete: bool`

- [ ] **步骤 1：编写失败的权限和上传测试**

覆盖：

```python
def test_anonymous_cannot_access_shared_document_read_or_write() -> None: ...
def test_regular_user_cannot_upload_shared_document() -> None: ...
def test_admin_can_upload_shared_document_and_job_is_resource_scoped() -> None: ...
def test_all_authenticated_users_can_list_and_read_shared_document() -> None: ...
def test_regular_user_cannot_delete_shared_document() -> None: ...
def test_admin_delete_hides_document_and_marks_evidence_deleted() -> None: ...
def test_shared_batch_rolls_back_all_objects_and_jobs_on_invalid_file() -> None: ...
```

预期：FAIL；`/api/v1/shared-documents` 返回 404 或不存在。

- [ ] **步骤 2：实现服务与 API**

要求：

- 共享上传复用严格的 MIME、大小、文件名和重复内容检查；
- API 层只解析请求、调用服务、返回 DTO，不写 SQL 或业务规则；
- 普通用户写操作由服务端返回 `403 admin_required`；
- 列表/详情对所有已登录用户开放；
- 个人资料 DTO 返回 `visibility=private`，共享 DTO 返回 `visibility=shared`；
- 共享删除在同一事务中标记 `deleted`、写证据状态和入队；
- 成功上传/删除写审计，参数不包含文件名或正文。

- [ ] **步骤 3：运行共享资料 API 测试**

```bash
RUN_INTEGRATION=1 uv run pytest tests/test_shared_documents_api.py tests/test_documents_api.py -q
```

预期：PASS，且匿名/普通用户伪造请求不会产生数据库记录或对象。

- [ ] **步骤 4：运行类型和 lint 检查**

```bash
uv run ruff check app tests && uv run mypy app tests
```

预期：PASS。

- [ ] **步骤 5：提交**

```bash
git add app/services/shared_documents.py app/api/v1/shared_documents.py app/api/v1/router.py app/schemas/documents.py app/api/dependencies.py tests/test_documents_api.py tests/test_shared_documents_api.py
git commit -m "feat: add admin-only shared document API"
```

### 任务 4：Worker 索引、删除与账号删除边界

**文件：**
- 修改：`app/worker.py`
- 修改：`app/services/privacy.py`
- 修改：`tests/test_document_worker.py`
- 修改：`tests/test_privacy_api.py`
- 修改：`tests/test_shared_documents_api.py`

**接口：**
- `process_document` 支持 `resource_type=shared_document`。
- `delete_document` 支持 `resource_type=shared_document`。
- 账号删除只清理 `UserDocument`，不触碰 `SharedDocument`。

- [ ] **步骤 1：编写失败的 Worker 测试**

覆盖：

```python
def test_worker_indexes_shared_document_into_shared_chunks() -> None: ...
def test_worker_delete_shared_document_removes_object_and_chunks() -> None: ...
def test_shared_document_embedding_failure_writes_no_partial_chunks() -> None: ...
def test_account_deletion_keeps_shared_documents_and_nulls_creator() -> None: ...
```

预期：FAIL，Worker 尚不识别 `shared_document` 资源。

- [ ] **步骤 2：实现 Worker 分支与删除隔离**

要求：

- 按 `resource_type` 读取正确的资料表；
- 复用提取、分块和 embedding 函数，不复制算法；
- 删除共享资料更新 `QaEvidence.shared_document_chunk_id` 对应记录；
- 账号删除路径仅更新个人资料和其证据，不触碰共享资料；
- 管理员用户删除后由数据库 `SET NULL` 保留共享资料；
- 重试、租约 fencing、dead-letter 逻辑复用现有任务基础设施。

- [ ] **步骤 3：运行 Worker 与隐私测试**

```bash
RUN_INTEGRATION=1 uv run pytest tests/test_document_worker.py tests/test_privacy_api.py tests/test_shared_documents_api.py -q
```

预期：PASS。

- [ ] **步骤 4：提交**

```bash
git add app/worker.py app/services/privacy.py tests/test_document_worker.py tests/test_privacy_api.py tests/test_shared_documents_api.py
git commit -m "feat: process shared documents in the worker"
```

### 任务 5：RAG 共享检索与证据冻结

**文件：**
- 修改：`app/rag/retrieval.py`
- 修改：`app/services/qa.py`
- 修改：`app/worker.py`
- 修改：`app/qa_contracts.py`
- 修改：`app/schemas/qa.py`
- 修改：`tests/test_rag_retrieval.py`
- 修改：`tests/test_qa_api.py`

**接口：**
- `SearchCandidate.source_kind` 支持 `shared_document`。
- `MergedEvidence` 增加 `shared_document_chunk_id`。
- `hybrid_retrieve(owner_user_id=...)` 返回个人、共享和系统三类证据。
- 问答证据 DTO 的 `source_kind` 支持 `shared_document`。

- [ ] **步骤 1：编写失败的 RAG 测试**

覆盖：

```python
def test_shared_document_is_retrievable_by_a_different_user() -> None: ...
def test_private_document_remains_invisible_to_other_users() -> None: ...
def test_shared_and_private_evidence_are_distinct() -> None: ...
def test_deleted_shared_document_is_not_retrievable() -> None: ...
def test_embedding_failure_degrades_to_lexical_shared_results() -> None: ...
```

预期：FAIL，检索只查询 owner 的个人资料。

- [ ] **步骤 2：实现共享词法和向量候选**

要求：

- 词法路径查询 ready 共享分块；
- 向量路径查询 ready 共享分块；
- RRF 的稳定排序能区分个人、共享和系统来源；
- 冻结证据写入 `shared_document_chunk_id`；
- 不把共享资料错误标记为 `user_document`，也不能把个人资料暴露给其他用户。

- [ ] **步骤 3：运行 RAG 与问答测试**

```bash
RUN_INTEGRATION=1 uv run pytest tests/test_rag_retrieval.py tests/test_qa_api.py -q
```

预期：PASS。

- [ ] **步骤 4：运行确定性评测**

```bash
uv run python -m evals.run
```

预期：包含共享资料来源和跨 owner 隔离的用例全部通过。

- [ ] **步骤 5：提交**

```bash
git add app/rag/retrieval.py app/services/qa.py app/worker.py app/qa_contracts.py app/schemas/qa.py tests/test_rag_retrieval.py tests/test_qa_api.py evals
git commit -m "feat: retrieve shared documents with RAG"
```

### 任务 6：前端共享资料入口与角色控制

**文件：**
- 修改：`web/src/api/types.ts`
- 修改：`web/src/api/client.ts`
- 修改：`web/src/auth/AuthProvider.tsx`
- 修改：`web/src/pages/DocumentsPage.tsx`
- 修改：`web/src/pages/DocumentsPage.test.tsx`
- 修改：`web/src/test/server.ts`
- 修改：`web/e2e/rag-slice.spec.ts`
- 修改：`web/src/styles.css`

**接口：**
- `UserSummary.role`。
- `DocumentItem.visibility` 和 `can_delete`。
- `api.sharedDocuments(...)`。
- `api.uploadSharedDocument(s)(...)`。
- `api.deleteSharedDocument(...)`。

- [ ] **步骤 1：编写失败的前端测试**

覆盖：

```tsx
it("shows private and shared document sections", ...)
it("hides shared upload controls from regular users", ...)
it("lets administrators upload and delete shared documents", ...)
it("shows permission errors without rendering optimistic rows", ...)
```

预期：FAIL，页面没有共享资料区域。

- [ ] **步骤 2：实现前端区域和角色控制**

要求：

- 个人资料区保留现有批量上传和删除；
- 共享资料区所有用户可见列表；
- 只有管理员渲染共享上传和删除控件；
- 普通用户不能通过手工构造请求绕过服务端 403；
- 角色来源为服务端返回的 `Session.user.role`，不写入 localStorage；
- 共享资料状态、来源标签和上传权限在移动端不溢出。

- [ ] **步骤 3：运行前端测试**

```bash
cd web
npm run typecheck
npm test -- --run
npm run lint
npm run build
```

预期：全部通过；只有既有 Fast Refresh 警告。

- [ ] **步骤 4：提交**

```bash
git add web/src/api/types.ts web/src/api/client.ts web/src/auth/AuthProvider.tsx web/src/pages/DocumentsPage.tsx web/src/pages/DocumentsPage.test.tsx web/src/test/server.ts web/e2e/rag-slice.spec.ts web/src/styles.css
git commit -m "feat: add shared document controls to the web client"
```

### 任务 7：文档、迁移、审计与端到端验收

**文件：**
- 修改：`docs/api-contract.md`
- 修改：`docs/data-model.md`
- 创建：`docs/adr/0010-shared-documents-and-admin-role.md`
- 修改：`docs/adr/README.md`
- 修改：`docs/decision-register.md`
- 修改：`README.md`
- 修改：`README.zh-CN.md`
- 修改：`docs/release-runbook.md`
- 修改：`web/e2e/rag-slice.spec.ts`

- [ ] **步骤 1：编写失败的文档契约测试**

覆盖：

```python
def test_shared_document_api_contract_is_documented() -> None: ...
def test_admin_role_and_shared_scope_are_documented() -> None: ...
def test_english_readme_remains_ascii() -> None: ...
```

预期：FAIL，文档尚未包含共享资料和角色边界。

- [ ] **步骤 2：更新 API、数据模型、ADR、决策和运行手册**

要求：

- 明确普通用户/管理员/未登录三类权限矩阵；
- 明确个人资料不可被管理员跨 owner 读取；
- 记录共享资料删除、账号删除和证据状态；
- 运行手册加入 `set-role` 命令和首个管理员任命顺序；
- 中英文 README 都描述个人/共享资料边界，英文 README 保持 ASCII。

- [ ] **步骤 3：编写并运行 WebKit 双视口 E2E**

覆盖：

- 普通用户看到共享资料但无上传/删除入口；
- 管理员看到共享上传和删除入口；
- 共享资料被问答引用；
- 手机视口无横向溢出。

运行：

```bash
cd web
E2E_BROWSER=webkit npm run test:e2e
```

预期：桌面和 iPhone 13 WebKit 全部通过。

- [ ] **步骤 4：运行完整验收**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
RUN_INTEGRATION=1 uv run pytest -m integration -q
uv run python -m evals.run
cd web && npm run typecheck && npm test -- --run && npm run lint && npm run build
```

预期：全部通过；记录实际 passed/skipped 数量。

- [ ] **步骤 5：提交**

```bash
git add docs README.md README.zh-CN.md web/e2e/rag-slice.spec.ts
git commit -m "docs: document shared documents and admin roles"
```

## 交接说明

计划按 7 个任务拆分：角色与会话、共享表、共享 API、Worker、RAG、前端、文档与全量
验收。任务之间共享 `SharedDocument`、`shared_document_chunk_id`、`role` 和
`visibility/can_delete` 接口，必须按顺序执行；个人资料接口和 owner 隔离在本计划中
不能放宽。执行方式需由项目负责人选择：

- 子代理驱动；
- 原生执行（推荐；计划接口已固定，但任务之间有较强顺序依赖）。
