# 技术面试智能体状态机与事务

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.5 |
| 文档状态 | 技术方案已确认 |
| 更新日期 | 2026-10-17 |
| 需求依据 | `docs/requirements.md` v1.5 |

> 本文把需求中的状态文本落成迁移矩阵、事务边界和并发规则。`DR-02`、`DR-03` 已批准：内部评分字段与公开响应 DTO 分离，提交回答和进行中查询只返回中性进度。`DR-04` 已批准：P0 只结束当前追问链，提前结束整场保留到 P1。ADR-0003、ADR-0006、ADR-0007、ADR-0008 已成为实现约束。

## 1. 通用规则

- 每个状态迁移必须由服务层方法执行，不能由模型原始输出直接触发。
- 迁移前读取当前状态并校验期望旧状态；更新条件包含 `WHERE state = :expected`。
- 终态不可被普通请求回退。重试通过新任务、新尝试或明确的重置流程表达。
- 同一资源的状态迁移必须经过数据库事务和行锁或条件更新。
- `updated_at` 使用数据库时钟或统一应用时钟；面试截止判断只使用 PostgreSQL 数据库时钟。
- 迁移失败返回稳定错误码，不返回内部 SQL、堆栈或模型原文。

## 2. 简历任务

允许迁移：

| 当前状态 | 事件 | 新状态 | 守卫条件 |
| --- | --- | --- | --- |
| `uploaded` | 文件校验完成 | `extracting` | 文件存在且未删除 |
| `extracting` | 文本提取成功 | `analyzing` | 文本非空，页数和大小合规 |
| `extracting` | 提取失败 | `failed` | 错误可记录 |
| `analyzing` | 分析 Schema 校验成功 | `generating_questions` | 分析结果已持久化 |
| `analyzing` | 分析失败 | `failed` | 有失败阶段 |
| `generating_questions` | 10 题校验成功 | `completed` | 数量、覆盖、去重通过 |
| `generating_questions` | 出题失败 | `failed` | 有失败阶段 |
| `completed` | 删除原始文件 | `source_deleted` | 衍生数据仍可见 |
| 任一处理中 | 用户取消 | `failed` | 记录取消原因 |
| `failed` | 用户重试 | 新任务 `uploaded` | 新任务 ID，旧任务保留 |

禁止迁移：

- `completed` 不能回到处理阶段。
- `source_deleted` 不能重新访问原始文件。
- 同一任务不能并发进入两个处理阶段。
- 任务删除或到期后不能继续生成结果。

事务边界：

1. Worker 领取并设置 `extracting`。
2. 文本写入和阶段更新同一事务。
3. 分析结果和阶段更新同一事务。
4. 10 道题批量写入和完成状态同一事务。
5. 原始文件删除通过墓碑事务加重试任务完成。

删除原始文件时，证据清理与任务状态迁移必须同时满足：

- 清除 `resume_texts.extracted_text` 和 `page_map`，并完成对象存储删除。
- 把分析、题目和报告证据重写为最长 200 字符的脱敏摘要，写入 `source_deleted`。
- 清除页码、章节、字符区间、原始文件名和可拼接上下文；无法安全脱敏的证据直接删除。
- 删除后的证据读取只返回摘要、能力标签、题目关联和 `source_deleted`，不得重新读取已删除正文。

## 3. 模拟面试

允许迁移：

| 当前状态 | 事件 | 新状态 | 守卫条件 |
| --- | --- | --- | --- |
| `created` | 用户开始 | `in_progress` | 用户确认配置，写入 `deadline_at` |
| `created` | 取消 | `cancelled` | 未开始 |
| `in_progress` | 完成全部主问题 | `completed` | 所有已接收轮次评分完成 |
| `in_progress` | 服务端截止 | `timed_out` | `now >= deadline_at` |
| `in_progress` | 不可恢复错误 | `failed` | 错误已记录 |
| `in_progress` | 用户提前结束整场 | `cancelled` | 仅 P1；独立操作、二次确认，原因 `user_ended_interview` |
| `timed_out` | 评分已完成 | `timed_out` | 保持终态，设置反馈解锁时间 |
| `completed` | 评分回放 | `completed` | 不重复写报告 |

