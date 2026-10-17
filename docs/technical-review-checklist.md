# 技术方案评审清单

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.6 |
| 文档状态 | 账号与简历纵向切片验收通过，准备进入检索问答切片 |
| 更新日期 | 2026-10-17 |

> 本清单跟踪架构决策、工程骨架和核心能力基座的验收证据。需求和用户可见行为的批准记录在[决策登记](./decision-register.md)。

## 1. 架构门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 分层符合 `AGENTS.md` | `accepted` | `docs/adr/0001-layering.md`、`docs/technical-design.md` v0.11 |
| 模块依赖方向明确 | `accepted` | `docs/adr/0001-layering.md`、`docs/technical-design.md` 依赖矩阵 |
| 业务状态以 PostgreSQL 为事实来源 | `accepted` | `docs/adr/0002-database-as-source-of-truth.md` |
| 面试截止由服务端控制 | `accepted` | `docs/adr/0003-server-authoritative-deadline.md` |
| 所有 LLM 调用统一 trace | `accepted` | `docs/adr/0004-llm-client-and-trace.md` |
| 工具单一注册与截断 | `accepted` | `docs/adr/0005-tool-registry-and-untrusted-content.md` |
| 问答流式协议可重连 | `accepted` | `docs/adr/0006-sse-contract.md` |
| 异步任务方案可实施 | `accepted` | `docs/adr/0007-database-job-queue.md` |
| 受保护反馈在服务端裁剪 | `accepted` | `docs/adr/0008-protected-feedback.md` |
| 数据表、关系、索引和迁移入口明确 | `accepted` | `docs/data-model.md` v0.6 |
| 状态机可闭合 | `accepted` | `docs/state-machine.md` v0.5 |
| 接口和错误语义明确 | `accepted` | `docs/api-contract.md` v0.7 |
| 安全威胁和控制明确 | `accepted` | `docs/threat-model.md` v0.6 |

## 2. 项目负责人审批结论

以下需求边界已由项目负责人批准并写入需求基线，不再作为待审批项：

| 编号 | 已批准问题 | 冻结方案 | 实现与验收 |
| --- | --- | --- | --- |
| `DR-03` | 面试中的流程反馈范围 | 仅中性流程、已提交轮次、完成数、剩余题数和时间 | AC-42、面试 DTO |
| `DR-04` | 结束追问与结束整场 | P0 仅结束当前追问；提前结束整场为 P1 独立操作 | AC-43、状态机 |
| `DR-05` | 删除简历后的证据展示 | 最长 200 字符脱敏摘要，标记 `source_deleted` | AC-44、删除任务 |
| `DR-06` | 审计摘要粒度与期限 | 仅最小白名单元数据，保留 365 天 | AC-45、审计清理 |
| `DR-07` | 首个用户可见切片与前端工程 | 方案 A：React + TypeScript + Vite；账号进入、工作台、历史分页、显式 CSRF 和浏览器测试同一切片 | `web/` 已建立；切片验收通过 |

`DR-01` 至 `DR-07` 均已由项目负责人批准并写入基线。ADR 评审结论只固化技术实现选择，不能替代需求变更控制。

`DR-07` 已按方案 A 批准，冻结首个用户可见切片的产品和工程边界；它不代表完整 G4A 模型矩阵通过，`G4A` 仍需独立证据。

## 3. 已评审问题与实现验证

以下问题已在 ADR 评审中逐项确认，后续在实现和测试中验证：

1. 分层和模块职责是否可维护。
2. 数据模型是否覆盖 30/90 天保留和删除补偿。
3. 面试状态机是否可闭合且不可回退。
4. 截止、评分和报告是否能在同一事务边界内保持一致。
5. SSE 断线重连是否会重复调用模型或重复计费。
6. Prompt 注入、答案泄露和跨用户访问是否有可测试控制。
7. LLM trace 字段是否足以定位成本、失败和回归。
8. 异步任务表是否能支撑 MVP 预期吞吐。
9. 是否明确哪些行为需要产品/需求审批。
10. 是否可以在不新增依赖的情况下建立骨架。

