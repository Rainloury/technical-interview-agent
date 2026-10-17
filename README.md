# Technical Interview Agent

技术面试问答与模拟面试智能体服务。项目规则见 `AGENTS.md`，需求与技术基线见 `docs/`。

当前阶段：**检索问答切片验收通过，准备进入模拟面试与报告切片**。`web/` 已实现注册、登录、找回/重置密码、工作台、四类历史分页、桌面/移动导航、简历上传/处理/出题/删除，以及 `/qa`、`/qa/:id` 的检索问答、流式状态、证据展示、失败恢复和历史重开。后端已接通账号、会话、工作台、历史、简历任务、异步 Worker、`POST /api/v1/qa`、`GET /api/v1/qa/{id}` 和 `GET /api/v1/qa/{id}/stream`。技术设计与流程基线分别为 `docs/technical-design.md` v0.12、`docs/development-flow.md` v2.8。

登录签发服务端会话 Cookie `interview_session`（`HttpOnly`、`Secure`、`SameSite=Lax`），同时签发前端可读的 `interview_csrf`；写请求通过 `X-CSRF-Token` 校验，数据库在 `auth_sessions.csrf_token_hash` 保存 CSRF 哈希，历史接口返回 `{items, next_cursor}`。

真实 provider FAST eval 已通过（`deepseek-flash`，2 steps，tokens `773 / 131`，latency `3471ms`，cost `$0.0003891`，Prompt `agent_system@1.0.0+agent_turn@1.1.0`）。这只证明 FAST 档位的一次真实纵向链路可用，**完整 G4A 模型矩阵仍未关闭**。

账号、简历与检索问答切片的验收证据：前端 `typecheck`、Vitest `9 files / 32 tests`、ESLint、生产构建全部通过；后端 `ruff`、格式检查、`mypy`（84 files）、`RUN_INTEGRATION=1 pytest`（`116 passed`）和 `alembic check` 全部通过，迁移头为 `4b6e9d2c1a70`；确定性 eval `3/3`；Playwright 在桌面 Chromium 与移动 Chrome 视口下 `8 passed`，其中问答专项 `4 passed`。检索问答覆盖 owner 隔离、幂等、任意 URL 拒绝、allowlist/最新发布版本、证据冻结、引用校验、失败重试、持久 SSE 游标重放、终态事件互斥和前端历史重开。当前 Playwright 版本不支持 macOS 13 的 WebKit 二进制，因此本轮没有 WebKit 覆盖。生产邮件供应商、生产对象存储、模拟面试与报告/复习切片、完整 G4A 模型矩阵尚未完成。

## 本地启动

```bash
cp .env.example .env
uv sync
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

服务默认监听 `http://127.0.0.1:8000`。

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

`web/playwright.config.ts` 默认使用本机 Google Chrome 通道，适合当前 macOS 13 环境；在具备对应浏览器二进制的 CI 环境中可恢复 Chromium/WebKit 项目矩阵。

没有 PostgreSQL 和 Redis 时，默认测试仍可运行；集成测试通过 `RUN_INTEGRATION=1` 显式启用。
`uv run python -m evals.run` 当前运行可在无网络环境重复执行的 HTTP 与 Agent 行为用例，不会调用真实供应商。
`uv run python -m evals.provider_behavior` 是显式联网的 `G4A` 验收入口；它要求 `.env` 中已配置 `LLM_API_KEY`，并将模型、Prompt 版本、工具调用、token、费用和延迟证据保存到 `/private/tmp/technical-interview-agent-provider-eval.json`。确定性测试不会自动调用它。当前已完成 FAST 档位的真实 provider 验证；DEFAULT、REASONING、异常边界和发布成本门槛仍需纳入完整 G4A 模型矩阵。

仅首次建立或经批准更新评测基线时执行：

```bash
uv run python -m evals.run --save-baseline
```

模型档位默认来自 `app/llm/models.py`；如需使用账号已开通的具体模型，在 `.env` 中设置 `LLM_FAST_MODEL`、`LLM_DEFAULT_MODEL`、`LLM_REASONING_MODEL`。Prompt 目录和工具结果限制也可通过 `.env.example` 中的对应配置调整。
