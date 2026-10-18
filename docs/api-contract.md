# 技术面试智能体接口契约

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.8 |
| 文档状态 | 隐私删除、保留清理与运维指标契约已落地 |
| 更新日期 | 2026-10-18 |
| 基础路径 | `/api/v1` |
| 数据格式 | JSON UTF-8；文件上传使用 `multipart/form-data` |

> 本契约冻结已批准的服务边界。账号与密码重置接口依据 `DR-01`，回答提交和中性进度依据 `DR-02`、`DR-03`，结束追问依据 `DR-04`，删除后证据与最小审计依据 `DR-05`、`DR-06`，`web/` 首个用户可见切片依据 `DR-07`。

## 1. 通用约定

### 1.1 请求

- 时间使用 ISO 8601 UTC，例如 `2026-10-17T08:30:00Z`。
- 分页使用 `limit`（默认 20，最大 100）和 `cursor`。
- 所有创建、提交和删除操作支持 `Idempotency-Key` 请求头；要求幂等的接口缺少该头时返回 `400 idempotency_key_required`。
- 客户端发送的 `submitted_at` 只用于诊断，不参与截止判断。
- 写操作使用 `dry_run` 由所属工具定义；用户业务 API 不默认执行外部副作用。
- 登录后的改变状态请求携带 `X-CSRF-Token`，值来自前端可读的 `interview_csrf` Cookie。登录、注册和未认证的密码重置请求没有可校验的会话，只执行 Origin/Referer allowlist 校验。

### 1.2 通用响应头

| Header | 说明 |
| --- | --- |
| `X-Request-ID` | 服务端请求标识 |
| `X-Server-Time` | 服务端 UTC 时间，用于客户端提示，不用于判定 |
| `Retry-After` | 限流或临时失败时可重试秒数 |

### 1.3 错误结构

```json
{
  "error": {
    "code": "interview_time_expired",
    "message": "本场面试已结束",
    "retryable": false,
    "request_id": "req_01J...",
    "details": {
      "interview_id": "..."
    }
  }
}
```

规则：

- `code` 是稳定机器码，前端按它映射文案。
- `message` 是安全、可理解的用户文案，不包含内部堆栈、SQL、Prompt 或模型原文。
- 越权资源与不存在资源使用相同公开错误，避免枚举。
- `details` 只允许白名单字段，不回显简历正文、完整回答或证据原文。

### 1.4 稳定错误码

| HTTP | Code | 含义 |
| ---: | --- | --- |
| 400 | `invalid_request` | 参数不合法 |
| 400 | `idempotency_key_required` | 缺少幂等键 |
| 401 | `authentication_required` | 未登录或会话失效 |
| 403 | `forbidden` | 无操作权限 |
| 404 | `resource_not_found` | 资源不存在或当前用户不可见 |
| 409 | `idempotency_conflict` | 相同幂等键但请求体不同 |
| 409 | `turn_already_submitted` | 轮次已提交 |
| 409 | `invalid_state_transition` | 当前状态不允许该操作 |
| 409 | `interview_time_expired` | 面试已到达服务端截止时间 |
| 409 | `report_not_ready` | 面试尚未结束或已接收轮次仍在评分 |
| 409 | `feedback_locked` | 面试尚未结束，受保护反馈不可用 |
| 410 | `reset_token_invalid` | 密码重置链接无效、过期或已使用 |
| 401 | `invalid_credentials` | 邮箱或密码错误，不区分账号是否存在 |
| 413 | `file_too_large` | 文件超过 10 MB |
| 415 | `unsupported_file_type` | 文件类型不允许 |
| 422 | `schema_validation_failed` | 模型或请求结构校验失败 |
| 422 | `text_extraction_unsupported` | 扫描件或无法提取文本 |
| 422 | `unsupported_source` | 请求包含未授权的 URL 或知识源 |
| 429 | `rate_limited` | 超出限流 |
| 503 | `upstream_unavailable` | 上游模型或检索服务暂不可用 |

## 2. 认证

