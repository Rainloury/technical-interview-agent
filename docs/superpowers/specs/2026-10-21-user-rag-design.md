# 内部资料 RAG 设计规格

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 文档状态 | 待用户审查 |
| 更新日期 | 2026-10-21 |
| 适用阶段 | MVP 内部资料检索 |
| 需求依据 | 本规格第 1、2 节，项目负责人已确认个人资料域、上传后自动参与问答、无资料选择器 |

## 1. 目标与已确认决策

本切片为每个登录用户增加私有内部资料库，并让技术问答优先检索和引用这些资料。

已确认的产品边界：

- 资料仅上传者本人可见、可删除、可检索，不跨用户共享。
- 现有系统白名单知识源继续保留，不迁移为个人资料。
- 第一版支持 PDF、DOCX、TXT、Markdown，单文件最大 10 MB。
- 上传后异步解析、分块和索引；只有完成索引的资料参与后续问答。
- 问答自动检索“当前用户已就绪资料 + 系统白名单资料”，不提供资料选择器。
- 检索采用 Ollama `bge-m3` embedding、pgvector 向量检索、PostgreSQL 全文相关性排序（`ts_rank_cd`，作为 BM25 风格词法召回）和 Reciprocal Rank Fusion（RRF）。
- Ollama embedding 不可用时，问答降级为纯 BM25；资料索引任务失败并通过重试上限后进入失败状态。
- 前端提供上传、列表、详情状态和删除入口，不提供资料共享或资料选择器。
- 不引入 LangChain、LlamaIndex、CrewAI 或托管向量数据库。

成功标准：

1. 用户能在同一账号内上传技术资料，查看处理状态，并在资料就绪后通过 `/qa` 获得带来源的证据回答。
2. 其他用户无法查看、删除、检索或通过证据推断该资料。
3. 混合检索结果包含 pgvector 与 BM25 两路候选；Ollama 不可用时问答仍能完成，并明确记录降级状态。
4. 资料删除、账号数据删除和保留到期后，原文与分块不再参与检索，迟到的 Worker 写入不能复活资料。

## 2. 非目标与本切片约束

- 不做团队共享、管理员审核、跨租户知识库或公开资料市场。
- 不解析扫描件、图片资料或需要 OCR 的文件。
- 不自动抓取 URL，不接受用户提交远程地址作为资料。
- 不做增量文件变更监听；重新上传生成新的资料记录。
- 不给问答增加资料标签筛选、排序权重设置或用户可编辑的检索参数。
- 不把用户资料写入现有 `knowledge_sources` allowlist。
- 不承诺首版支持超长书籍；正文超过服务端硬上限时拒绝或截断，规则必须稳定并可测试。

## 3. 技术架构

### 3.1 依赖方向

沿用现有依赖方向：

```text
api -> services -> db / storage / rag / llm
worker -> services / db / storage / rag / llm
```

`app/rag/` 是检索域模块，不导入 `app/api/`，也不自行读取全局状态。Ollama 和数据库通过显式注入的客户端或 Session 使用。

### 3.2 组件职责

| 模块 | 职责 |
| --- | --- |
| `app/api/v1/documents.py` | 上传、列表、详情、删除路由；认证、CSRF、幂等键和 DTO |
| `app/services/documents.py` | 所有者校验、上传事务、幂等、任务入队、状态查询和删除墓碑 |
| `app/rag/contracts.py` | 文档、分块、检索候选、融合结果和 Pydantic Schema |
| `app/rag/ingestion.py` | 文件类型校验、文本提取、规范化、分块、哈希和 embedding 批处理 |
| `app/rag/retrieval.py` | 查询 embedding、pgvector Top-K、BM25 Top-K、RRF 融合和证据裁剪 |
| `app/rag/ollama.py` | Ollama `/api/embed` 客户端、超时、有限重试、维度校验和错误映射 |
| `app/db/models.py` | 用户资料、分块、索引状态和证据来源字段 |
| `app/worker.py` | `process_document`、`delete_document` 和保留清理任务 |
| `web/src/pages/DocumentsPage.tsx` | 资料库列表、上传、状态和删除 |
| `web/src/pages/QaDetailPage.tsx` | 显示系统资料与个人资料证据来源 |

### 3.3 核心链路

