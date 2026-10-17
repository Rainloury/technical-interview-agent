# 下一步执行计划

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.5 |
| 文档状态 | 简历纵向切片验收通过，进入检索问答准备 |
| 更新日期 | 2026-10-17 |
| 当前阶段 | 简历纵向切片验收通过，准备进入检索问答切片 |
| 当前目标 | 建立限定知识源、持久 SSE 事件、证据校验和可重连的问答链路 |
| 后续目标 | 完成检索问答、模拟面试和报告切片，并继续补齐完整 G4A 模型矩阵 |
| 审批依据 | `docs/decision-register.md` v0.8 |

> `DR-01` 至 `DR-07` 已批准，ADR-0001 至 ADR-0008 已接受。工程骨架、核心基座和简历异步 Worker 已落地，真实 provider FAST eval 已通过；完整 G4A 模型矩阵仍未关闭。`web/` 已建立并完成认证、工作台、四类历史分页、移动导航和简历闭环，当前进入检索问答。

## 1. 当前完成度

| 事项 | 状态 | 证据 | 是否阻塞下一步 |
| --- | --- | --- | --- |
| 全流程与阶段门禁 | 已完成 | `docs/development-flow.md` v2.7 | 否 |
| 需求基线 | 已完成 | `docs/requirements.md` v1.5 | 否 |
| 产品方案 | 已完成 | `docs/product-design.md` v1.5 | 否 |
| 需求决策 `DR-01` 至 `DR-07` | `approved` | `docs/decision-register.md` v0.8 | 否 |
| 技术设计 | 已完成 | `docs/technical-design.md` v0.11 | 否 |
| 数据模型与状态机 | 已完成 | `docs/data-model.md` v0.6、`docs/state-machine.md` v0.5 | 否 |
| 接口与安全基线 | 已完成 | `docs/api-contract.md` v0.7、`docs/threat-model.md` v0.6 | 否 |
| ADR-0001 至 ADR-0008 | 全部 `accepted` | `docs/adr/` | 否 |
| Python 工程 | 已完成 | `pyproject.toml`、`uv.lock`、`.python-version` | 否 |
| 应用与数据库骨架 | 已完成 | FastAPI、SQLAlchemy async、Alembic、初始迁移和 Compose | 否 |
| 可观测性与安全入口 | 已完成 | 请求 ID、结构化日志、脱敏、trace 契约和统一错误信封 | 否 |
| LLM 档位与 Client | 已完成 | `app/llm/`；OpenAI/Anthropic 适配、重试、Schema 校验、trace 和费用统计测试通过 | 否 |
| Prompt 与 Tool Registry | 已完成 | Markdown 版本加载、变量校验、Pydantic Schema、注册契约、截断与错误回灌测试通过 | 否 |
| Agent Loop 与确定性行为评测 | 已完成 | 三重封顶、嵌套限制、终止、不可信内容、截断和工具选择用例通过；完整工具参数 Schema 已进入 Prompt | 否 |
| 阶段与审批文档契约 | 已完成 | `tests/test_decision_docs.py` 锁定 `DR-07`、首切片边界和当前阶段证据 | 否 |
| 集成、迁移与确定性评测 | 已完成 | `RUN_INTEGRATION=1 pytest` 为 `107 passed`；`alembic check` 无漂移；迁移头 `8f3d2a1c7b90`；确定性 eval `3 passed` | 否 |
| 真实 provider FAST eval | `passed` | `deepseek-flash`；2 steps；tokens `773 / 131`；latency `3471ms`；cost `$0.0003891`；Prompt `agent_system@1.0.0+agent_turn@1.1.0` | 否 |
| 完整 G4A 模型矩阵 | `open` | FAST 已通过；DEFAULT、REASONING、异常边界和发布成本门槛仍待验证 | 是 |
| 首个用户可见切片 `DR-07` | `approved` | `docs/decision-register.md` v0.8；方案 A | 否 |
| 前端工程与账号路径 | 已完成 | `web/`；注册、登录、找回/重置密码、空工作台和响应式导航 | 否 |
| 历史分页 | 已完成 | `web/src/pages/HistoryPage.tsx`；`{items, next_cursor}`，每页 10 条 | 否 |
| 浏览器 E2E | `passed` | 账号与简历桌面/移动项目 `4 passed`；macOS 13 不支持的 WebKit 留待兼容 CI | 否 |
| 简历纵向切片 | `passed` | 上传、PDF/DOCX 校验、异步处理、10 道题、失败重试、原始文件删除和 `source_deleted` 状态通过 | 否 |
| 全量质量门禁 | `passed` | 前端 typecheck、Vitest `7 files / 21 tests`、lint、build；后端 ruff、格式、mypy（78 files）、`107 passed` 集成测试和 `alembic check` | 否 |