认证接口依据已批准的 `DR-01` 冻结。所有认证接口使用 JSON；会话 Cookie 只在登录成功后由服务端设置。

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/logout
GET  /api/v1/auth/session
POST /api/v1/auth/password-reset/request
POST /api/v1/auth/password-reset/confirm
```

### 2.1 注册

```http
POST /api/v1/auth/register
Content-Type: application/json
```

```json
{
  "email": "user@example.com",
  "password": "correct horse battery staple"
}
```

响应固定为 `202 Accepted`：

```json
{
  "accepted": true,
  "next_action": "login"
}
```

规则：

- 邮箱经标准化后唯一；新账号密码使用 Argon2id 哈希。
- 已存在邮箱与成功创建新账号必须返回相同的 `202` 和响应体，不建立会话，也不设置 `Set-Cookie`；`X-Request-ID` 等请求级标识可以不同。
- 注册成功只表示请求已按中性结果处理；客户端应提示用户前往登录。登录是唯一签发会话的入口。
- 并发注册触发唯一约束冲突时，按已存在邮箱的同一中性路径处理，不返回账号存在性信息。
- 注册请求按来源和标准化邮箱维度限流。
- 已存在邮箱不得通过公开响应、错误码或可观测处理路径暴露；服务端应对成功创建和已存在分支执行一致的基础校验与耗时控制。
- 响应不返回密码哈希、原始会话令牌或内部会话 ID。
- 注册流程不依赖邮件服务，邮件服务故障不得阻塞注册或后续登录。

### 2.2 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "email": "user@example.com",
  "password": "correct horse battery staple"
}
```

成功响应 `200 OK`：

```json
{
  "user": {
    "id": "uuid",
    "display_name": "示例用户"
  },
  "session": {
    "expires_at": "2026-10-24T08:30:00Z"
  }
}
```

同时设置两个 Cookie：

- `interview_session`：服务端会话，使用 `HttpOnly`、`Secure`、`SameSite=Lax`。
- `interview_csrf`：前端可读的 CSRF verifier，使用 `Secure`、`SameSite=Lax`。

数据库 `auth_sessions.csrf_token_hash` 只保存 verifier 哈希，不保存原始值。失败统一返回：

```json
{
  "error": {
    "code": "invalid_credentials",
    "message": "邮箱或密码不正确",
    "retryable": false,
    "request_id": "req_01J..."
  }
}
```

规则：

- 邮箱不存在和密码错误使用相同状态码、错误码和面向用户文案。
- 登录和注册均需限流，并记录不含凭据的安全审计事件。
- 登录成功是唯一签发新会话的入口；服务端只保存令牌哈希。
- `interview_session` 不进入 URL、localStorage、日志或响应 JSON。

### 2.3 退出与当前会话

```http
POST /api/v1/auth/logout
GET  /api/v1/auth/session
```

退出响应 `204 No Content`；重复退出仍返回成功，不要求会话继续有效。已登录客户端的退出请求携带 `X-CSRF-Token`；服务端同时校验允许写请求来源。当前会话响应只返回用户标识、显示名和会话到期时间，不返回原始令牌或密码字段。

### 2.4 请求密码重置

```http
POST /api/v1/auth/password-reset/request
Content-Type: application/json
```

```json
{
  "email": "user@example.com"
}
```

无论邮箱是否存在、邮件是否实际发送，均返回 `202 Accepted` 和同一中性结果：

```json
{
  "accepted": true
}
```

规则：

- 请求按账号和来源维度限流，响应不包含账号存在性、邮件可达性或令牌信息。
- 一次性重置令牌只保存哈希，必须短时有效且只能使用一次。
- 令牌不得出现在日志、埋点、错误详情或客服文案中。
- 邮件发送失败可由用户稍后重试，但不能将其变成账号枚举信号。
- 邮件服务故障不得使注册或登录不可用。

### 2.5 确认密码重置

```http
POST /api/v1/auth/password-reset/confirm
Content-Type: application/json
```

```json
{
  "token": "opaque-token",
  "new_password": "new correct horse battery staple"
}
```

成功响应 `204 No Content`。令牌无效、过期、已使用或已被撤销时统一返回 `410 reset_token_invalid`。成功后必须撤销该用户全部旧会话，旧令牌不可重放。

### 2.6 认证安全属性

