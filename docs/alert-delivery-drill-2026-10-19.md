# 告警接入与通知演练记录

| 项目 | 结果 |
| --- | --- |
| 演练日期 | 2026-10-19 |
| 演练状态 | `passed` |
| 执行环境 | 本地隔离 PostgreSQL 16、Redis、API 和真实 HTTP webhook 接收器 |
| 数据库迁移头 | `7e2b4c6d8f10` |
| 通知协议 | HTTP POST JSON，`Authorization: Bearer <token>`，2xx 视为送达 |
| 演练接收器 | `http://127.0.0.1:58999/hook` |

> 本文只记录告警码、送达状态、HTTP 状态和聚合计数，不记录数据库密码、真实账号、简历或面试正文。

## 1. 告警规则

生产巡检命令：

```bash
technical-interview-agent alerts
```

规则：

| 告警码 | 触发条件 |
| --- | --- |
| `ready_failed` | `/health/ready` 返回非 2xx 或连接失败 |
| `dead_letter` | 存在任意 `async_jobs.state='dead_letter'` |
| `scoring_failed` | 存在 `interview_turns.state='scoring_failed'` |
| `deletion_failed` | 存在 `data_deletion_requests.state='failed'` |
| `worker_heartbeat_stale` | Worker 健康文件缺失或超过配置时限未更新 |

每次发送都会写入 `alert_deliveries`，记录告警码、严重级别、观察计数、消息、送达状态、HTTP 状态和错误摘要。生产 Compose 提供一次性 `alerts` 服务，`restart: "no"`，由外部调度器周期执行。

当前巡检不做跨轮次静默：同一异常持续存在时，每轮都会发送并写入新记录。生产调度窗口和通知平台的静默、聚合与升级策略负责减少重复打扰；数据库记录不应被删除。

## 2. 演练步骤与结果

### 2.1 基线

隔离数据库迁移到 `7e2b4c6d8f10`，API 以 `staging` 配置启动，`/health/ready` 返回 `ok`，PostgreSQL 和 Redis 均为 `ok`。webhook 接收器验证 Bearer token 和 JSON Content-Type。

### 2.2 五类告警

| 告警码 | 触发方式 | CLI 结果 | 接收器结果 |
| --- | --- | --- | --- |
| `ready_failed` | 临时停止 Redis 后执行巡检 | `delivered`，HTTP `204` | 收到 1 条，HTTP `204` |
| `dead_letter` | 插入 1 条 `dead_letter` 任务 | `delivered`，HTTP `204` | 收到 1 条，HTTP `204` |
| `scoring_failed` | 插入 1 条 `scoring_failed` 面试轮次 | `delivered`，HTTP `204` | 收到 1 条，HTTP `204` |
| `deletion_failed` | 插入 1 条 `failed` 删除请求 | `delivered`，HTTP `204` | 收到 1 条，HTTP `204` |
| `worker_heartbeat_stale` | 使用超过阈值未更新的健康文件 | `delivered`，HTTP `204` | 收到 1 条，HTTP `204` |

数据库聚合：

```text
alert_deliveries: 5
status=delivered: 5
```

接收器聚合：

```text
total: 5
dead_letter: 1
deletion_failed: 1
ready_failed: 1
scoring_failed: 1
worker_heartbeat_stale: 1
```

所有接收记录均包含 `schema_version=1`、`alert_code`、`severity=critical`、`environment=staging`、`observed_count`、`message` 和 `observed_at`，且 Bearer token 与演练配置一致。

## 3. 结论与限制

本次演练确认：五类告警均能真实通过 HTTP webhook 送达，接收器收到正确告警内容，数据库保存了对应的 `delivered` 记录，`ready_failed` 能反映 Redis 不可用导致的 `/health/ready` 降级。

限制：

- 使用本地 HTTP 接收器，不是生产 Slack、飞书、钉钉或企业告警网关；生产替换 `ALERT_WEBHOOK_URL` 和 token 后仍需做一次渠道验收。
- 演练使用临时测试数据和隔离数据库，不代表真实流量、跨网络延迟或通知平台限流下的行为。
- 生产需由外部调度器按约定周期执行 `technical-interview-agent alerts`，当前 Compose 只提供一次性执行服务。

## 4. 证据文件

临时证据位于 `/private/tmp/technical-interview-agent-alert-drill/`：

- `received-webhooks.jsonl`
- `ready-alert-cli.txt`
- `database-alerts-cli.txt`
- `api.env`（含演练临时值，禁止提交）

演练结束后应删除临时 API、PostgreSQL、Redis 容器和临时配置文件。

## 5. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-19 | 完成五类告警的隔离 webhook 送达演练；`alert_deliveries` 记录 5/5 delivered，接收器收到 5/5，包含 `ready_failed`、`dead_letter`、`scoring_failed`、`deletion_failed` 和 `worker_heartbeat_stale` |