简历切片已关闭，不再受审批或质量门禁阻塞。完整 G4A 模型矩阵与后续业务切片并行推进，但不能把 FAST 单档通过写成 G4A 已关闭。

## 2. 执行顺序

```mermaid
flowchart TD
    S0["工程骨架与质量基线：已完成"] --> N0["账号与工作台切片：验收通过"]
    N0 --> N1["模型档位与 LLM Client：已完成"]
    N1 --> N2["Prompt 加载与变量校验：已完成"]
    N2 --> N3["Tool 基类、截断与错误回灌：已完成"]
    N3 --> N4["Tool Registry 与不可信内容入口：已完成"]
    N4 --> N5["Agent Loop 三重封顶与嵌套限制：已完成"]
    N5 --> N6["确定性 Agent 行为 eval：已完成"]
    N6 --> N7["真实 provider FAST eval：已通过"]
    N7 --> N8["DR-07：已批准"]
    N8 --> N9["web/ 账号、工作台与历史分页：已实现"]
    N9 --> N10["Playwright E2E、质量门禁与切片验收：已完成"]
    N10 --> N11["简历纵向切片：验收通过"]
    N11 --> N12["当前：检索问答切片"]
    N12 --> N13["模拟面试与报告切片"]
    N13 --> N14["完整 G4A 模型矩阵与发布评审"]
```

原则：

- 先建立可运行底座，再实现业务页面和 Agent 行为。
- 数据库迁移必须覆盖已接受 ADR 的数据约束，不用临时内存状态替代。
- 每个骨架项同时交付测试或可重复验证命令，不以“文件已创建”为完成。
- 核心基座完成前，不并行堆叠多个业务切片。

## 3. 工程骨架交付清单（已完成）

工程骨架已按下列范围落地，并通过迁移循环、静态检查、单元/集成测试和首次 eval 验证。本节保留为后续改动的影响检查清单。

### 3.1 Python 工程与配置

| 工作 | 交付物 | 完成判据 |
| --- | --- | --- |
| 初始化 `uv` 工程 | `pyproject.toml`、`uv.lock`、`.python-version` | 空环境执行 `uv sync` 可重复安装 |
| 固定运行依赖 | FastAPI、uvicorn、Pydantic Settings、SQLAlchemy、asyncpg、Redis、structlog、Argon2id | 依赖版本锁定且理由可追踪 |
| 固定开发依赖 | pytest、pytest-asyncio、respx、ruff、mypy、pre-commit | 本地命令可直接运行 |
| 配置入口 | `app/config.py`、`.env.example` | 缺失或非法配置启动时给出明确错误 |
| 环境样例 | 数据库、Redis、会话密钥、邮件和 LLM 配置 | `.env.example` 与配置模型字段一致 |

### 3.2 FastAPI 与服务基础

| 工作 | 交付物 | 完成判据 |
| --- | --- | --- |
| 应用工厂与入口 | `app/main.py` | uvicorn 可启动，装配逻辑不进入业务模块 |
| 健康检查 | `/health/live`、`/health/ready` | live 不依赖外部服务；ready 检查 PostgreSQL 和 Redis |
| 统一错误结构 | 错误模型和异常处理器 | 业务错误、校验错误和未知错误结构稳定 |
| 请求关联 | 请求 ID 中间件 | 响应、日志和后续任务可关联同一请求 |
| 生命周期 | 数据库、Redis 客户端启停 | 启动失败可定位，关闭时不泄漏连接 |