- `interview_session` 使用 `HttpOnly`、`Secure`、`SameSite=Lax`；`interview_csrf` 是前端可读的 verifier，写请求同时携带 `X-CSRF-Token` 并执行 Origin/Referer allowlist 校验。
- 响应只返回用户 ID、显示名和会话到期时间，不返回密码哈希或内部令牌。
- 登录失败不区分“邮箱不存在”和“密码错误”。
- 注册与找回密码请求始终返回中性结果；一次性令牌只保存哈希，短时有效且使用后撤销全部旧会话。
- 会话撤销和密码重置成功后，旧 Cookie 不能继续访问业务接口。

## 3. 工作台与历史

### 3.1 获取工作台摘要

```http
GET /api/v1/dashboard
```

响应：

```json
{
  "user": {
    "id": "uuid",
    "display_name": "示例用户"
  },
  "recent_tasks": [
    {
      "id": "uuid",
      "type": "resume",
      "title": "后端简历.pdf",
      "state": "completed",
      "updated_at": "2026-10-17T08:00:00Z"
    }
  ],
  "recent_interviews": [],
  "server_time": "2026-10-17T08:30:00Z"
}
```

### 3.2 历史列表

```http
GET /api/v1/history?type=interview&limit=20&cursor=...
```

只返回当前用户资源。`type` 支持 `resume`、`qa`、`interview`、`wrong_question`，后续类型不得改变已有字段语义。响应固定为以下分页信封：

```json
{
  "items": [
    {
      "id": "uuid",
      "type": "interview",
      "title": "后端模拟面试",
      "state": "completed",
      "updated_at": "2026-10-17T08:00:00Z"
    }
  ],
  "next_cursor": "opaque-cursor"
}
```

没有下一页时 `next_cursor` 为 `null`。前端使用 `{items, next_cursor}` 每次加载 10 条；游标只表示稳定的降序位置，不包含用户标识或可枚举资源信息。

## 4. 简历

### 4.1 上传简历

```http
POST /api/v1/resumes
Content-Type: multipart/form-data
Idempotency-Key: <uuid>
```

表单字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `file` | 是 | PDF 或 DOCX，<=10 MB，<=10 页 |
| `target_role` | 否 | P1 的岗位信息，P0 可忽略并明确返回 |

响应 `202 Accepted`：

```json
{
  "resume_task_id": "uuid",
  "state": "uploaded",
  "created_at": "2026-10-17T08:30:00Z"
}
```

实现要求：

- 服务端校验扩展名、声明 MIME、魔数、大小和页数。
- 对象键随机生成，不接受客户端路径。
- 文件不合格时不进入分析队列。
- 重复上传按 P1 去重规则处理，P0 默认创建新任务。

### 4.2 查询简历任务

```http
GET /api/v1/resumes/{task_id}
```

```json
{
  "id": "uuid",
  "state": "completed",
  "failure_stage": null,
  "error_code": null,
  "analysis": {
    "schema_version": "1.0",
    "skills": [],
    "projects": [],
    "unverified_items": []
  },
  "questions": [
    {
      "id": "uuid",
      "sequence": 1,
      "question_text": "...",
      "category": "backend",
      "difficulty": "medium",
      "assessment_points": ["..."],
      "evidence_refs": ["..."]
    }
  ],
  "created_at": "2026-10-17T08:30:00Z",
  "completed_at": "2026-10-17T08:31:00Z"
}
```

公开题目 DTO 永远不包含 `reference_answer` 或 `scoring_rubric`。

### 4.3 重新提交失败任务

```http
POST /api/v1/resumes/{task_id}/retry
Idempotency-Key: <uuid>
```

只允许失败任务。返回新任务 ID，原任务保留审计。删除原始文件后不提供恢复原文件能力。

### 4.4 删除原始简历

```http
DELETE /api/v1/resumes/{task_id}/source
Idempotency-Key: <uuid>
```

响应 `202 Accepted` 或 `204 No Content`。原始文件立即不可访问，衍生数据按审批后的证据规则处理。

## 5. 检索问答

### 5.1 创建问答

```http
POST /api/v1/qa
Content-Type: application/json
Idempotency-Key: <uuid>
```

