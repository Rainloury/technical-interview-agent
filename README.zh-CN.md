# Technical Interview Agent

[English](README.md) | 简体中文 | [在线站点](https://it.rainstone.top)

一个可自托管的技术面试平台，包含有界回答智能体、私有资料检索和异步 Worker。

> 当前状态：发布候选（release candidate）。隐私与可观测门禁、真实 provider
> 三档单轮 eval、G4A 行为矩阵、整场成本门禁、本地恢复/回滚和告警送达演练均已
> 通过；生产环境复核、发布 SHA 冻结与发布批准待完成。详细发布证据与内部验收
> 记录见 [`docs/README.md`](docs/README.md) 和
> [`docs/release-runbook.md`](docs/release-runbook.md)。

应用提供：

- 账号注册、会话管理、密码重置和带 CSRF 防护的写请求；
- 简历上传、技术问答、模拟面试、终态报告和复习中心；
- 内部资料库，支持 PDF、DOCX、TXT 和 Markdown 文件；
- 管理员维护的共享资料，所有登录账号可见；
- 按文件异步索引，以及按 owner 隔离的混合检索；
- pgvector 余弦检索与 PostgreSQL BM25 风格词法检索，并通过倒数排名融合
  （RRF）合并结果；
- 问答时自动使用当前账号已就绪的资料，不提供资料选择器；
- embedding 服务不可用时确定性地降级为词法检索；
- 默认使用 `mxbai-embed-large:latest` 的 1024 维 embedding；
- React 前端和 Docker Compose 部署。

本服务面向技术面试工作流，不是通用聊天机器人，也不会自动执行外部写操作。

会话使用服务端 `interview_session` Cookie（`HttpOnly`），并提供独立的
`interview_csrf` 校验值配合 `X-CSRF-Token` 检查。数据库只在
`auth_sessions.csrf_token_hash` 保存哈希。分页历史接口返回
`{items, next_cursor}`。

## 架构

```text
Browser
  |
  v
Nginx web container
  |-- static React application
  `-- /api and /health proxy
          |
          +--> FastAPI API
          |      |-- PostgreSQL + pgvector
          |      |-- Redis
          |      |-- model provider
          |      `-- Ollama embeddings
          |
          `--> async worker
                 |-- document extraction and indexing
                 |-- interview processing
                 |-- password-reset delivery
                 `-- retention cleanup
```

Python 应用遵循 `api -> agent -> tools -> llm` 的依赖方向。PostgreSQL 是会话和
异步任务的权威数据源。架构决策见 [`docs/adr/`](docs/adr/README.md)，当前设计见
[`docs/technical-design.md`](docs/technical-design.md)。

## 快速开始

### 本地全容器部署

前置条件：安装带 Compose 的 Docker。

```bash
cp .env.example .env
docker compose -f deploy/local.compose.yaml up --build --detach
```

打开 `http://127.0.0.1:8080`。该编排会在容器内运行 PostgreSQL、Redis、数据库
迁移、API、Worker 和 Web 服务，不向宿主机发布 PostgreSQL、Redis 或 API 端口。

embedding 需要独立部署的 Ollama 服务。本地使用时，将 `.env` 中的
`OLLAMA_BASE_URL` 设置为容器可访问的地址，例如
`http://host.docker.internal:11434`。默认模型为
`mxbai-embed-large:latest`，维度为 1024。Ollama 不可用时，问答会降级为词法
检索；资料索引会重试，最终干净失败，不会写入部分向量。

### Python 与前端开发

前置条件：

- Python 3.11 或 3.12，以及 [uv](https://docs.astral.sh/uv/)
- Node.js 22 和 npm
- 带 pgvector 的 PostgreSQL 和 Redis，或使用 Docker 启动这两个服务

```bash
uv sync
cp .env.example .env
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

在另一个终端启动前端：

```bash
cd web
npm ci
npm run dev
```

API 默认监听 `http://127.0.0.1:8000`，Vite 前端默认监听
`http://127.0.0.1:3001`。可通过 `VITE_API_BASE_URL` 覆盖前端使用的 API 地址。

## 配置

配置通过 `app/config.py` 加载，并由 `.env.example` 说明。将示例复制为 `.env`
后只在本地填写实际值。禁止提交 `.env`、凭据、私钥或生产地址。

主要配置项：

| 类别 | 配置项 |
| --- | --- |
| 运行环境 | `APP_ENV`、`APP_DEBUG`、`APP_ALLOWED_ORIGINS` |
| PostgreSQL | `DATABASE_URL` |
| Redis | `REDIS_URL` |
| 会话 | `SESSION_COOKIE_NAME`、`CSRF_COOKIE_NAME`、`COOKIE_SECURE`、`DATA_ENCRYPTION_KEY` |
| 模型 provider | `LLM_PROVIDER`、`LLM_API_KEY`、`LLM_BASE_URL`、各档模型名 |
| Embedding | `OLLAMA_BASE_URL`、`OLLAMA_EMBEDDING_MODEL`、`OLLAMA_EMBEDDING_DIMENSIONS` |
| 简历存储 | `RESUME_STORAGE_BACKEND`、本地路径或兼容 OSS 的配置 |
| 邮件 | `SMTP_HOST`、`SMTP_PORT`、`SMTP_SECURITY`、账号和发件人 |
| Worker | `WORKER_CONCURRENCY`、运行时限和停机参数 |

Staging 和 production 启动时会校验必需的安全配置，缺失时快速失败。生产模板见
[`deploy/production.env.example`](deploy/production.env.example)。

## 内部资料检索

登录用户可上传一个或多个 PDF、DOCX、TXT 或 Markdown 文件，单文件最大 10 MB。
批量接口会为每个文件分别创建资料记录和索引任务。Worker 按文件逐个提取、分块、
embedding 并独立存储。

公开资料接口按 owner 隔离：

```text
POST   /api/v1/documents
POST   /api/v1/documents/batch
GET    /api/v1/documents
GET    /api/v1/documents/{document_id}
DELETE /api/v1/documents/{document_id}
```

管理员还可以维护共享资料。所有登录账号都能查看共享资料，但只有管理员可以上传或删除：

```text
POST   /api/v1/shared-documents
POST   /api/v1/shared-documents/batch
GET    /api/v1/shared-documents
GET    /api/v1/shared-documents/{document_id}
DELETE /api/v1/shared-documents/{document_id}
```

个人资料仍然按 owner 隔离，即使管理员也不能读取他人的个人资料。共享资料进入
`ready` 后会对所有登录账号自动参与检索。

只有处于 `ready` 状态的资料参与检索。删除资料会立即停止后续检索；历史证据标记
为 `source_deleted`，存储内容由 Worker 异步清理。

检索先分别取得余弦候选和词法候选的 Top 20，再使用等权 RRF（`k=60`）融合，
最终返回 Top 5。完整契约见 [`docs/api-contract.md`](docs/api-contract.md)，
设计原因见
[ADR-0009](docs/adr/0009-hybrid-rag-for-private-documents.md)。

## 开发

后端检查：

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
```

集成测试需要 PostgreSQL 和 Redis：

```bash
RUN_INTEGRATION=1 uv run pytest -m integration -q
```

前端检查：

```bash
cd web
npm run typecheck
npm test -- --run
npm run lint
npm run build
npm run test:e2e
```

确定性评测与依赖真实 provider 的评测彼此独立：

```bash
uv run python -m evals.run
uv run python -m evals.provider_behavior
```

第二条命令会调用真实 provider，并要求已配置 `LLM_API_KEY`。Provider 评测为显式
联网操作。

项目规则和智能体约束见 [`AGENTS.md`](AGENTS.md)，公开文档入口为
[`docs/README.md`](docs/README.md)。

## 部署

生产环境使用独立的 `migrate`、`api`、`worker` 和 `web` 服务，只暴露 Nginx
入口。API 和 Worker 镜像以非 root 用户运行，并在支持时使用只读根文件系统。

部署和回滚流程见 [`docs/release-runbook.md`](docs/release-runbook.md)，生产
编排见 [`deploy/production.compose.yaml`](deploy/production.compose.yaml)。

构建镜像：

```bash
docker build --pull -t technical-interview-agent:v0.1.0 .
docker build --pull -t technical-interview-agent-web:v0.1.0 web/
```

生产发布应使用不可变镜像 digest。生产环境文件应放在仓库外，通过密钥管理器或
部署平台注入。

## Android

Capacitor Android 工程位于 `web/android`，加载
`https://it.rainstone.top` 的同源生产站点。本地构建、release 签名、
GitHub Actions 与 Google Play Console 步骤见
[`docs/android-release.zh-CN.md`](docs/android-release.zh-CN.md)。

## 参与贡献

提交 Pull Request 前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md)。参与项目即表示
遵守 [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)。

- 支持与 Issue 指引：[`SUPPORT.md`](SUPPORT.md)
- 安全问题报告：[`SECURITY.md`](SECURITY.md)
- 版本记录：[`CHANGELOG.md`](CHANGELOG.md)
- 依赖与字体声明：[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)

## 许可证

Copyright 2026 Rainloury.

本项目依据 [Apache License, Version 2.0](LICENSE) 授权。