```text
上传资料
  -> 鉴权、CSRF、幂等键
  -> 扩展名/MIME/魔数/大小校验
  -> 写入私有对象存储
  -> 创建 user_document(state=uploaded)
  -> 创建 process_document 任务
  -> 返回 202

Worker
  -> 读取并再次校验对象
  -> 提取文本并规范化
  -> 固定版本分块并计算 token/哈希
  -> 调用 Ollama 批量 embedding
  -> 事务写入 chunks 和 ready 状态
  -> 失败按现有租约重试，耗尽后 failed

问答
  -> 生成问题 embedding
  -> 当前 owner 的 ready 资料做 pgvector Top 20
  -> 当前 owner 的 ready 资料 + 系统 allowlist 资料做 BM25 Top 20
  -> RRF 融合
  -> 取 Top 5，冻结 qa_evidence 快照
  -> 现有结构化回答和 SSE
```

## 4. 数据模型

### 4.1 `user_documents`

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID | PK |
| `owner_user_id` | UUID | FK `users.id`，非空 |
| `title` | text | 非空，展示标题 |
| `original_filename` | text | 非空，仅个人可见 |
| `detected_mime` | text | 非空 |
| `size_bytes` | bigint | `1..10485760` |
| `sha256` | text | 文件内容哈希 |
| `object_key` | text | 私有存储键，唯一，不返回 API |
| `state` | enum | `uploaded`、`processing`、`ready`、`failed`、`deleted` |
| `failure_code` | text | 可空，稳定错误码 |
| `error_message` | text | 可空，仅展示中性原因 |
| `chunk_count` | integer | 默认 0 |
| `index_version` | text | 可空，当前为 `rag-v1` |
| `embedding_model` | text | 可空，成功索引时固定模型名 |
| `embedding_dimensions` | integer | 可空，成功索引时固定维度 |
| `deletion_state` | text | 可空；`pending`、`deleted`、`failed`，仅用于异步对象清理 |
| `idempotency_key` | text | 可空，服务端哈希后的幂等键 |
| `request_fingerprint` | text | 可空，上传内容指纹 |
| `created_at` | timestamptz | 非空 |
| `updated_at` | timestamptz | 非空 |
| `completed_at` | timestamptz | 可空 |
| `deleted_at` | timestamptz | 可空 |
| `retention_expires_at` | timestamptz | 非空，默认 90 天 |

约束与索引：

- `UNIQUE (owner_user_id, sha256) WHERE deleted_at IS NULL`，同用户相同内容复用现有记录。
- `UNIQUE (owner_user_id, idempotency_key) WHERE idempotency_key IS NOT NULL`。
- `INDEX (owner_user_id, created_at DESC)`。
- `INDEX (owner_user_id, state, updated_at)`。
- `CHECK (state IN (...))`、`CHECK (size_bytes > 0 AND size_bytes <= 10485760)`、`CHECK (chunk_count >= 0)`。
- 删除采用墓碑：先写 `deleted_at` 和 `state='deleted'`，再异步删对象；检索查询必须同时满足 `deleted_at IS NULL` 和 `state='ready'`。

### 4.2 `user_document_chunks`

| 字段 | 类型 | 约束/说明 |
| --- | --- | --- |
| `id` | UUID | PK |
| `document_id` | UUID | FK `user_documents.id`，级联删除 |
| `owner_user_id` | UUID | FK `users.id`，非空 |
| `chunk_index` | integer | 从 0 开始 |
| `section_path` | text | 提取出的章节或稳定序号，如 `正文 / 1` |
| `content` | text | 规范化分块正文，不返回完整原文给问答 DTO |
| `content_hash` | text | 分块哈希 |
| `token_count` | integer | 用于预算和展示限制 |
| `embedding` | `vector(1024)` | bge-m3 向量，非空 |
| `created_at` | timestamptz | 非空 |

约束与索引：

- `UNIQUE (document_id, chunk_index)`。
- `INDEX (owner_user_id, document_id)`。
- `CHECK (chunk_index >= 0)`、`CHECK (token_count > 0)`。
- 分块正文和向量只在 owner 过滤后参与检索。
- 不对 `content` 建立全文索引；BM25 使用独立 `search_vector`。

### 4.3 `user_document_chunks` 的 BM25 字段