```json
{
  "question": "如何设计幂等的支付回调？",
  "answer_preference": "concise"
}
```

响应 `202 Accepted`：

```json
{
  "qa_request_id": "uuid",
  "stream_url": "/api/v1/qa/uuid/stream",
  "state": "created"
}
```

实现要求：

- 空输入、超长输入和非技术输入返回可理解结果。
- 用户文本中的 URL 不作为知识源；任意 URL 返回 `422 unsupported_source`。
- 用户输入不能扩大方向知识源白名单。

### 5.2 SSE 流

```http
GET /api/v1/qa/{qa_request_id}/stream
Accept: text/event-stream
Last-Event-ID: 12
```

事件序列：

```text
event: started
id: 1
data: {"request_id":"req_01J..."}

event: delta
id: 2
data: {"text":"先给出直接结论。"}

event: delta
id: 3
data: {"text":"再展开设计取舍。"}

event: completed
id: 4
data: {"answer":{...},"evidence":[],"extended_questions":[]}
```

事件类型：

| Event | 说明 |
| --- | --- |
| `started` | 已建立流并确认所有权 |
| `delta` | 可展示文本增量，不保证最终事实 |
| `evidence` | 可选的中途证据摘要，不能用于提前公开隐藏答案 |
| `completed` | 最终结构化结果，必须唯一且最后出现 |
| `error` | 失败事件，含稳定错误码和是否可重试 |

规则：

- 每个事件带持久化的请求内单调递增 `id`，用于 `Last-Event-ID` 或 `after_seq` 重连；序号跨连接保持一致。
- `delta` 只用于显示；最终答案以 `completed.answer` 和持久化结果为准。
- 重连从 PostgreSQL 补发序号更大的事件，不重新执行检索、模型调用或消耗预算；Redis 只能作为缓存。
- `completed` 与 `error` 互斥，同一请求每个终态最多出现一次。
- 最终结构化答案和 `completed` 事件先持久化，再发送完成事件。
- 客户端断开不取消服务端已完成的结构化保存；客户端按事件 `id` 去重。
- 流结束后仍可通过 `GET /api/v1/qa/{id}` 获取最终结果。

### 5.3 查询最终问答

```http
GET /api/v1/qa/{qa_request_id}
```

未完成时返回状态；已完成时返回与 `completed` 一致的最终结构。是否进入历史由 P1 保存语义决定，P0 不把临时问答自动写入错题。

## 6. 模拟面试

### 6.1 创建面试

```http
POST /api/v1/interviews
Content-Type: application/json
Idempotency-Key: <uuid>
```

```json
{
  "direction": "backend",
  "difficulty": "balanced",
  "topic_keys": ["db_transactions", "api_idempotency"]
}
```

响应 `201 Created`：

```json
{
  "interview_id": "uuid",
  "state": "created",
  "main_question_count": 5,
  "deadline_at": null,
  "configuration": {
    "direction": "backend",
    "difficulty": "balanced"
  }
}
```

创建时生成内部蓝图，但不在公开响应中返回参考答案、评分标准或完整随机化计划。

### 6.2 开始面试

```http
POST /api/v1/interviews/{interview_id}/start
Idempotency-Key: <uuid>
```

响应：

```json
{
  "interview_id": "uuid",
  "state": "in_progress",
  "server_time": "2026-10-17T08:30:00Z",
  "deadline_at": "2026-10-17T09:10:00Z",
  "current_turn": {
    "id": "uuid",
    "type": "main",
    "depth": 0,
    "question_text": "...",
    "topic_key": "api_idempotency",
    "difficulty": "medium"
  },
  "progress": {
    "main_questions_completed": 0,
    "main_questions_total": 5
  }
}
```

开始操作只允许一次；重复开始返回当前状态。`deadline_at` 只能由服务端写入。

### 6.3 查询当前面试

```http
GET /api/v1/interviews/{interview_id}
```

进行中响应只包含：

- 当前题目或“正在准备下一题”。
- 已提交轮次、主问题完成数、剩余题数和当前追问链状态。
- 服务端剩余时间和截止时间。
- 中立错误和恢复状态。

