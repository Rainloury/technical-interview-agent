# ADR-0009：私有内部资料采用 pgvector、BM25 和 RRF 混合检索

| 项目 | 内容 |
| --- | --- |
| 状态 | `accepted` |
| 日期 | 2026-10-21 |
| 审批日期 | 2026-10-21 |
| 决策者 | 项目负责人 |
| 评审状态 | 已批准 |
| 影响 | 数据、存储、检索、Worker、API、前端、部署、成本 |

## 背景

当前技术问答只检索后台 allowlist 的已发布知识源，普通用户无法上传自己的技术资料。用户需要把个人资料加入私有知识库，并在不提供资料选择器的前提下，让问答自动使用当前账号的已就绪资料和系统资料。现有检索是 PostgreSQL 内确定性词法排序，没有向量检索、分块表或资料归属模型。

## 决策

- 每个用户拥有独立私有资料库；资料、分块、对象和证据都按 `owner_user_id` 隔离。
- 支持 PDF、DOCX、TXT、Markdown，上传后异步解析、分块、embedding 和索引。
- 使用独立 Ollama 服务提供 embedding，当前部署为 `mxbai-embed-large:latest`，默认 1024 维；模型、维度和服务地址显式配置。
- 使用 PostgreSQL pgvector 存储向量，使用 HNSW 余弦索引做候选召回。
- 使用 PostgreSQL `ts_rank_cd` 做 BM25 风格词法召回，中文采用固定字符级预处理。
- 向量与 BM25 各取 Top 20，通过 RRF（`k=60`，等权）融合后取 Top 5。
- Ollama 不可用时问答降级为 BM25；资料索引任务不降级为无向量资料，按 Worker 有界重试并在耗尽后失败。
- 问答自动检索当前用户 ready 资料和系统 allowlist 资料，不增加资料选择器。
- 公开证据只包含 `citation_id`、标题、章节、摘要、相关度、来源类型和来源状态；不暴露 owner、chunk UUID 或对象键。
- 资料上传、删除、账号删除和保留清理沿用现有幂等、软删除、私有对象存储和 Worker fencing 机制。

## 替代方案

1. 只做 BM25：实现简单、无 embedding 依赖，但无法满足语义相近问法召回，已明确不选。
2. 只做向量检索：语义召回强，但对精确术语、版本号、错误码和专有名词不稳定，且 Ollama 故障会完全阻断检索。
3. 引入托管向量数据库或搜索服务：可扩展，但增加部署、网络、权限、成本和数据出域面，不符合当前 MVP。
4. 在 API 进程内加载 embedding 模型：减少服务数量，但会显著增加 API 内存、冷启动和资源争用。
5. 用户上传资料直接写入现有 allowlist：会让跨用户共享和审核语义混入个人资料，违反私有资料边界。

## 后果

- 需要 pgvector 数据库镜像、`vector` 扩展、向量索引和迁移；部署和备份要求提高。
- 需要独立 Ollama 服务，增加一个内部网络依赖和模型资源管理项。
- 问答链路增加 embedding 调用、两路召回和融合，首段延迟和成本需要单独观测。
- BM25 中文预处理需要固定版本；改动分词规则会影响历史检索一致性。
- 资料处理失败、Ollama 降级和清理积压需要单独告警或指标。
- 用户资料正文和向量进入数据库与备份范围，必须遵守现有隐私保留策略。

## 影响文件

- `app/rag/`
- `app/services/documents.py`
- `app/api/v1/documents.py`
- `app/db/models.py`
- `app/worker.py`
- `app/qa_contracts.py`
- `app/services/qa.py`
- `app/schemas/qa.py`
- `migrations/versions/*`
- `web/src/pages/DocumentsPage.tsx`
- `web/src/pages/QaDetailPage.tsx`
- `compose.yaml`
- `deploy/local.compose.yaml`
- `deploy/production.compose.yaml`
- `pyproject.toml`
- `requirements.txt`
- `uv.lock`

## 验证

- 空库迁移、降级、再次升级和 `alembic check` 通过，`vector` 扩展可用。
- `mxbai-embed-large:latest` 返回 1024 维有限数值向量；维度不匹配时拒绝写入。
- 用户资料与系统资料都能进入混合检索，RRF 结果稳定且不超过 Top 5。
- 其他用户资料、未 ready 资料和已删除资料不进入向量或 BM25 候选。
- Ollama 超时/不可用时问答降级 BM25，并留下稳定错误码和降级指标。
- 资料删除、账号删除、保留到期和 Worker fencing 验证通过。
- 问答证据只暴露允许字段，资料正文中的注入内容不改变系统行为。
- 前后端质量门禁、迁移门禁、RAG eval 和部署合同测试通过。

## 审批

本 ADR 与 `docs/superpowers/specs/2026-10-21-user-rag-design.md` 已于 2026-10-21 获项目负责人批准，状态为 `accepted`。