### 3.3 数据与异步任务

| 工作 | 交付物 | 完成判据 |
| --- | --- | --- |
| SQLAlchemy async 基座 | engine、session、事务边界 | 连接池配置明确，测试可注入会话 |
| Alembic | `alembic.ini`、env 和初始迁移 | 空库可升级到 `head` |
| 核心表首版 | 账号、会话、简历、问答、面试、轮次、报告、错题和审计表 | 约束、索引和保留字段与技术基线一致 |
| SSE 持久事件 | `qa_requests.last_event_seq`、`qa_stream_events` | `UNIQUE (qa_request_id, seq)` 和重连查询可验证 |
| 任务租约 | `async_jobs.lease_owner`、`fencing_token`、`lease_until` | `FOR UPDATE SKIP LOCKED` 领取和条件写入有测试 |
| 本地依赖 | PostgreSQL、Redis 编排或等价启动说明 | 新环境按文档可启动并完成迁移 |

### 3.4 可观测性与安全入口

| 工作 | 交付物 | 完成判据 |
| --- | --- | --- |
| 结构化日志 | structlog JSON 行输出 | 不使用 `print` 或裸 `logging` |
| 日志脱敏 | token、邮箱、手机号和身份证号过滤器 | 敏感样例不会原样进入日志 |
| LLM trace 骨架 | 模型、Prompt 版本、token、延迟、工具调用和请求 ID | 每次调用可通过统一入口记录 |
| 不可信内容入口 | `<untrusted>` 包裹工具 | 网页、上传文件和第三方响应统一处理 |
| 写操作保护 | `dry_run=True` 默认值 | 外部副作用工具无默认放行路径 |

### 3.5 测试、评测与质量门禁

| 工作 | 交付物 | 完成判据 |
| --- | --- | --- |
| pytest 基础 | `tests/`、fixture、事务回滚 | 测试默认不连接生产数据 |
| 外部依赖模拟 | respx 和数据库测试夹具 | HTTP 与数据库失败路径可稳定复现 |
| 评测入口 | `evals/run.py`、首批用例 | 可运行并保存首次基线 |
| 静态检查 | ruff、mypy、pre-commit | `ruff check`、`ruff format --check`、`mypy app` 通过 |
| CI 门禁 | 单测、lint、类型检查和迁移检查 | 合并前可重复执行，不依赖人工本机状态 |

## 4. 上一阶段退出条件（已满足）

“工程骨架与质量基线”完成需要同时满足：

- `uv sync` 在干净环境成功，锁文件与 `pyproject.toml` 一致。
- API 可启动，`/health/live` 与 `/health/ready` 返回符合契约的结果。
- 空 PostgreSQL 可从零迁移到最新版本，迁移方向和关键约束经过测试。
- PostgreSQL、Redis、SSE 事件和任务租约字段能在本地验证。
- 请求 ID、结构化日志和 LLM trace 骨架可关联一次请求或任务。
- `ruff check`、`ruff format --check`、`mypy app` 和 `pytest` 全部通过。
- 至少一条 eval 用例可运行并记录基线。
- `.env.example`、配置模型、迁移和启动文档保持一致。

验证证据：

- `ruff check .`、`ruff format --check .` 和 `mypy app tests evals migrations` 通过。
- 默认测试可运行；`RUN_INTEGRATION=1 uv run pytest -q` 当前为 `107 passed`。
- 空库迁移、降级、再次升级及 `alembic check` 通过。
- 首次 eval 已通过并写入 `evals/baseline.json`；当前确定性 eval 为 `3 passed`。
- 真实服务可启动，健康检查、请求 ID 和服务端时间响应头可验证。

## 5. 核心基座与已验收切片

核心基座共享能力已经落地：

1. LLM Client：超时、有限重试、token 统计、trace、费用记录和日志脱敏。
2. Prompt 加载：Markdown、版本标识、变更说明和变量校验。
3. Tool Registry：Pydantic schema、单一注册、截断和结构化错误回灌；完整参数 Schema 已进入每轮 Prompt。
4. Agent Loop：`max_steps`、`max_tokens`、`timeout` 三重封顶及嵌套限制。
5. 安全基线：`<untrusted>` 包裹、写入工具 `dry_run=True` 和私有大结果文件权限。