不包含公开的分数、参考答案、错题详情、详细失分原因、通过趋势、预测分数、关键错误提示或追问触发依据。`DR-02`、`DR-03` 已批准，内部评分和分支判断不得进入该响应。

中性进度字段固定为：

```json
{
  "progress": {
    "main_questions_completed": 1,
    "main_questions_total": 5,
    "main_questions_remaining": 4,
    "current_follow_up_chain": "awaiting_answer",
    "remaining_seconds": 2137
  }
}
```

`current_follow_up_chain` 只允许中性流程枚举，例如 `awaiting_answer`、`scoring`、`generating_follow_up`、`completed`；不得暴露是否因高分触发追问、分数区间或关键错误。

### 6.4 提交回答

```http
POST /api/v1/interviews/{interview_id}/turns/{turn_id}/answer
Content-Type: application/json
Idempotency-Key: <uuid>
```

```json
{
  "answer": "我的方案是使用业务幂等键与唯一约束...",
  "client_submitted_at": "2026-10-17T08:31:00Z"
}
```

公开响应固定为 `202 Accepted`：

```json
{
  "turn_id": "uuid",
  "state": "scoring",
  "accepted_at": "2026-10-17T08:31:01Z",
  "progress": {
    "main_questions_completed": 1,
    "main_questions_total": 5
  },
  "next_action": "wait"
}
```

不得在此响应中返回分项分数、总分、是否通过、参考答案、评分标准或错题。内部评分写入后通过服务层判断下一动作。

提交规则：

- 首次提交成功返回 `202`。
- 相同幂等键和相同请求体返回首次接收结果。
- 相同轮次不同幂等键返回 `409 turn_already_submitted`。
- `now >= deadline_at` 返回 `409 interview_time_expired`。
- 截断前已接收的回答继续评分；截止后不创建新轮次。

### 6.5 跳过追问

```http
POST /api/v1/interviews/{interview_id}/turns/{turn_id}/skip
Idempotency-Key: <uuid>
```

只允许当前追问的 `awaiting_answer`。已提交结果不变，当前链结束并进入下一主问题。响应只返回状态和下一动作。

### 6.6 结束当前追问

```http
POST /api/v1/interviews/{interview_id}/turns/{turn_id}/end-branch
Idempotency-Key: <uuid>
```

`DR-04` 已批准，P0 行为固定为：

- 仅允许当前追问轮次处于 `awaiting_answer`，并只结束当前追问链。
- 已提交轮次和评分结果保持不变；当前链进入 `branch_completed`，随后进入下一主问题。
- 请求可带稳定原因枚举 `user_ended_branch`；该原因与 `user_skipped`、P1 的 `user_ended_interview` 分开存储，不得互相覆盖。
- 重复请求按幂等键返回首次结果；对主问题或不存在的追问返回明确的状态冲突。
- 该端点不得取消整场面试、取消未展示的主问题或设置 `ended_at`。

### 6.7 结束整场（P1，不包含在 P0）

```http
POST /api/v1/interviews/{interview_id}/end
Idempotency-Key: <uuid>
```

P1 才允许提供该端点，必须使用独立操作和二次确认，并把未完成轮次标记为 `unanswered` 或 `cancelled`。P0 不暴露该端点，也不在“结束当前追问”同一层级提供相似按钮。整场结束原因固定使用 `user_ended_interview`，不得复用跳过或结束追问链的原因。

### 6.8 查询报告

```http
GET /api/v1/interviews/{interview_id}/report
```

只有面试进入终态且所有已接收轮次离开 `scoring` 后返回受保护反馈；否则返回 `409 report_not_ready`。报告结构：

```json
{
  "interview_id": "uuid",
  "state": "completed",
  "direction": "backend",
  "scoring_status": "complete",
  "summary": {
    "main_question_count": 5,
    "follow_up_count": 2,
    "passed_count": 5,
    "failed_count": 2
  },
  "turns": [
    {
      "id": "uuid",
      "parent_turn_id": null,
      "type": "main",
      "depth": 0,
      "result": "passed",
      "score_total": 88,
      "score_breakdown": {},
      "loss_reasons": []
    }
  ],
  "wrong_questions": [],
  "weak_points": []
}
```