## 4. 工程骨架通过标准

进入工程骨架时已满足：

- ADR-0001 至 ADR-0008 均已接受，评审结论和实现约束可追踪。
- 数据模型的核心约束、索引和删除策略无未决实现分歧。
- 面试、简历、问答和报告状态机可闭合。
- 接口错误码、幂等、权限和受保护内容边界有测试映射。
- `DR-01` 至 `DR-06` 的批准规则已同步到需求、接口、数据、状态和安全测试。
- `DR-07` 已按方案 A 批准，`web/` 的账号、工作台、历史分页、CSRF 和 E2E 资产已建立。
- 公开实现只依赖已批准需求或已接受 ADR。

## 5. 核心基座验收状态

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| `uv` 工程、依赖锁定和 CI 质量命令 | `passed` | `pyproject.toml`、`uv.lock`、ruff 和 mypy 门禁 |
| FastAPI、配置、健康检查和统一错误入口 | `passed` | `app/main.py`、`app/config.py`、API 测试 |
| PostgreSQL 迁移和约束 | `passed` | 空库降级/升级往返与 `alembic check` |
| LLM 档位、供应商 Client、trace 和费用 | `passed` | `app/llm/` 及确定性测试 |
| Prompt 版本、变量和变更说明 | `passed` | `app/prompts/`、`tests/test_prompts.py` |
| 工具 Schema、注册、截断和错误回灌 | `passed` | `app/tools/`、`app/agent/registry.py`、`tests/test_registry.py` |
| Agent Loop 三重封顶和嵌套限制 | `passed` | `app/agent/loop.py`、`tests/test_agent_loop.py` |
| 完整工具参数 Schema 进入模型上下文 | `passed` | `agent_turn` v1.1.0、Agent Loop 回归测试 |
| 确定性 Agent 行为 eval | `passed` | `evals/run.py`、`evals/baseline.json` |
| 阶段与审批文档契约 | `passed` | `tests/test_decision_docs.py` 验证 `DR-07` 已批准、`web/` 资产和当前阶段证据 |
| 默认与集成质量门禁 | `passed` | `RUN_INTEGRATION=1 pytest` 为 `107 passed`；集成结果包含文档契约测试 |
| 迁移一致性 | `passed` | `alembic check` 无漂移；迁移头为 `8f3d2a1c7b90` |
| 确定性行为评测 | `passed` | `pytest -q evals` 为 `3 passed`，通过率 1.0 |
| 前端工程与账号路径 | `passed` | `web/`；注册、登录、退出、找回/重置密码、空工作台和响应式导航 |
| 会话与 CSRF | `passed` | `interview_session` 为 `HttpOnly`；`interview_csrf` 配合 `X-CSRF-Token`；`auth_sessions.csrf_token_hash` 只保存哈希 |
| 历史分页 | `passed` | 历史接口返回 `{items, next_cursor}`；前端每页 10 条并支持继续加载 |
| 简历纵向切片 | `passed` | 上传、PDF/DOCX 校验、异步处理、10 题、失败重试、删除原始简历和 `source_deleted` 证据摘要 |
| 浏览器 E2E | `passed` | Playwright 桌面与移动项目 `4 passed`；覆盖账号、工作台、历史及简历上传、处理、出题和删除。macOS 13 不支持本轮 Playwright WebKit 二进制，WebKit 留待兼容 CI |
| 全量质量门禁 | `passed` | 前端 typecheck、Vitest `7 files / 21 tests`、ESLint、build；后端 ruff、格式、mypy（78 files）、`RUN_INTEGRATION=1 pytest`（`107 passed`）和 `alembic check`。Vitest 曾出现一次偶发加载超时，单文件复跑和连续两次全量复跑均通过，作为测试稳定性风险保留 |
| 真实 provider FAST eval | `passed` | 真实 provider FAST eval 已通过：`deepseek-flash`；2 steps；tokens `773 / 131`；latency `3471ms`；cost `$0.0003891`；Prompt `agent_system@1.0.0+agent_turn@1.1.0` |
| 完整 G4A 模型矩阵 | `open` | FAST 已通过；DEFAULT、REASONING、异常边界和发布成本门槛仍未关闭 |

