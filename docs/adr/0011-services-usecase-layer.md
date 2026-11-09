# ADR-0011：承认 `services` 用例编排层并固定依赖边界

| 项目 | 内容 |
| --- | --- |
| 状态 | `accepted` |
| 日期 | 2026-11-09 |
| 关联 | ADR-0001（`superseded`）、DR-09 |
| 影响 | `app/api/`、`app/services/`、`app/worker.py`、`app/cli.py`、分层静态检查 |

## 背景

ADR-0001 将用例编排固定在 `agent/` 内，并明确不新增独立 `services` 层。实际落地时，
账号、简历、问答、面试、私有资料、共享资料、隐私、工作台与运维指标等纵向切片的用例
编排全部位于 `app/services/`，`app/api/v1/`、`app/worker.py`、`app/cli.py` 均直接调用它们。
`tests/test_layering.py` 只检查 `agent/`、`tools/`、`llm/` 的反向依赖，没有覆盖 `services/`，
因此文档红线与代码现状长期漂移。代码评审无法依据一份与实现不符的依赖矩阵判断改动是否越界。

本项目存在两个彼此独立的执行入口：有界 `agent` 循环（plan / act / observe）与 HTTP / Worker
驱动的用例编排。`agent` 循环不参与账号和资料用例，把两者强行塞进同一层并不能减少耦合，
只会让 `agent/` 既承担循环控制又承担全部业务状态迁移。

## 决策

- 正式承认 `app/services/` 为用例编排层，与 `app/agent/` 平级。
- `app/api/` 依赖 `app/services/`；`app/worker.py`、`app/cli.py` 通过 services 暴露的用例接口
  执行任务，不复制业务状态规则。
- `app/services/` 允许依赖 `app.config`、`app.errors`、`app.logging`、`app.security`、
  `app.crypto`、`app.storage`、`app.resume_processing`、`app.db.*`、`app.schemas.*`、
  `app.*_contracts` 以及同层 `app.services._*.py` 公共模块。
- `app/services/` 禁止依赖 `app.api`、`app.agent`、`app.tools`、`app.llm`、`app.worker`。
- `app/agent/` 与 `app/services/` 互不 import；`api → agent → tools → llm` 仍是 agent 循环
  内部的依赖链，不再是全仓唯一的目录红线。
- 同层公共逻辑集中在 `app/services/_*.py`，导出公开函数；禁止跨 service import 下划线私有成员。
- `AGENTS.md` 第 3 节分层红线、本 ADR、`docs/technical-design.md` 依赖矩阵与
  `tests/test_layering.py` 必须同步；后者对 services 的允许/禁止清单做静态校验。

ADR-0001 标记为 `superseded`，其「反向 import 禁止」「LLM 不感知业务」「基础设施显式注入」
等结论继续有效，仅目录红线由本 ADR 取代。

## 替代方案

1. 把 `app/services/` 全部迁回 `app/agent/`：文档无需改，但会把上千行用例编排塞进循环层，
   且与 `app/agent/loop.py` 的有界循环职责混杂，改动面远大于收益。
2. 维持文档不变、把现状当技术债：成本最低，但红线持续失真，静态检查仍会漏掉越界依赖。
3. 允许 services 任意 import：改动最少，但会重新引入 `tools`/`llm`/`api` 的反向耦合。

## 后果

- 依赖矩阵与实现一致，新增 service 的越界 import 会在 CI 被拒绝。
- `app/agent/` 回归「有界循环」单一职责，`app/services/` 回归「用例编排」单一职责。
- `app/services/` 内部仍需继续收口重复逻辑与事务边界；本 ADR 不改变任何对外行为。
- 历史文档中「用例编排位于 agent 层」的表述由本 ADR 标注取代，版本记录保留原文以便追溯。

## 影响文件

- `AGENTS.md`
- `docs/adr/0001-layering.md`、`docs/adr/README.md`、`docs/adr/0011-services-usecase-layer.md`
- `docs/technical-design.md`、`docs/solution-map.md`
- `tests/test_layering.py`

## 验证

- `uv run pytest tests/test_layering.py -q`：services 允许/禁止依赖清单通过，并包含失败样例。
- `uv run pytest -q` 与 `uv run mypy app` 无回归。
- 新增 service 若 import `app.api`、`app.agent`、`app.tools`、`app.llm` 或 `app.worker`，
  分层测试失败。

## 审批

项目负责人于 2026-11-09 确认「按推荐方向执行」，采纳正式承认 services 层的方案。