截止处理：

- 接收回答事务内同时校验 `state = in_progress` 和数据库 `server_now < deadline_at`；相等即已截止。
- 超时扫描与回答提交必须锁定同一面试行，禁止扫描先进入终态后提交仍成功，或提交先完成前扫描覆盖其状态。
- 到达截止时间后，新回答和追问提交返回 `interview_time_expired`。
- 截止前已接收的回答保留并继续评分；未作答轮次设置为 `unanswered`。
- 超时进入终态后，报告可用时设置 `feedback_unlocked_at`。
- 恢复请求不能延长 `deadline_at`，也不能把 `timed_out` 改回 `in_progress`；`client_submitted_at` 不参与判断。
- P0 不提供 `in_progress -> cancelled` 的用户入口；结束当前追问链只改变轮次和追问链，不改变面试终态。
- P1 提前结束与自然完成、截止和失败使用不同 `end_reason`，不得互相覆盖。

评分完成与终态：

- 面试不会因为所有主问题被展示而立刻终态；必须确认所有已接收轮次评分完成。
- 评分失败保持可重试状态，不写错题。
- 报告生成失败可以重试，但面试终态不因报告暂时失败而回退。

## 4. 面试轮次

公开边界：

- `interview_turns` 可以持久化分项分数、总分、通过结论、失分点、参考答案和评分标准，但这些字段不得进入回答提交响应或进行中面试查询 DTO。
- 提交回答的状态迁移完成后，公开响应固定为 `202 Accepted`、`state = scoring`、`accepted_at` 和中性进度；内部评分结果只由服务层和终态报告读取。
- 进行中查询只返回当前题目、已提交轮次、主问题完成数、剩余题数、当前追问链状态和剩余时间；不得返回趋势、预测分数、关键错误或追问触发依据。
- 面试进入终态且所有已接收轮次离开 `scoring` 后，报告 DTO 才允许返回受保护反馈。
- 永久评分失败必须转为可解释的 `scoring_failed`，不能无限停留在 `scoring`；报告可返回已成功轮次并标记 `incomplete_scoring`，不得暴露失败轮次的中间分数或参考答案。
- 后续评分恢复仍在同一面试终态内重生成报告，不重新开放提交，也不改变 `feedback_unlocked_at` 的语义。
- DTO 裁剪是公开边界的唯一依据；前端隐藏、字段置空或额外调试端点都不能替代服务端裁剪。

允许迁移：

| 当前状态 | 事件 | 新状态 | 守卫条件 |
| --- | --- | --- | --- |
| `pending` | 展示题目 | `awaiting_answer` | 面试进行中且未过截止 |
| `awaiting_answer` | 接收回答 | `scoring` | 首次提交、幂等键有效 |
| `awaiting_answer` | 跳过追问 | `skipped` | 仅追问；原因 `user_skipped` |
| `awaiting_answer` | 结束当前追问链 | `branch_completed` | 仅追问；原因 `user_ended_branch`，不结束整场 |
| `awaiting_answer` | 整场截止 | `unanswered` | 尚未提交 |
| `scoring` | 评分成功且通过 | `passed` | 分数和关键错误已确定性计算 |
| `scoring` | 评分成功且未通过 | `failed` | 分数和关键错误已确定性计算 |
| `scoring` | 评分超时 | `scoring_failed` | 尝试记录已持久化 |
| `scoring_failed` | 重试评分 | `scoring` | 未超过尝试上限且未过截止 |
| `scoring_failed` | 尝试耗尽或永久失败 | `scoring_failed` | 保持可解释失败终态；当前链按规则结束，不写错题 |
| `passed` | 生成追问 | `pending` 子轮次 | 分数 >=85、无关键错误、预算允许 |
| `passed` | 不满足追问条件 | `branch_completed` | 结束当前分支 |
| `failed` | 写入错题 | `branch_completed` | 错题幂等写入成功 |
| `skipped` | 链结束 | `branch_completed` | 已提交结果不变 |

