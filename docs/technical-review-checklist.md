# 技术方案评审清单

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v2.1 |
| 文档状态 | 发布候选；隐私与可观测门禁已通过，G4A 行为矩阵已通过，技术、生产依赖、浏览器兼容与 Worker 入口门禁通过，待发布批准 |
| 更新日期 | 2026-10-18 |

> 本清单跟踪架构决策、工程骨架和核心能力基座的验收证据。需求和用户可见行为的批准记录在[决策登记](./decision-register.md)。

## 1. 架构门禁

| 检查项 | 状态 | 证据 |
| --- | --- | --- |
| 分层符合 `AGENTS.md` | `accepted` | `docs/adr/0001-layering.md`、`docs/technical-design.md` v0.20 |
| 模块依赖方向明确 | `accepted` | `docs/adr/0001-layering.md`、`docs/technical-design.md` 依赖矩阵 |
| 业务状态以 PostgreSQL 为事实来源 | `accepted` | `docs/adr/0002-database-as-source-of-truth.md` |
| 面试截止由服务端控制 | `accepted` | `docs/adr/0003-server-authoritative-deadline.md` |
| 所有 LLM 调用统一 trace | `accepted` | `docs/adr/0004-llm-client-and-trace.md` |
| 工具单一注册与截断 | `accepted` | `docs/adr/0005-tool-registry-and-untrusted-content.md` |
| 问答流式协议可重连 | `accepted` | `docs/adr/0006-sse-contract.md` |
| 异步任务方案可实施 | `accepted` | `docs/adr/0007-database-job-queue.md` |
| 受保护反馈在服务端裁剪 | `accepted` | `docs/adr/0008-protected-feedback.md` |
| 数据表、关系、索引和迁移入口明确 | `accepted` | `docs/data-model.md` v0.7 |
| 状态机可闭合 | `accepted` | `docs/state-machine.md` v0.5 |
| 接口和错误语义明确 | `accepted` | `docs/api-contract.md` v0.8 |
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
| 默认与集成质量门禁 | `passed` | 默认测试 `147 passed, 51 skipped`；`RUN_INTEGRATION=1 pytest` 为 `198 passed`；集成结果包含文档契约、provider 矩阵、整场成本、DirectMail 和 OSS 适配器契约测试 |
| 迁移一致性 | `passed` | `alembic check` 无漂移；迁移头为 `3b7e1c9d4a20` |
| 确定性行为评测 | `passed` | `pytest -q evals` 与 eval CLI 为 `7/7`，通过率 1.0 |
| 前端工程与账号路径 | `passed` | `web/`；注册、登录、退出、找回/重置密码、空工作台和响应式导航 |
| 会话与 CSRF | `passed` | `interview_session` 为 `HttpOnly`；`interview_csrf` 配合 `X-CSRF-Token`；`auth_sessions.csrf_token_hash` 只保存哈希 |
| 历史分页 | `passed` | 历史接口返回 `{items, next_cursor}`；前端每页 10 条并支持继续加载 |
| 简历纵向切片 | `passed` | 上传、PDF/DOCX 校验、异步处理、10 题、失败重试、删除原始简历和 `source_deleted` 证据摘要 |
| 检索问答切片 | `passed` | owner 隔离、幂等、任意 URL 拒绝、allowlist/最新发布版本、证据冻结、引用校验、持久 SSE 游标重放、终态互斥和前端历史重开 |
| 浏览器 E2E | `passed` | Chromium 桌面与移动 `14 passed`，隐私专项 `2 passed`；GitHub Actions Ubuntu 24.04 托管 runner 的 Playwright WebKit Desktop Safari + iPhone 13 `14 passed`（2.4 min）；本地 Ubuntu WebKit 同套件 `14 passed` |
| DirectMail SMTP | `passed` | `smtpdm.aliyun.com:465` + SSL 的 TLS 与 SMTP 登录通过；测试邮件已由 SMTP 服务器接受且无拒收收件人；收件箱到达待人工确认 |
| OSS 私有对象存储 | `passed` | 真实私有桶 PUT/GET/DELETE、简历业务上传内容一致性和源文件删除后不可读均已验证 |
| 全量质量门禁 | `passed` | 前端 typecheck、Vitest `12 files / 37 tests`、ESLint、build；后端 ruff、格式、mypy（109 files）、默认测试 `147 passed, 51 skipped`、`RUN_INTEGRATION=1 pytest`（`198 passed`）和 `alembic check` |
| 真实 provider 三档单轮 eval | `passed` | 真实 provider 三档单轮 eval 已通过：FAST `deepseek-flash`；DEFAULT/REASONING `deepseek-v4-pro`；均 2 steps、正确调用 `add` 并返回 `42` |
| 完整 G4A 模型矩阵 | `passed` | 三档单轮与异常边界测试已通过；110 条行为矩阵为完整运行 `108/110` 加定向复验 `2/2`；10 场整场成本 P95 ¥0.83908，每场覆盖追问，检索外部费用 ¥0 |
| 部署资产 | `passed` | 非 root 生产镜像、migrate/API/Worker Compose、只读根文件系统、API/Worker 健康检查和 CI 镜像构建门禁 |
| 密码重置异步投递 | `passed` | 请求事务保存加密投递密文和持久任务；Worker 有限重试、死信和终态密文清理通过 |