## 6. 下一步

1. 账号与简历纵向切片已通过浏览器、安全、权限、质量和迁移门禁。
2. 进入检索问答前，确认知识源 allowlist、检索预算、持久 SSE 事件和证据校验边界。
3. 检索问答覆盖有证据、证据不足、检索失败、任意 URL 拒绝、重连和知识源版本冻结。
4. 完整 G4A 模型矩阵继续作为发布前独立门禁：补齐 DEFAULT、REASONING、异常边界和发布成本门槛。
5. 按[下一步执行计划](./next-steps.md)和[开发全流程](./development-flow.md)推进后续切片。

## 7. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-17 | 建立架构门禁、审批项和进入骨架开发的条件 |
| v0.2 | 2026-10-17 | 下一步统一指向可执行计划和切片退出条件 |
| v0.3 | 2026-10-17 | 接受 ADR-0001、ADR-0002、ADR-0004、ADR-0005；修正架构图并补充验证门禁 |
| v0.4 | 2026-10-17 | 同步 DR-01、DR-02 批准；冻结账号、数据、状态、接口和威胁模型，收敛剩余审批与 ADR 评审 |
| v0.5 | 2026-10-17 | 同步 DR-03 至 DR-06 批准；冻结面试进度、结束追问、删除证据和最小审计，需求审批不再阻塞 |
| v0.6 | 2026-10-17 | 接受 ADR-0003、ADR-0006、ADR-0007、ADR-0008；全部架构门禁通过，下一步进入工程骨架与质量基线 |
| v0.7 | 2026-10-17 | 同步技术设计 v0.7、数据模型 v0.5、状态机 v0.5 和接口契约 v0.6 的评审证据版本 |
| v0.8 | 2026-10-17 | 同步工程骨架与核心基座实现证据；记录工具参数 Schema 注入修复、确定性评测通过和真实供应商评测待凭据 |
| v0.9 | 2026-10-17 | 新增 `DR-07` 待审批事项；同步首个用户可见切片、前端工程和 CSRF 门禁，基座模型验收仍未关闭 |
| v1.0 | 2026-10-17 | 增加阶段与审批文档契约测试；完整质量门禁更新为 `67 passed, 10 skipped` |
| v1.1 | 2026-10-17 | 复跑集成测试、确定性 eval 和沙箱外迁移检查；记录 `77 passed`、`2/2`、`alembic check` 通过及真实评测的凭据阻塞 |
| v1.2 | 2026-10-17 | `DR-07` 方案 A 已批准；`web/`、账号、工作台、历史分页和双 Cookie/CSRF 已实现；真实 provider FAST eval 已通过；当前进入首个用户可见纵向切片收尾与验收，完整 G4A 模型矩阵仍未关闭 |
| v1.3 | 2026-10-17 | 首个用户可见纵向切片验收通过：双视口 E2E、前端质量门禁、后端 `88 passed` 与迁移检查完成；下一阶段为简历闭环，完整 G4A 模型矩阵仍未关闭 |
| v1.4 | 2026-10-17 | 同步技术设计 v0.10；确认阶段文档契约、首切片质量门禁和简历闭环入口 |
| v1.5 | 2026-10-17 | 简历纵向切片验收通过：桌面与移动 E2E `4 passed`、前端 `7 files / 21 tests`、后端 `107 passed`、mypy 78 files、确定性 eval `3 passed`、迁移头 `8f3d2a1c7b90`；下一阶段为检索问答 |
| v1.6 | 2026-10-17 | 复核移动端 E2E 与剩余质量门禁；记录一次 Vitest 偶发加载超时及连续复跑通过结果，保留测试稳定性风险 |