完整报告只在整场进入终态且所有已接收轮次离开 `scoring` 后返回。逐轮详细分数、参考答案、失分原因和追问依据只在报告接口解锁，回答提交接口不得返回这些字段。

永久评分失败的已接收轮次必须转为可解释的 `scoring_failed`，不能无限停留在 `scoring`。此时可以返回已成功评分的内容，并把 `scoring_status` 标记为 `incomplete_scoring`，但不能返回失败轮次的中间分数、参考答案、失分原因或追问依据。后续恢复评分时，在同一面试终态内重新生成报告并更新状态。

## 7. 错题与薄弱点

### 7.1 错题列表

```http
GET /api/v1/wrong-questions?state=active&topic=...&limit=20&cursor=...
```

只返回当前用户数据，默认排除已删除和已过期内容。支持按日期、主题、难度和掌握状态筛选。

### 7.2 错题详情

```http
GET /api/v1/wrong-questions/{wrong_question_id}
```

整场面试结束后才返回原题、用户回答、参考答案、分项分数、失分原因和复习建议。面试进行中访问返回 `409 feedback_locked`，不返回任何隐藏内容。

### 7.3 薄弱点

```http
GET /api/v1/weak-points?state=identified&limit=20&cursor=...
GET /api/v1/weak-points/{weak_point_id}
```

返回聚合主题、严重程度、失败次数、最近时间、复习建议和来源错题摘要。不得输出人格、智力或胜任力定论。

## 8. 删除与隐私

```http
DELETE /api/v1/me/data
Idempotency-Key: <uuid>
```

响应 `202 Accepted`，表示删除请求已登记并开始异步清理。接口成功前至少完成业务可见性墓碑，后续通过删除状态接口查询。

```http
GET /api/v1/me/data-deletion
GET /api/v1/me/data-deletion/{request_id}
```

返回删除范围、状态、时间和审计摘要。`DR-05`、`DR-06` 已批准，响应只能包含操作类型、资源类型内部枚举、结果、时间和请求标识；资源标识使用不可逆哈希，不返回原始资源 ID。

删除实现约定：

- 删除请求立即把简历任务、问答、面试和错题标记为不可见，并把私有对象标记为 `delete_pending`。
- `delete_account_data` Worker 任务完成对象清理和业务主体删除后，把用户状态转为 `deleted`，后续会话返回 `401 authentication_required`。
- `retention_cleanup` 任务清理 30 天到期原始简历、90 天到期衍生数据和 365 天到期审计记录。
- 删除请求状态保存在 `data_deletion_requests`，终态只包含范围、结果摘要和稳定错误码，不包含用户正文或原始资源 ID。

运维指标：

```http
GET /api/v1/ops/metrics
Authorization: Bearer <ops_metrics_token>
```

未配置或错误 token 统一返回 `404 resource_not_found`。响应只包含任务状态/类型计数、评分失败数、追问终止原因、删除请求状态和过期审计数，不包含用户内容或资源 ID。

原始简历删除后的证据 DTO 固定为：

```json
{
  "evidence_id": "opaque-id",
  "summary": "使用幂等键和唯一约束处理重复提交，摘要不超过 200 个字符。",
  "capability_labels": ["API 设计"],
  "question_ref": "question-id",
  "source_state": "source_deleted"
}
```

不得返回原文引用、页码、章节定位、原始文件名、可拼接上下文或任何可恢复正文的字段。摘要每条最多 200 个字符；删除时无法安全脱敏的证据必须删除或替换为不可恢复的通用摘要。

## 9. 审计与权限测试矩阵