禁止迁移：

- `passed` 或 `failed` 被第二次评分覆盖。
- `unanswered` 被当作失败轮次写入错题。
- `scoring_failed` 直接写入错题，或无限停留在 `scoring`。
- 子轮次在父轮次未评分前独立开始。
- 同一轮次接受两次不同回答。
- 结束当前追问链设置面试 `ended_at` 或取消未展示主问题。
- 跳过与结束追问链复用同一原因值。

提交事务必须完成：

1. 校验资源所有权。
2. 校验面试 `in_progress`。
3. 校验 `now < deadline_at`。
4. 校验轮次 `awaiting_answer`。
5. 校验幂等键和请求体。
6. 写入回答和 `submitted_at`。
7. 将轮次更新为 `scoring`。
8. 创建评分任务。

提交事务的公开结果只包含轮次 ID、接收时间、`scoring` 状态和中性进度，不等待同步评分完成，也不在响应构造前读取评分表。

## 5. 追问链

允许迁移：

| 当前状态 | 事件 | 新状态 | 守卫条件 |
| --- | --- | --- | --- |
| `awaiting_answer` | 接收回答 | `scoring` | 与轮次状态一致 |
| `scoring` | 轮次通过且高分 | `generating_follow_up` | 深度和预算未耗尽 |
| `scoring` | 轮次未通过 | `completed` | 记录终止原因 |
| `generating_follow_up` | 生成有效追问 | `awaiting_answer` | 深度加一、答案次数加一 |
| `generating_follow_up` | 生成失败 | `follow_up_failed` | 可重试 |
| `follow_up_failed` | 重试耗尽 | `completed` | 结束当前链 |
| `awaiting_answer` | 用户跳过 | `completed` | 原因 `user_skipped`，不写错题 |
| `awaiting_answer` | 用户结束当前追问链 | `completed` | 原因 `user_ended_branch`，不设置面试终态 |
| `awaiting_answer` | 整场截止 | `completed` | 原因 `deadline_reached`，不新增追问 |

结束当前追问链的事务必须：

1. 锁定面试、当前轮次和追问链。
2. 校验面试仍为 `in_progress`、轮次为当前追问的 `awaiting_answer`。
3. 保持已提交轮次和评分结果不变。
4. 把当前链置为 `completed` 并写入 `user_ended_branch`。
5. 让下一主问题进入 `pending`；不设置面试 `ended_at`，不取消未展示主问题。

同一幂等键重放返回首次结果；不同幂等键且链已结束时返回状态冲突，不覆盖首次原因。

预算更新规则：

- `answer_count` 在首次接收回答时加 1。
- `depth_used` 在展示新追问时加 1。
- `tokens_used` 在每次 LLM 调用完成后按实际用量原子累加。
- 预算扣减与状态迁移同一事务提交，避免恢复重置。
- 任何预算达到上限都直接结束当前链。

## 6. 检索问答

允许迁移：

| 当前状态 | 事件 | 新状态 | 守卫条件 |
| --- | --- | --- | --- |
| `created` | 开始检索 | `retrieving` | 输入通过校验 |
| `retrieving` | 检索完成 | `answering` | 结果已裁剪、去重 |
| `retrieving` | 检索失败或无结果 | `answering` | 进入模型知识或拒答分支 |
| `answering` | 结构校验成功 | `completed` | 最终答案持久化 |
| `answering` | 不可恢复失败 | `failed` | 错误已记录 |

SSE 流事件不是数据库状态事实来源；以 `qa_requests.state`、`qa_requests.answer_json` 和持久化 `qa_stream_events` 为准。事件序号是每请求持久化序号，不是连接内计数；连接断开不使问答失败。

流式规则：

- `UNIQUE (qa_request_id, seq)` 保证序号不重复、不回退。
- `completed` 与 `error` 互斥，每个终态最多一次。
- 最终结构化结果和 `completed` 事件先落库，再发送完成事件。
- 重连从 PostgreSQL 按 `seq > cursor` 补发，不重新执行检索或模型调用，也不再次扣减预算。
- Redis 只能缓存事件，清空后仍可从 PostgreSQL 重建游标和终态。

