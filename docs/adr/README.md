# 架构决策记录

本目录保存已评审的架构决策。ADR 记录“为什么这样做”、替代方案和后果，不复制需求正文。

## 决策索引

| 编号 | 决策 | 状态 | 影响范围 |
| --- | --- | --- | --- |
| [ADR-0001](./0001-layering.md) | 固定 `api -> agent -> tools -> llm` 依赖方向 | 已接受 | 全仓模块边界 |
| [ADR-0002](./0002-database-as-source-of-truth.md) | PostgreSQL 作为业务状态与幂等事实来源 | 已接受 | 数据、任务、恢复 |
| [ADR-0003](./0003-server-authoritative-deadline.md) | 服务端时间控制面试截止 | 已接受 | 面试状态、提交、恢复 |
| [ADR-0004](./0004-llm-client-and-trace.md) | 所有 LLM 调用统一经过可追踪 Client | 已接受 | LLM、日志、成本 |
| [ADR-0005](./0005-tool-registry-and-untrusted-content.md) | Tool Registry 单一注册并包裹不可信内容 | 已接受 | Agent、检索、安全 |
| [ADR-0006](./0006-sse-contract.md) | 问答使用可重连 SSE 事件流 | 已接受 | 问答接口、前端 |
| [ADR-0007](./0007-database-job-queue.md) | P0 使用 PostgreSQL 任务表而非新增消息队列 | 已接受 | 异步任务、部署 |
| [ADR-0008](./0008-protected-feedback.md) | 受保护反馈按整场终态解锁 | 已接受 | 面试、报告、DTO |
| [ADR-0009](./0009-hybrid-rag-for-private-documents.md) | 私有内部资料采用 pgvector、BM25 和 RRF 混合检索 | 已接受 | 数据、检索、Worker、前端、部署 |
| [ADR-0010](./0010-shared-documents-and-admin-role.md) | 共享资料采用独立资源与管理员角色 | 已接受 | 鉴权、数据、检索、Worker、前端、运维 |

当前 ADR-0001 至 ADR-0010 已全部接受。

## 状态

- `proposed`：技术方案提出，等待评审。
- `accepted`：评审通过，作为实现约束。
- `superseded`：被后续 ADR 替代。
- `rejected`：明确不采用。

需求范围、用户可见行为和验收规则仍需通过[决策登记](../decision-register.md)审批；ADR 只能固化技术实现选择。

## 模板

新增 ADR 时包含：背景、决策、替代方案、后果、影响文件、验证方式和审批人/日期。
