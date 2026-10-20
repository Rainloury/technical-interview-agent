# 文档导航

当前阶段：**发布候选（release candidate）；P0 业务切片、质量门禁、隐私与可观测门禁、G4A 行为矩阵、本地恢复/回滚和五类告警送达演练已通过；生产环境复核、发布 SHA 冻结与发布批准待完成**。`DR-07` 已批准，`web/` 已实现账号、工作台、历史、响应式导航、简历闭环、问答、模拟面试、报告、复习中心和数据删除。后端已提供 `interview_session`（`HttpOnly`）、`interview_csrf`、`X-CSRF-Token`、`{items, next_cursor}`、owner-scoped 业务与隐私 API、持久 SSE 重放、数据库权威截止和数据保留清理，并在 `auth_sessions.csrf_token_hash` 只保存 CSRF 哈希。

上线质量门禁当前覆盖 Chromium 桌面与移动 E2E `14 passed`、隐私专项 `2 passed`、前端 Vitest `12 files / 37 tests`、默认测试 `166 passed, 51 skipped`、后端集成测试 `206 passed`、Mypy `112 files`、确定性 eval `7/7` 和迁移头 `7e2b4c6d8f10`。GitHub Actions Ubuntu 24.04 托管 runner 的 Playwright WebKit Desktop Safari + iPhone 13 实跑 `14 passed`（2.4 min）；本地 Ubuntu WebKit 同套件 `14 passed`。真实 provider 三档单轮 eval 已通过；G4A 行为矩阵已通过，110 条矩阵为 `110/110`（完整运行 `108/110` + 定向复验 `2/2`）；10 场整场成本 P95 为 ¥0.83908，且每场均覆盖追问，检索为数据库内词法排序、外部费用 ¥0。

| 文档 | 用途 | 状态 |
| --- | --- | --- |
| [开发全流程](./development-flow.md) | 从需求收集到 MVP 落地、上线和迭代的入口、阶段门禁与交付物 | v3.7 当前流程基线 |
| [需求文档](./requirements.md) | 产品目标、范围、功能需求、状态模型、验收场景和已确认决策 | v1.5 需求基线 |
| [产品方案设计](./product-design.md) | 信息架构、页面方案、交互规则、数据隐私和 MVP 交付切片 | v1.5 已确认 |
| [决策登记与审批](./decision-register.md) | 需求审批规则、已确认决策和首个切片审批 | v0.8 `DR-07` 已批准 |
| [技术设计](./technical-design.md) | 总体架构、运行链路、权限、预算、异步任务和实现顺序 | v0.21 当前基线 |
| [数据模型](./data-model.md) | 核心表、关系、约束、索引、迁移和保留策略 | v0.6 技术基线 |
| [状态机与事务](./state-machine.md) | 简历、面试、轮次、追问链、删除的迁移与并发规则 | v0.5 技术基线 |
| [接口契约](./api-contract.md) | HTTP API、SSE、错误码、幂等和权限测试矩阵 | v0.7 账号与历史契约已落地 |
| [威胁模型](./threat-model.md) | 信任边界、主要威胁、控制措施和上线阻断条件 | v0.6 首切片安全控制已验收 |
| [架构决策记录](./adr/README.md) | ADR-0001 至 ADR-0008 及后续技术决策 | 8 项已接受 |
| [技术方案评审清单](./technical-review-checklist.md) | 架构门禁、已批准需求、基座验收证据和后续条件 | v3.3 发布候选门禁已通过 |
| [发布与回滚运行手册](./release-runbook.md) | 生产配置、迁移备份恢复、灰度观察、Go/No-Go 和回滚流程 | v1.5 发布候选；存在上线阻断项 |
| [下一步执行计划](./next-steps.md) | 核心基座和业务纵向切片的执行顺序与退出条件 | v3.9 生产复核待关闭 |
| [项目规则](../AGENTS.md) | 技术栈、分层边界、智能体开发约束、安全底线和 DoD | 生效中 |

## 快速定位

| 我想了解 | 首先查看 |
| --- | --- |
| 项目现在处于什么阶段 | [当前状态](./development-flow.md#当前状态) |
| 从需求到上线的完整顺序 | [流程总览](./development-flow.md#流程总览) |
| 每个阶段做什么、产出什么 | [阶段说明](./development-flow.md#阶段说明) |
| 什么时候可以进入下一阶段 | [阶段门禁](./development-flow.md#阶段门禁) |
| MVP 如何拆成可交付切片 | [开发切片](./development-flow.md#mvp-开发切片) |
| 每个功能怎样算完成 | [完成定义](./development-flow.md#完成定义) |
| 上线前检查什么 | [上线前检查](./development-flow.md#上线前检查) |
| 发布、迁移、观测和回滚怎么执行 | [发布与回滚运行手册](./release-runbook.md) |
| 已确认的产品规则 | [需求基线第 14 节](./requirements.md#14-已确认决策基线) |
| 哪些需求需要我审批 | [决策登记](./decision-register.md) |
| 已接受的技术约束是什么 | [技术设计](./technical-design.md) 和 [ADR 索引](./adr/README.md) |
| 下一步具体做什么、何时算完成 | [下一步执行计划](./next-steps.md) |
| 前端工程与当前页面 | [技术设计的认证与前端实现](./technical-design.md) |
| 数据怎么存、状态怎么迁移 | [数据模型](./data-model.md) 和[状态机](./state-machine.md) |
| API 和流式事件怎么约定 | [接口契约](./api-contract.md) |
| 有哪些架构决策 | [ADR 索引](./adr/README.md) |
| 页面和交互怎么设计 | [产品方案设计](./product-design.md) |

## 建议阅读顺序

1. 先读[开发全流程](./development-flow.md)，明确当前阶段、下一步和门禁。
2. 读[决策登记](./decision-register.md)，确认 `DR-01` 至 `DR-07` 均已批准。
3. 读[需求文档](./requirements.md)第 14 节，确认已冻结的 MVP 规则。
4. 读[产品方案设计](./product-design.md)第 15 节，查看已确认决策和已关闭交互问题。
5. 读[技术设计](./technical-design.md)及其数据、状态和接口文档，核对 ADR-0001 至 ADR-0008 的实现约束。
6. 读[下一步执行计划](./next-steps.md)，按发布候选检查清单完成批准与上线。
7. 开发前读[项目规则](../AGENTS.md)，确认分层、循环、工具、安全和测试约束。
8. 发布前确认回滚、备份、监控、告警和上一版本恢复路径。

## 文档维护规则

- 需求范围或验收规则变化时，先更新需求文档并提升版本，再同步流程文档。
- 产品交互决策变化时，先更新需求或决策登记，再同步产品方案，不直接改写已冻结契约。
- 需求、验收或用户可见行为需要审批时，先更新决策登记；未经批准不得写入需求基线。
- 架构或技术约束变化时，在 `docs/adr/` 新增 ADR，并在开发全流程相关阶段引用。
- 每个开发切片的验收结果记录到 PR 或测试报告中，不把临时进度写进产品文档。