## 7. 错题写入

错题写入是评分成功后的幂等副作用：

```text
passed -> 不写错题
failed -> 检查 critical_error / score_band
       -> upsert wrong_questions ON turn_id
       -> 关联 weak point evidence
```

写入规则：

- 只有 `failed` 且评分已经成功提交的轮次可写入。
- `scoring_failed`、`timed_out`、`skipped`、`unanswered` 不写入。
- 网络重试和报告重建不能产生重复错题。
- 错题写入失败不应把评分回退为未通过或未评分；记录重试任务和可观测错误。

## 8. 删除与到期

删除状态机：

```text
active
  -> delete_requested
  -> tombstoned
  -> object_delete_pending
  -> deleted

object_delete_pending -> delete_failed
delete_failed -> object_delete_pending
```

规则：

- 用户立即删除使用 `delete_requested`，接口成功响应前至少完成业务可见性墓碑。
- 原始简历删除后，只保留不可恢复正文的脱敏证据摘要；每条最长 200 字符，并标记 `source_deleted`。
- 删除事务必须清除原文、页码、章节、文件名、字符区间和可拼接上下文；无法安全脱敏的证据删除。
- 到期任务只删除对应保留范围，不能把未到期数据误删。
- 每个删除操作只记录最小审计元数据：操作类型、资源类型内部枚举、哈希化资源 ID、结果、时间和请求 ID。
- 审计保留 365 天，到期后删除或不可逆匿名化；不得保存用户业务正文、原始用户 ID 或可逆个人标识。

## 9. 并发矩阵

| 场景 | 控制方式 | 期望结果 |
| --- | --- | --- |
| 两个回答同时提交 | 行锁 + 轮次状态条件更新 | 一个成功，另一个幂等或冲突 |
| 超时扫描与提交并发 | 面试行锁 + PostgreSQL 数据库时间 | 截止前提交成功，截止瞬间及之后拒绝；不得互相覆盖终态 |
| 两个 Worker 领任务 | `FOR UPDATE SKIP LOCKED` + 租约 | 只一个执行，写入递增 `fencing_token` |
| 旧 Worker 租约被接管 | 当前 `lease_owner` + `fencing_token` 条件更新 | 旧 Worker 成功、失败和续期写入均被拒绝 |
| SSE 断线重连 | 持久事件序号 + `Last-Event-ID` | 只补发后续事件，不重跑检索/模型、不重复扣费 |
| 两设备继续同一面试 | 读取当前轮次和预算 | 不复制轮次，不重置预算 |
| 错题回放 | 唯一约束 | 只存在一条错题 |
| 报告重建 | 报告 upsert | 不改变原始评分 |
| 删除与读取并发 | 删除墓碑可见性 | 删除后读取不可见 |

## 10. 状态可观测性

每次关键迁移只记录最小审计元数据：

- 操作类型、资源类型内部枚举和哈希化资源 ID。
- 结果、时间和请求 ID。

迁移审计不得包含旧/新业务正文、答案、简历正文、Prompt、参考答案、证据原文、原始用户 ID 或可逆个人标识。需要排查状态问题时，通过受控 trace 和业务表定位，不把业务内容复制进审计。

## 11. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-17 | 建立简历、面试、轮次、追问链、检索问答、错题和删除状态机 |
| v0.2 | 2026-10-17 | 按 DR-02 冻结内部评分与公开提交 DTO 的裁剪边界，同步需求 v1.2 |
| v0.3 | 2026-10-17 | 同步需求 v1.4，账号注册不签发会话，评分公开边界保持不变 |
| v0.4 | 2026-10-17 | 按 DR-03 至 DR-06 冻结中性进度、P0 结束追问、P1 整场结束、删除后证据清理和 365 天最小审计 |
| v0.5 | 2026-10-17 | 接受四项 ADR；补充数据库时钟截止边界、并发行锁、SSE 持久游标、任务 fencing 租约和 `scoring_failed` 终态规则 |