核心基座关闭前还需（已提供入口）：

1. 配置真实 `LLM_API_KEY`、供应商和至少一组可用模型名。
2. 运行 `uv run python -m evals.provider_behavior --tier FAST`，记录工具选择、结构化输出、终止、延迟、token 和费用；本轮已完成。
3. 将真实评测结果与确定性基线分开记录，不以 mock 结果代替模型验收。
4. 评估首次真实调用成本与超时；FAST 已通过，剩余档位与异常边界再形成完整 G4A 结论。

异步 Worker 已随简历切片落地，提供任务租约、fencing、重试和简历状态链；生产对象存储适配仍待发布前完成。

随后交付“账号 -> 工作台 -> 空状态”，现已实现：

- 注册、登录、退出、当前会话和邮件找回密码。
- 服务端可撤销会话、Cookie 属性和跨设备会话。
- 工作台摘要、空状态和历史分页入口。
- 所有权校验、未登录和越权错误。
- 单元、集成、安全、接口契约和 eval 门禁。
- 同一切片建立 `web/`、页面路由与 API 集成；登录使用 `interview_session`（`HttpOnly`），CSRF 使用可读 `interview_csrf` 与 `X-CSRF-Token`，数据库 `auth_sessions.csrf_token_hash` 只保存 verifier 哈希。
- 历史接口统一返回 `{items, next_cursor}`；前端每次请求 10 条并支持继续加载。

账号切片退出条件（已全部满足）：

- 注册只返回中性受理结果，登录是唯一会话签发入口。
- 重置密码成功后旧会话全部失效。
- 未登录返回稳定认证错误，用户 A 无法读取用户 B 的资源。
- 质量命令、迁移和切片测试全部通过。
- 公开实现只依赖已批准需求或已接受 ADR。

## 6. 简历切片验收与后续顺序

简历切片退出条件（已全部满足）：

- PDF/DOCX、10 MB、10 页、空文本和不支持格式均有确定性结果。
- 结构化分析、未验证信息、10 题覆盖计划和隐藏评分材料通过 Schema 与业务测试。
- 异步处理、失败重试、原始文件删除和 `source_deleted` 证据摘要通过接口、Worker 与 E2E。
- 前端在桌面和移动视口完成上传、处理中、结果和删除闭环。

后续切片顺序：

| 顺序 | 切片 | 进入条件 | 核心退出条件 |
| --- | --- | --- | --- |
| 1 | 账号与工作台 | 当前切片 E2E 和质量门禁通过（已完成） | 认证、隔离、会话、历史分页和响应式导航可验证（已满足） |
| 2 | 简历闭环（已完成） | 异步 Worker 和对象存储已就绪 | 文件限制、分析失败、出题和删除通过 |
| 3 | 检索问答（下一项） | LLM、检索工具、知识源 allowlist 和持久 SSE 已就绪 | 证据、重连、降级和版本冻结通过 |
| 4 | 模拟面试 | 任务、评分和状态机已就绪 | 截止、幂等、恢复和解锁规则通过 |
| 5 | 报告与复习 | 面试终态数据稳定 | 追问树、错题、薄弱点和缺口报告通过 |
| 6 | 上线质量 | P0 切片全部完成 | 安全、性能、评测和发布门禁通过 |

## 7. 实现约束与风险

| 约束或风险 | 实现要求 | 阻断条件 |
| --- | --- | --- |
| ADR-0003 服务端截止 | 使用 PostgreSQL 时间，`server_now < deadline_at` 才有效 | 使用客户端时间或应用实例时间 |
| ADR-0006 SSE 重连 | 事件持久化，游标来自 PostgreSQL | 重连重复调用模型、扣预算或丢失终态 |
| ADR-0007 任务租约 | 领取递增 fencing token，写入校验 owner/token | 旧 Worker 可覆盖新租约 |
| ADR-0008 受保护反馈 | 终态且评分离开 `scoring` 后解锁 | 提交接口提前返回分数或评分无限卡住 |
| 骨架只建不使用 | 健康检查、迁移和 trace 先通过测试 | 业务模块直接绕过基座 |
| 依赖边界漂移 | 保持 `api -> agent -> tools -> llm` | 反向 import 或跨层直调 |
| 生产对象存储未接入 | 发布前替换本地私有存储适配器并验证访问控制 | 使用公开链接或无租约清理 |
| 质量门禁后补 | 骨架阶段即建立 lint、类型和测试 | 先堆业务代码再补门禁 |