为同一分块增加：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `search_text` | text | 规范化分词文本，保留中文双字切分和英文词项 |
| `search_vector` | `tsvector` | 由 `search_text` 生成，`GIN` 索引 |

本项目把 PostgreSQL `ts_rank_cd` 作为 BM25 风格词法排序，不宣称它与独立 BM25 实现逐值等价。配置按中文预处理后的 `simple` 字典；英文专用词项也保留在预处理文本中。这样不依赖额外扩展，同时保持现有部署可控。

### 4.4 扩展字段

- `qa_evidence` 增加：`source_kind`（`system` / `user_document`）、`user_document_chunk_id`（可空 FK，删除时 `SET NULL`）。
- 公开证据 DTO 增加 `source_kind`；不暴露 `user_document_id`、对象键、owner ID 或 chunk ID。
- `async_jobs.job_type` 增加 `process_document`、`delete_document`。
- `data_deletion_requests.scope` 增加 `user_documents`。

## 5. 文件接收与解析

支持格式：

- `.pdf`：`application/pdf`，复用 `pypdf` 提取文本。
- `.docx`：现有 DOCX MIME，复用 `python-docx`。
- `.txt`：`text/plain`。
- `.md`：`text/markdown` 或 `text/plain`，按 UTF-8 文本读取。

校验顺序：

1. 文件名 basename 化、去除路径和控制字符。
2. 扩展名、声明 MIME、魔数（文本格式校验可读性）和大小。
3. 文本可提取且非空。
4. 正文长度不超过 `DOCUMENT_MAX_CHARACTERS`，默认 200000。
5. 规范化空白、控制字符和重复空行。

解析失败返回稳定错误码：

- `unsupported_source`
- `file_too_large`
- `text_extraction_unsupported`
- `document_too_large`
- `idempotency_conflict`

分块：

- 目标 800 字符、重叠 100 字符，按段落和句子边界优先切分。
- 单个分块最多 1200 字符，至少 1 个有效字符。
- 记录稳定 `section_path` 和 `chunk_index`，确保重建索引可重复。

## 6. Ollama Embedding 契约

配置项：

```text
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
OLLAMA_EMBEDDING_DIMENSIONS=1024
OLLAMA_CONNECT_TIMEOUT_SECONDS=5
OLLAMA_REQUEST_TIMEOUT_SECONDS=30
OLLAMA_MAX_RETRIES=2
```

请求：

```http
POST {OLLAMA_BASE_URL}/api/embed
Content-Type: application/json
```

```json
{
  "model": "bge-m3",
  "input": ["分块一", "分块二"]
}
```

响应校验：

- `embeddings` 数量必须与输入数量一致。
- 每个向量必须全部为有限数值，维度等于 1024。
- 模型名和维度写入资料记录，不能在维度变化时静默混用。
- 超时、连接失败、429、5xx 进入现有有界重试；永久性 4xx 映射为 `embedding_invalid_request`。
- 日志只记录模型名、批量大小、耗时和错误码，不记录正文或向量。

部署：

- Ollama 是独立服务，可运行在同一 Compose 网络或外部私有网络。
- 生产启动校验 Ollama URL、模型名和维度；不在 API 进程内加载模型。
- Ollama 不作为 `/health/ready` 的硬阻塞依赖；其可用性通过问答降级、资料任务失败和指标体现。
- 提供本地 Compose 服务示例，生产环境通过环境变量注入真实地址。

## 7. 混合检索

### 7.1 候选生成

对已就绪资料与系统白名单资料分别执行：

1. **向量召回**
   - 对问题进行 embedding。
   - 在当前 owner 的 `ready` 个人资料分块中，按 `embedding <=> query_embedding` 升序取 Top 20。
   - 系统资料也建立同样的 pgvector 列，按 allowlist 最新发布版本取 Top 20。
2. **BM25 / 全文召回**
   - 使用 PostgreSQL `tsquery` 与 `ts_rank_cd(search_vector, query)` 取 Top 20。
   - 查询词来自现有确定性 tokenizer，保留中文双字片段和英文词项。
3. **空召回**
   - 任一路为空不影响另一条路；两路都为空时回答进入 `model_knowledge` 或 `insufficient`。

### 7.2 RRF 融合

按候选在各自列表中的名次融合：

```text
score(d) = Σ 1 / (k + rank_i(d))
```

