# Technical Interview Agent

技术面试问答与模拟面试智能体服务。项目规则见 `AGENTS.md`，需求与技术基线见 `docs/`。

当前阶段：**上线质量切片进行中；隐私与可观测门禁已通过**。`web/` 已实现注册、登录、找回/重置密码、工作台、四类历史分页、桌面/移动导航、简历闭环、检索问答、模拟面试、终态报告、复习中心和账号数据删除确认。后端已接通账号、会话、工作台、历史、异步 Worker、检索问答、面试评分/追问/报告、隐私删除、保留清理与运维聚合指标。技术设计与流程基线分别为 `docs/technical-design.md` v0.14、`docs/development-flow.md` v3.0。真实 provider 三档单轮 eval 已通过；110 条行为矩阵为 `82/110`，完整 G4A 模型矩阵仍未关闭。

登录签发服务端会话 Cookie `interview_session`（`HttpOnly`、`Secure`、`SameSite=Lax`），同时签发前端可读的 `interview_csrf`；写请求通过 `X-CSRF-Token` 校验，数据库在 `auth_sessions.csrf_token_hash` 保存 CSRF 哈希，历史接口返回 `{items, next_cursor}`。

真实 provider 三档单轮 eval 已通过：FAST `deepseek-flash`、DEFAULT/REASONING `deepseek-v4-pro`，均为 2 steps、正确调用 `add` 并返回 `42`；本轮成本分别约 `$0.000465`、`$0.002612`、`$0.002311`，Prompt `agent_system@1.0.0+agent_turn@1.1.0`。这只证明三档单轮纵向链路可用，**完整 G4A 模型矩阵仍未关闭**。

上线质量门禁证据：前端 `typecheck`、Vitest `12 files / 37 tests`、ESLint、生产构建通过；后端 `ruff`、格式检查、`mypy`（71 files）、`RUN_INTEGRATION=1 pytest`（`140 passed`）和 `alembic check` 通过，迁移头 `9f4c2a7d1e30`；确定性 eval `7/7`；Playwright 桌面与移动视口 `14 passed`，其中隐私专项 `2 passed`。隐私门禁覆盖删除请求幂等、立即隐藏业务数据、对象与业务主体清理、30/90/365 天保留清理、审计最小化、会话失效和双视口删除确认。G4A 当前证据是三档单轮行为和 LLM 异常边界测试通过；110 条真实矩阵为 `82/110`，未达到发布门槛。单次评分调用成本 P95 为 ¥0.097853，但完整面试成本 P95（5 个主问题、追问链和检索）仍未测量。生产邮件供应商与生产对象存储仍是发布前事项。

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
`uv run python -m evals.provider_behavior` 是显式联网的 `G4A` 验收入口；它要求 `.env` 中已配置 `LLM_API_KEY`，并将模型、Prompt 版本、工具调用、token、费用和延迟证据保存到 `/private/tmp/technical-interview-agent-provider-eval.json`。确定性测试不会自动调用它。FAST、DEFAULT、REASONING 三档单轮已验证；`uv run python -m evals.provider_matrix` 运行 110 条真实行为矩阵并写入 `evals/provider_matrix.json`。矩阵记录的是单次评分调用成本，不能替代完整面试成本 P95。

仅首次建立或经批准更新评测基线时执行：

```bash
uv run python -m evals.run --save-baseline
```

模型档位默认来自 `app/llm/models.py`；当前 DeepSeek 账号可用的模型是 `deepseek-flash` 与 `deepseek-v4-pro`，`.env.example` 已按这两项配置三档映射。如需切换账号已开通的具体模型，在 `.env` 中覆盖 `LLM_FAST_MODEL`、`LLM_DEFAULT_MODEL`、`LLM_REASONING_MODEL`。`deepseek-v4.1-flash` 不在供应商 `/models` 列表中，批量评测会在调用前通过 preflight 拒绝。Prompt 目录和工具结果限制也可通过 `.env.example` 中的对应配置调整。
