# Technical Interview Agent

技术面试问答与模拟面试智能体服务。项目规则见 `AGENTS.md`，需求与技术基线见 `docs/`。

当前阶段：**发布候选（release candidate）；P0 业务切片、质量门禁、隐私与可观测门禁、G4A 行为矩阵、本地恢复/回滚和告警送达演练已通过；生产环境复核、发布 SHA 冻结与发布批准待完成**。`web/` 已实现注册、登录、找回/重置密码、工作台、四类历史分页、桌面/移动导航、简历闭环、检索问答、模拟面试、终态报告、复习中心和账号数据删除确认。后端已接通账号、会话、工作台、历史、异步 Worker、检索问答、面试评分/追问/报告、隐私删除、保留清理与运维聚合指标。技术设计与流程基线分别为 `docs/technical-design.md` v0.21、`docs/development-flow.md` v3.7。真实 provider 三档单轮 eval 已通过；G4A 行为矩阵已通过，整场成本 P95 为 ¥0.83908；生产 DirectMail/OSS 和 GitHub Actions WebKit 均已通过。

登录签发服务端会话 Cookie `interview_session`（`HttpOnly`、`Secure`、`SameSite=Lax`），同时签发前端可读的 `interview_csrf`；写请求通过 `X-CSRF-Token` 校验，数据库在 `auth_sessions.csrf_token_hash` 保存 CSRF 哈希，历史接口返回 `{items, next_cursor}`。

真实 provider 三档单轮 eval 已通过：FAST `deepseek-flash`、DEFAULT/REASONING `deepseek-v4-pro`，均为 2 steps、正确调用 `add` 并返回 `42`；本轮成本分别约 `$0.000465`、`$0.002612`、`$0.002311`，Prompt `agent_system@1.0.0+agent_turn@1.1.0`。三档单轮、110 条行为矩阵和整场成本门禁均已通过。

上线质量门禁证据：前端 `typecheck`、Vitest `12 files / 37 tests`、ESLint、生产构建通过；后端 `ruff`、格式检查、`mypy`（112 files）、默认测试 `166 passed, 51 skipped`、`RUN_INTEGRATION=1 pytest`（`206 passed`）和 `alembic check` 通过，迁移头 `7e2b4c6d8f10`；确定性 eval `7/7`；Playwright Chromium 桌面与移动视口 `14 passed`，其中隐私专项 `2 passed`。GitHub Actions Ubuntu 24.04 托管 runner 的 Playwright WebKit Desktop Safari + iPhone 13 共 `14 passed`（2.4 min）；本地 Ubuntu WebKit 同套件 `14 passed`。G4A 行为矩阵完整复跑 `108/110`，两条共享契约修正后定向复验 `2/2`，合计 `110/110`。10 场真实整场面试全部覆盖追问，累计 74 次模型调用；模型与检索成本 P95 为 ¥0.83908，低于 ¥3.00。DirectMail 已验证 TLS、登录和实际发送；阿里云 OSS 真实私有桶已验证简历上传、读取与删除。生产配置在启动时执行 fail-fast；五类告警已通过真实 webhook 演练；生产环境与通知渠道复核仍按[发布与回滚运行手册](docs/release-runbook.md)关闭。

## 本地启动

```bash
cp .env.example .env
uv sync
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`。

生产 Worker 使用同一安装入口：

```bash
uv run technical-interview-agent worker
```

Worker 启动时会执行生产配置校验、注册 `SIGINT`/`SIGTERM` 停止信号，并按 `WORKER_CONCURRENCY`、`WORKER_MAX_RUNTIME_SECONDS`、`WORKER_IDLE_SECONDS` 有界轮询。生产必须使用 OSS，不能改用 E2E 的确定性 Worker 脚本。

前端位于 `web/`：

```bash
cd web
npm ci
npm run dev -- --port 3001
```

默认请求 `http://127.0.0.1:8000`，可通过 `VITE_API_BASE_URL` 覆盖。

## 质量命令

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
RUN_INTEGRATION=1 uv run pytest -m integration -q
uv run python -m evals.run
uv run python -m evals.provider_behavior
```

前端质量门禁：

```bash
cd web
npm run typecheck
npm test -- --run
npm run lint
npm run build
npm run test:e2e
```

`web/playwright.config.ts` 默认使用本机 Google Chrome；设置 `E2E_BROWSER=webkit` 可运行 Desktop Safari 与 iPhone 13 WebKit 项目。GitHub Actions 的 `webkit-e2e` job 在 `ubuntu-latest` 上启动 PostgreSQL/Redis、安装 WebKit 并运行完整双视口 E2E，可通过 `workflow_dispatch` 手动触发。

没有 PostgreSQL 和 Redis 时，默认测试仍可运行；集成测试通过 `RUN_INTEGRATION=1` 显式启用。
`uv run python -m evals.run` 当前运行可在无网络环境重复执行的 HTTP 与 Agent 行为用例，不会调用真实供应商。
`uv run python -m evals.provider_behavior` 是显式联网的 `G4A` 验收入口；它要求 `.env` 中已配置 `LLM_API_KEY`，并将模型、Prompt 版本、工具调用、token、费用和延迟证据保存到 `/private/tmp/technical-interview-agent-provider-eval.json`。确定性测试不会自动调用它。FAST、DEFAULT、REASONING 三档单轮已验证；`uv run python -m evals.provider_matrix` 运行 110 条真实行为矩阵并写入 `evals/provider_matrix.json`。矩阵记录的是单次评分调用成本，不能替代完整面试成本 P95。

仅首次建立或经批准更新评测基线时执行：

```bash
uv run python -m evals.run --save-baseline
```

模型档位默认来自 `app/llm/models.py`；DeepSeek 模式默认使用 `deepseek-flash` 与 `deepseek-v4-pro`，`.env.example` 已按这两项配置三档映射。如需切换账号已开通的具体模型，在 `.env` 中覆盖 `LLM_FAST_MODEL`、`LLM_DEFAULT_MODEL`、`LLM_REASONING_MODEL`。OpenAI 兼容服务可设置 `LLM_PROVIDER=openai`，并把 `LLM_BASE_URL` 填成完整端点（以 `/chat/completions` 结尾）；客户端会自动推导 SDK 根地址并走流式 Chat Completions，累计 SSE 内容后执行同一套 Schema 校验。该模式不依赖 `/models` 预检。Prompt 目录和工具结果限制也可通过 `.env.example` 中的对应配置调整。

生产依赖：

- 邮件：阿里云 DirectMail，`SMTP_HOST=smtpdm.aliyun.com`；当前验证通过的是 465 端口 + `SMTP_SECURITY=ssl`（TLS、登录和实际发送成功），587/StartTLS 在本地网络不可达。
- 对象存储：阿里云 OSS。设置 `RESUME_STORAGE_BACKEND=oss`、`OSS_ENDPOINT`、`OSS_BUCKET`、`OSS_ACCESS_KEY_ID`、`OSS_ACCESS_KEY_SECRET`，存储桶必须私有。