| 场景 | 预期 |
| --- | --- |
| 未登录访问任一业务接口 | `401 authentication_required` |
| 正确邮箱错误密码与不存在邮箱 | 均返回 `401 invalid_credentials`，状态码和文案一致 |
| 新邮箱与已存在邮箱注册 | 均返回相同的 `202` 和中性响应体，不设置会话 Cookie，不暴露账号存在性 |
| 注册后未调用登录 | 不建立会话；访问业务接口返回 `401 authentication_required` |
| 用户退出后复用旧会话 | `401 authentication_required`，会话立即失效 |
| 密码找回请求的邮箱不存在或邮件发送失败 | 返回与成功一致的中性结果，不泄露账号存在性或邮件可达性 |
| 已使用或过期的密码重置令牌 | `410 reset_token_invalid`，不返回账号信息 |
| 密码重置成功后旧会话 | 全部立即失效，必须重新登录 |
| 用户 A 访问用户 B 的资源 | `404 resource_not_found` |
| 面试进行中访问报告 | `409 report_not_ready` |
| 截止后提交回答 | `409 interview_time_expired` |
| 重复回答不同幂等键 | `409 turn_already_submitted` |
| 相同幂等键相同请求 | 返回首次结果，不重复评分 |
| 相同幂等键不同请求体 | `409 idempotency_conflict` |
| 提交回答成功 | 仅返回 `202`、已接收和中性进度，不包含分数、通过结论、失分点或追问依据 |
| 进行中查询面试 | 仅返回中性流程、已提交轮次、完成数、剩余题数和时间，不返回趋势、预测或追问依据 |
| 结束当前追问 | 只结束当前链并进入下一主问题，不设置整场 `ended_at` |
| 跳过、结束链和结束整场 | 分别记录 `user_skipped`、`user_ended_branch`、`user_ended_interview`，不互相覆盖 |
| 评分失败 | 不写错题；有限重试后永久失败必须进入 `scoring_failed`，不能无限停留在 `scoring` |
| 删除原始简历 | 原始对象立即不可访问；证据摘要最多 200 字符，且不含原文、页码、文件名或可拼接上下文 |
| 删除后查看证据 | 只返回脱敏摘要、能力标签、题目关联和 `source_deleted` |
| 审计事件写入 | 仅允许白名单元数据；资源 ID 不可逆；不出现正文、回答、证据原文或凭据 |
| 审计记录超过 365 天 | 删除或不可逆匿名化，不能继续保留可关联的原始元数据 |
| P0 调用结束整场接口 | 不提供入口；若被直接请求，返回稳定的不支持或路由错误，不改变面试状态 |
| SSE 重连带旧事件 ID | 只从 PostgreSQL 补发后续事件，不重跑检索/模型、不重复扣费；Redis 清空后仍可恢复游标和终态 |
| 任意 URL 检索 | `422 unsupported_source` |
| 输出含内部 Prompt 或参考答案 | 默认 DTO 不允许，测试必须失败 |

## 10. 契约版本与兼容

- 路径版本使用 `/api/v1`，删除字段或改变语义需要新路径版本或显式弃用期。
- 新增可选字段可以保持 v1，但前端必须忽略未知字段。
- 枚举新增值需要客户端兼容策略；公开枚举变更必须进入需求/接口评审。
- 每次行为变化更新本文件版本、需求追踪和测试用例。

## 11. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-17 | 建立认证、简历、问答、面试、报告、隐私和审计接口契约 |
| v0.2 | 2026-10-17 | 补充 `report_not_ready`、`unsupported_source` 和 `feedback_locked` 稳定错误码 |
| v0.3 | 2026-10-17 | 按 DR-01、DR-02 冻结登录、退出、会话、密码重置和回答提交公开响应；补充认证安全测试矩阵 |
| v0.4 | 2026-10-17 | 将注册统一为中性 `202` 且不签发会话，消除注册响应与防账号枚举之间的冲突；明确登录为唯一会话签发入口 |
| v0.5 | 2026-10-17 | 按 DR-03 至 DR-06 冻结中性进度字段、P0 结束追问、P1 整场结束边界、删除后证据 DTO 和最小审计保留规则，并补充契约测试矩阵 |
| v0.6 | 2026-10-17 | 接受 ADR-0003、ADR-0006、ADR-0007、ADR-0008；冻结数据库时钟截止、持久 SSE 游标、评分失败终态和 `incomplete_scoring` 报告语义 |
| v0.7 | 2026-10-17 | 落实 `DR-07` 方案 A：补充 `interview_session`/`interview_csrf`、`X-CSRF-Token`、`csrf_token_hash` 和 `{items, next_cursor}` 历史分页契约 |
| v0.8 | 2026-10-18 | 冻结账号数据删除、删除状态查询、30/90/365 天保留清理和 `ops_metrics_token` 运维指标契约 |