## 6. 下一步

1. 全部业务切片已通过浏览器、安全、权限、质量和迁移门禁。
2. 生产 DirectMail 实际发送、OSS 私有桶上传/读取/删除和 GitHub Actions WebKit 均通过。
3. 完成发布批准、环境变量与密钥复核、数据库迁移、备份恢复和回滚方案确认。
4. 执行灰度上线，观察任务成功率、首段延迟、评分失败率、检索命中率、成本与删除任务。
5. 按[下一步执行计划](./next-steps.md)和[开发全流程](./development-flow.md)完成上线与复盘。

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
| v1.7 | 2026-10-18 | 检索问答切片验收通过：owner 隔离、幂等、URL 拒绝、allowlist/版本冻结、证据引用校验、持久 SSE 重放和公开字段边界通过；双视口 E2E `8 passed`、前端 `9 files / 32 tests`、后端 `116 passed`、mypy 84 files、确定性 eval `3/3`、迁移头 `4b6e9d2c1a70` |
| v1.8 | 2026-10-18 | 模拟面试与报告切片验收通过：数据库硬截止、操作幂等、中性 202 响应、评分、两层追问、分支结束原因、评分失败收口和受保护反馈通过；双视口 E2E `12 passed`、前端 `11 files / 36 tests`、后端 `126 passed`、mypy 58 files、迁移头 `7d1a3e5b9c42` |
| v1.9 | 2026-10-18 | 上线质量隐私与可观测门禁通过：账号数据删除、对象与业务主体清理、30/90/365 天保留清理、审计最小化、ops metrics、确定性 eval `7/7` 和双视口隐私 E2E `2 passed`；双视口 E2E `14 passed`、前端 `12 files / 37 tests`、后端 `140 passed`、mypy 71 files、迁移头 `3b7e1c9d4a20`；110 条真实行为矩阵 `82/110`，完整 G4A 模型矩阵仍未关闭 |
| v2.0 | 2026-10-18 | 修正矩阵构念失真后，完整复跑 `108/110`（98.18%），两条共享契约定向复验 `2/2`，行为矩阵合计 `110/110` 并通过；完整 G4A 仅剩整场面试成本 P95 证据 |
| v2.1 | 2026-10-18 | 整场成本基准通过：10 场完整面试全部覆盖追问，模型与检索成本 P95 ¥0.83908；生产 SMTP 失败改为可诊断上抛；发布评审保留生产邮件、对象存储和 WebKit 兼容 CI 确认项 |
| v2.2 | 2026-10-18 | 生产依赖选定并落地适配器：DirectMail SMTP、阿里云 OSS 私有桶、GitHub Actions Ubuntu Playwright WebKit（Desktop Safari + iPhone 13）；本地质量门禁 `158 passed / 76 files`，待真实凭据和 CI 实跑验收 |
| v2.3 | 2026-10-18 | DirectMail 凭据验证通过：465/SSL TLS 握手与 SMTP 登录成功；587/StartTLS 本机超时；实际邮件投递仍待验证 |
| v2.4 | 2026-10-18 | DirectMail 实际发送通过：测试邮件发往 `no-reply@rainstone.top`，SMTP 服务器接受且无拒收收件人 |
| v2.5 | 2026-10-18 | 阿里云 OSS 真实私有桶验收通过：临时对象三步操作、简历上传内容一致性和删除源文件后对象不可读均通过 |
| v2.6 | 2026-10-18 | Ubuntu 24.04 Playwright WebKit 本地容器实跑通过：Desktop Safari + iPhone 13 共 `14 passed`；`webkit-e2e` 增加 `workflow_dispatch` 与失败报告产物，GitHub Actions 托管 runner 实跑待推送验收 |
| v2.7 | 2026-10-18 | GitHub Actions `ubuntu-latest` 托管 runner WebKit 实跑通过：Desktop Safari + iPhone 13 `14 passed`（2.4 min），quality job 全绿；修复 preview 构建 API 地址注入，并增加手动 grep、默认零重试和全局超时诊断 |
| v2.8 | 2026-10-18 | 阶段切换至发布候选：全部技术与生产依赖门禁通过；后续只剩发布批准、回滚/备份检查和灰度上线观测 |
| v2.9 | 2026-10-18 | 增加生产配置启动 fail-fast 与发布运行手册；默认测试更新为 `121 passed, 49 skipped`、mypy 103 files；生产 Worker、部署资产、密码重置异步投递、备份恢复和回滚演练仍为上线阻断项 |
| v3.0 | 2026-10-18 | 生产 Worker 命令与有界生命周期验收通过；默认测试更新为 `138 passed, 49 skipped`、mypy 104 files；部署编排、密码重置异步投递、备份恢复、回滚和告警仍为上线阻断项 |
| v3.1 | 2026-10-18 | 部署资产门禁通过：非 root 生产镜像、migrate/API/Worker Compose、Worker 心跳和 CI 镜像构建验证落地 |
| v3.2 | 2026-10-18 | 密码重置异步投递通过：加密密文、持久任务、重试、死信和密文清理；关闭同步 SMTP 阻断项 |