- `k=60`，向量和 BM25 权重相同。
- 同一分块在两路出现时只保留一个候选，分数相加。
- 同分时按来源类型（系统资料优先稳定）、标题、`section_path` 和稳定 UUID 排序。
- 融合后取 Top 5 进入证据冻结；每条证据摘要最多 200 字符。

### 7.3 降级

- Ollama 不可用或 embedding 调用最终失败时，记录 `vector_status=degraded`，问答继续只用 BM25。
- 降级不把“模型知识”伪装成检索证据；BM25 有有效结果时仍可标记 `supported`。
- 降级原因只写错误码和指标，不写正文。
- `process_document` 的 embedding 失败不降级为“无向量可检索”；任务按现有 Worker 有界重试，耗尽后资料为 `failed`。

### 7.4 系统资料向量化

现有 `knowledge_source_sections` 增加 `embedding vector(1024)` 和 `search_vector tsvector`。系统资料没有 embedding 时：

- BM25 仍可检索。
- 不伪造向量结果。
- 在资料索引重建完成前，系统资料可继续用词法检索。
- 系统资料增加 `embedding_model`、`embedding_dimensions` 和 `embedding_index_version`；回填任务固定这些值，历史问答继续通过证据快照保持稳定。

## 8. API 契约

### 8.1 上传

```http
POST /api/v1/documents
Content-Type: multipart/form-data
Idempotency-Key: <opaque-key>
X-CSRF-Token: <token>
```

表单字段：

- `file`：必填。
- `title`：可选；默认取安全文件名，最长 120 字符。

成功响应 `202 Accepted`：

```json
{
  "document_id": "uuid",
  "state": "uploaded",
  "created_at": "2026-10-21T08:00:00Z"
}
```

### 8.2 列表

```http
GET /api/v1/documents?cursor=<cursor>&limit=20
```