## 8. 完成定义

“下一步工作完成”需要同时满足：

- 工程骨架和核心基座在干净环境可启动、迁移、测试和评测。
- ADR-0003、ADR-0006、ADR-0007、ADR-0008 的实现约束有对应测试。
- `DR-01` 至 `DR-06` 在需求、接口、数据、状态和安全测试中一致。
- 账号与简历纵向切片通过接口、权限、安全、质量和文档门禁。
- 开发全流程的当前阶段、阻塞和下一步与仓库实际状态一致。

## 9. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-17 | 建立从决策审批、ADR 评审、工程骨架到首个纵向切片的执行计划 |
| v0.2 | 2026-10-17 | 记录 ADR-0001、ADR-0002、ADR-0004、ADR-0005 已接受，剩余四项技术评审 |
| v0.3 | 2026-10-17 | 记录 DR-01、DR-02 已批准并完成文档同步；剩余审批收敛为 DR-03 至 DR-06 |
| v0.4 | 2026-10-17 | 记录 DR-03 至 DR-06 已批准；需求审批全部关闭 |
| v0.5 | 2026-10-17 | 记录 ADR-0001 至 ADR-0008 全部接受；当前阶段切换为工程骨架与质量基线，补充 `uv`、FastAPI、迁移、SSE、任务租约、日志、测试和 eval 交付清单 |
| v0.6 | 2026-10-17 | 工程骨架与质量基线通过；记录静态检查、测试、迁移和 eval 证据，当前阶段切换为核心能力基座 |
| v0.7 | 2026-10-17 | 记录 LLM/Prompt/Tool/Loop 与确定性行为评测完成；真实供应商模型评测待凭据，明确前端随首切片建立及首个切片审批门 |
| v0.8 | 2026-10-17 | 补齐工具参数 Schema 注入与预算估算缺口；同步基座验收证据，真实供应商模型评测和首切片审批仍是后续阻塞 |
| v0.9 | 2026-10-17 | 登记 `DR-07` 为首个用户可见切片审批项；同步待审批状态、前端工程阻塞和推荐实现边界 |
| v1.0 | 2026-10-17 | 增加阶段与审批文档契约测试；记录完整质量门禁 `67 passed, 10 skipped` |
| v1.1 | 2026-10-17 | 复跑并记录 `77 passed` 集成门禁、无漂移迁移检查和 `2/2` 确定性 eval；真实模型证据和 `DR-07` 审批仍是外部门禁 |
| v1.2 | 2026-10-17 | `DR-07` 方案 A 已批准；`web/`、账号与历史切片已实现；真实 provider FAST eval 已通过；当前进入 E2E、质量门禁和验收收尾，完整 G4A 模型矩阵仍未关闭 |
| v1.3 | 2026-10-17 | 首个用户可见纵向切片验收通过：双视口 E2E `2 passed`、前端质量门禁、后端 `88 passed`、迁移检查通过；下一阶段为简历闭环，完整 G4A 模型矩阵仍未关闭 |
| v1.4 | 2026-10-17 | 同步技术设计 v0.10 与开发流程 v2.6；更新文档契约证据，保留异步 Worker、对象存储、简历闭环和完整 G4A 矩阵为后续工作 |
| v1.5 | 2026-10-17 | 简历纵向切片验收通过：双视口 E2E `4 passed`、前端 `7 files / 21 tests`、后端 `107 passed`、mypy 78 files、确定性 eval `3 passed`、迁移头 `8f3d2a1c7b90`；下一阶段切换为检索问答 |
