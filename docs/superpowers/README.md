# Superpowers 方案目录

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 文档状态 | 当前方案与计划入口 |
| 更新日期 | 2026-10-23 |
| 适用目录 | `docs/superpowers/` |

> 本目录统一承载可执行方案：`specs/` 记录设计规格，`plans/` 记录实施计划。
> 需求、产品基线、ADR、技术契约和发布手册保持原位，并由[方案总览](../solution-map.md)
> 统一索引。实现是否落地仍以代码、测试、迁移和合并记录为准。

## 1. 目录职责

| 路径 | 用途 | 权威边界 |
| --- | --- | --- |
| [方案总览](../solution-map.md) | 跨目录导航、当前事实和权威顺序 | 跨方案总览，不替代需求或 ADR |
| `specs/` | 单个切片的方案、边界、数据流、错误处理和验收设计 | 方案规格，不替代长期 ADR |
| `plans/` | 按任务拆分的实现步骤、验证命令和交付记录 | 执行计划；历史复选框不表示当前待办 |
| `../requirements.md`、`../product-design.md` | 产品目标、用户可见行为和验收基线 | 原位维护，不属于实施计划 |
| `../adr/` | 长期架构选择及其后果 | 原位维护，不复制到本目录 |
| `../release-runbook.md` | 生产发布、回滚和 Go/No-Go 操作 | 原位维护，不替方案规格 |

## 2. 方案索引

| 方案 | 规格 | 计划 | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| 私有内部资料混合 RAG | [user-rag-design.md](./specs/user-rag-design.md) | [user-rag.md](./plans/user-rag.md) | 已实现 | `DR-08`、ADR-0009 |
| 共享资料与管理员权限 | [shared-documents-design.md](./specs/shared-documents-design.md) | [shared-documents.md](./plans/shared-documents.md) | 已实现并合并 | `DR-09`、ADR-0010、PR #6 |
| Android 发布接入 | [android-release-design.md](./specs/android-release-design.md) | [android-release.md](./plans/android-release.md) | 已实现，含设计修订 | 实际采用 Capacitor 8；发布文档为 `../android-release.md` |
| iOS 发布接入 | [ios-release-design.md](./specs/ios-release-design.md) | [ios-release.md](./plans/ios-release.md) | 工程与预检完成 | 签名、TestFlight 和商店提交待完成 |

实现状态和发布阻塞优先看[方案总览](../solution-map.md)；规格与计划的详细状态以本目录为准。

## 3. 文件命名

- 使用稳定的主题名称，例如 `user-rag-design.md`、`android-release.md`。
- 文件名不写日期；日期和版本写在正文元数据与版本记录中。
- 新规格使用 `<topic>-design.md`，对应计划使用 `<topic>.md`。
- 同一主题的规格和计划使用相同主题词，便于通过文件名配对。
- 历史日期只保留在正文中；重命名文件时同步更新所有相对链接和契约测试。

## 4. 状态定义

| 状态 | 含义 | 是否表示当前待办 |
| --- | --- | --- |
| `draft` | 设计仍在整理，尚未提交评审 | 是 |
| `awaiting_approval` | 方案已完成，等待明确批准 | 是 |
| `accepted` | 已批准；计划可进入执行 | 否；看计划任务状态 |
| `implemented` | 代码、测试和必要迁移已落地 | 否；看发布或遗留项 |
| `superseded` | 被后续规格或 ADR 替代 | 否；以替代项为准 |
| `blocked` | 受外部账号、凭据或生产条件阻塞 | 是；需负责人处理 |

方案状态与发布状态分开记录。一个方案可以 `implemented`，但移动端商店提交或生产发布仍是 `blocked`。

## 5. 工作流

1. 先读[方案总览](../solution-map.md)和本目录索引，确认已有方案和冲突。
2. 新需求先在[决策登记](../decision-register.md)确认是否需要审批。
3. 架构级方案在 `specs/` 写规格，引用需求、ADR 和受影响契约。
4. 规格批准后，在 `plans/` 写计划；计划中的每个任务必须有可执行验证。
5. 实现完成后，更新规格状态、计划状态和[方案总览](../solution-map.md)，不把临时进度写进需求基线。
6. 设计选择改变时新增 ADR 或在本目录规格中写修订记录，并同步所有链接。

发布操作不在本目录重复维护：iOS 的构建、签名和归档步骤见 [iOS 发布手册](../ios-release.md)，
Android 的构建和商店操作见 [Android 发布手册](../android-release.md)。

## 6. 维护规则

- 当前方案以本目录索引和[方案总览](../solution-map.md)为准；历史规格和计划保留作审计证据。
- 新增规格或计划时，同时更新本文件第 2 节、[方案总览](../solution-map.md)第 5 节和对应测试。
- 文件名、状态和目录变化时，必须运行文档契约测试和 Markdown 链接检查。
- 不在本目录复制需求正文、ADR 正文或发布手册；只链接并说明它们和本方案的关系。
- 不把英文版作为新方案的必需交付；中文方案是默认版本。

## 7. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-10-23 | 建立 Superpowers 方案目录入口、四组方案索引、命名规则、状态定义和维护流程 |