响应：

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Redis 设计笔记",
      "original_filename": "redis.md",
      "state": "ready",
      "chunk_count": 12,
      "failure_code": null,
      "created_at": "2026-10-21T08:00:00Z",
      "updated_at": "2026-10-21T08:01:00Z"
    }
  ],
  "next_cursor": null
}
```

列表只返回当前用户、未删除且未到期的资料。

### 8.3 详情

```http
GET /api/v1/documents/{document_id}
```

返回同上单条字段，并增加 `error_message`、`completed_at`、`retention_expires_at` 和 `index_version`。不返回对象键、完整正文、chunks 或 embedding。

### 8.4 删除

```http
DELETE /api/v1/documents/{document_id}
Idempotency-Key: <opaque-key>
X-CSRF-Token: <token>
```

成功返回 `204 No Content`。删除事务立即设置 `deleted_at`、`state='deleted'` 并排除检索，随后由 Worker 删除对象和分块。重复删除幂等返回 204。

### 8.5 权限与错误

- 所有接口要求有效会话。
- 所有写接口要求 CSRF、Origin/Referer allowlist 和幂等键。
- 他人资料和不存在的资料统一返回 `404 resource_not_found`。
- 上传/索引不可重试错误返回稳定错误码和中性文案。
- 错误响应沿用现有 `{error: {code, message, retryable, request_id}}` 信封。

## 9. Worker 与生命周期

### 9.1 `process_document`

1. 校验任务租约和 fencing token。
2. 按 `document_id + owner_user_id` 读取未删除资料。
3. 转为 `processing`；读取私有对象并再次校验哈希。
4. 提取、规范化、分块。
5. 批量调用 Ollama embedding。
6. 在单个事务中删除同资料旧 chunks、写入新 chunks、更新 `ready`、`chunk_count`、`index_version`、`embedding_model`、`embedding_dimensions` 和 `completed_at`。
7. 失败写入 `failure_code`，按现有 Worker 重试；耗尽后 `failed`。
8. 任何阶段都必须重新确认租约，旧 Worker 不得覆盖新状态。

### 9.2 `delete_document`

1. 数据库已先行墓碑化后，Worker 读取待删除资料。
2. 删除分块和对象；对象不存在视为成功。
3. 记录完成状态和可审计的最小元数据。
4. 失败保留可重试状态，不恢复资料可见性。

### 9.3 保留与账号删除

- 资料默认保留 90 天，`retention_expires_at` 到期后立即不可见并进入清理。
- `delete_account_data` 范围包含 `user_documents` 和其 chunks。
- 清理任务必须同时处理对象、chunks 和资料元数据，不留下可检索向量。
- 清理失败只记录稳定错误码，不记录正文、向量或对象 URL。

## 10. 前端

新增 `/documents` 页面：

- 页面标题：内部资料库。
- 上传区：文件选择、可选标题、10 MB/格式提示。
- 列表：标题、文件名、状态、分块数、更新时间、失败原因和删除操作。
- 状态：上传中、处理中、可检索、失败、已删除。
- 删除使用确认对话框，成功后从列表移除。
- 失败资料可重新上传，不修改旧记录。
- 列表空状态提供上传 CTA，不使用营销式 hero 或卡片堆叠。

导航：

- `AppShell` 主侧栏增加“内部资料”。
- 工作台增加“内部资料”快捷入口，但不能挤压现有主要操作。

问答：

- 问答页说明“检索当前账号已就绪资料与系统资料”。
- 证据卡显示“系统资料”或“个人资料”。
- 资料删除后，历史证据显示“来源已删除”，但不返回正文。
- 不上传媒体、不做资料预览器。

无障碍与响应式：

- 文件输入有可见标签和错误文本。
- 删除按钮有可访问名称。
- 列表在移动端转为纵向账本布局。
- 状态不只依赖颜色，包含文本和可读状态标签。

## 11. 安全与隐私

- 文件扩展名、声明 MIME、魔数、大小、可提取文本和正文长度均校验。
- 对象存储保持私有，API 永不返回对象键或公开 URL。
- OCR/扫描件不支持时明确失败，不进入索引。
- 资料正文、分块、embedding 和原始响应不写日志、不写 trace payload。
- Ollama 请求只在服务端发起，不接受用户指定模型、URL 或维度。
- 资料内容进入 Prompt 时统一包裹在 `<untrusted>` 中；系统说明只能作为数据。
- 证据摘要最多 200 字符；公开 DTO 不暴露 owner、chunk UUID 或内部对象位置。
- 跨 owner 访问统一 404，不泄露资料存在性。
- 向量索引和 BM25 查询必须先应用 `owner_user_id` 和 `ready/deleted_at` 条件。
- 数据库备份包含资料正文和向量，按现有备份加密与访问控制执行。

## 12. 可观测性

记录以下不含正文的指标/日志字段：

- 上传结果、文件类型、大小、解析耗时。
- 分块数、embedding 批量大小、embedding 耗时、错误码、重试次数。
- 向量候选数、BM25 候选数、融合结果数、降级状态。
- 资料状态、删除结果、对象清理结果。
- trace 关联 `document_id`、`qa_request_id`，不记录正文或对象键。

需要监控：

- 资料处理成功率与 P95 耗时。
- Ollama embedding 失败率、超时率和降级次数。
- pgvector 查询耗时、BM25 查询耗时和 RRF 后证据为空率。
- 删除/保留清理积压和失败数。

## 13. 测试与验收

### 13.1 后端单元与集成

- 文件格式、MIME、魔数、大小、空文本和超长文本校验。
- TXT/Markdown/PDF/DOCX 提取、规范化、分块边界与重叠。
- 同用户相同内容复用；不同用户相同内容互不可见。
- 上传幂等重放、冲突、CSRF 和 404 隐藏。
- Worker 成功写入 chunks 与向量；embedding 失败重试、耗尽和 fencing。
- BM25 在中文/英文混合查询上的召回。
- pgvector 余弦排序和维度校验。
- RRF 排名、去重、同分稳定性、Top 5 裁剪。
- 混合检索 owner 隔离；个人资料与系统资料合并；未 ready 资料排除。
- Ollama 不可用时 BM25 降级，问答仍可完成且证据正确。
- 删除后立即不可检索、对象清理、历史证据标记 `source_deleted`。
- 账号删除和保留到期覆盖资料、分块、向量和对象。
- 证据 DTO 不泄露内部 UUID、对象键或完整正文。

### 13.2 前端

- `/documents` 上传成功、处理中、ready、失败和删除。
- 上传请求包含 CSRF 和稳定幂等键。
- 列表分页、空状态、错误重试和移动布局。
- 资料上传后问答页能展示个人资料证据来源。
- 删除后历史证据显示来源已删除。
- 键盘操作和可访问名称。

### 13.3 评测

新增 `evals/cases/rag-hybrid-boundary.yaml`，覆盖：

- 资料正文中的 prompt injection 只能作为数据。
- 模型只能引用当前请求冻结的 `evidence-N`。
- 跨 owner 资料不可召回。
- 未 ready 或已删除资料不可召回。
- Ollama 不可用时 BM25 降级结果仍受证据边界约束。
- RRF 融合不扩大引用集合。

### 13.4 部署验证

- 本地 Compose 使用支持 pgvector 的 PostgreSQL 镜像。
- 空库升级、降级、再次升级和 `alembic check` 通过。
- Ollama 独立服务可访问，`bge-m3` embedding 维度为 1024。
- API/Worker 启动配置校验和健康检查符合约定。
- 后端 `ruff`、`mypy`、测试、eval 和前端 typecheck、Vitest、ESLint、build、Playwright 全部通过。

## 14. 迁移与发布顺序

1. 切换 PostgreSQL 镜像为兼容 pgvector 的 `pgvector/pgvector` 版本，执行 `CREATE EXTENSION IF NOT EXISTS vector`。
2. 新增资料、分块、证据来源和任务类型迁移。
3. 先在 staging 配置 Ollama 和 `bge-m3`，验证维度与 API 契约。
4. 上线后端接口和 Worker，确认资料处理与删除。
5. 上线前端资料库和问答证据来源展示。
6. 对既有系统资料运行一次性 embedding 回填；回填期间保留 BM25 可用性。
7. 观察处理成功率、降级率、检索延迟和成本，再扩大使用范围。

回滚要求：

- 不回滚已持久化的用户资料或证据快照。
- 回滚应用版本时保留新表，旧版本不得读取它们。
- 向量不可用时只启用 BM25 路由；不得删除已存在的向量列。
- 迁移降级必须明确是否删除资料数据，默认不自动丢弃用户数据。

## 15. 影响文件

后端：

- `app/api/v1/documents.py`
- `app/api/v1/router.py`
- `app/services/documents.py`
- `app/schemas/documents.py`
- `app/rag/*`
- `app/db/models.py`
- `app/worker.py`
- `app/config.py`
- `app/qa_contracts.py`
- `app/services/qa.py`
- `app/schemas/qa.py`
- `migrations/versions/*`

前端：

- `web/src/App.tsx`
- `web/src/components/AppShell.tsx`
- `web/src/pages/DocumentsPage.tsx`
- `web/src/pages/DocumentsPage.test.tsx`
- `web/src/pages/QaDetailPage.tsx`
- `web/src/pages/QaPage.tsx`
- `web/src/pages/WorkspacePage.tsx`
- `web/src/api/client.ts`
- `web/src/api/types.ts`
- `web/src/api/queryKeys.ts`
- `web/src/styles.css`

文档与部署：

- `docs/adr/0009-hybrid-rag-for-private-documents.md`
- `docs/adr/README.md`
- `docs/api-contract.md`
- `docs/data-model.md`
- `docs/technical-design.md`
- `docs/threat-model.md`
- `docs/decision-register.md`
- `README.md`
- `.env.example`
- `compose.yaml`
- `deploy/local.compose.yaml`
- `deploy/production.compose.yaml`
- `.github/workflows/ci.yml`

## 16. 依赖与版本风险

- `pgvector` Python 包用于 SQLAlchemy 向量类型和 Alembic 迁移；版本需锁定并记录原因。
- PostgreSQL 镜像必须包含 `vector` 扩展；部署前验证扩展版本。
- `bge-m3` 模型名和 1024 维必须显式配置，不能根据响应静默变更。
- Ollama 是独立服务，必须验证网络、模型加载、超时和并发限制。
- BM25 通过 PostgreSQL `ts_rank_cd` 实现，不额外引入搜索服务；中文预处理必须固定版本并纳入测试。

## 17. 审批与后续

本规格需要项目负责人审查。批准后：

1. 使用 `writing-plans` 生成实现计划。
2. 按计划先做数据库和配置迁移，再做服务与 Worker，再做前端和评测。
3. 每个阶段执行对应质量门禁，不以未验证代码替代完成定义。
