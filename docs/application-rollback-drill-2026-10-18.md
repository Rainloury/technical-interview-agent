# 应用回滚演练记录

| 项目 | 结果 |
| --- | --- |
| 演练日期 | 2026-10-18 |
| 演练状态 | `passed` |
| 执行环境 | 本地 Docker 预发布编排；独立 PostgreSQL volume、独立 Redis 和独立 Compose 项目 |
| 回滚版本 | `7b9ed7a90c9897ecada6f63affd8869bb10dcb37` |
| 当前版本 | `55a1053da091fc77b6d3396beb210b9104dafbbb` |
| 回滚方向 | API + Worker 同时从当前版本切到上一已验证版本 |
| 数据库迁移头 | 回滚前后均为 `3b7e1c9d4a20` |

> 本次演练只记录版本、时间、聚合状态和测试任务 ID，不记录数据库密码、真实账号或业务正文。

## 1. 版本与镜像

| 项目 | 回滚版本 | 当前版本 |
| --- | --- | --- |
| Git SHA | `7b9ed7a` | `55a1053` |
| 镜像 | `technical-interview-agent:rollback-7b9ed7a` | `technical-interview-agent:rollback-55a1053` |
| 镜像 ID | `sha256:19c4e94a49f64b7d01eef92695b9dd8b90c6f84b3113f94823ac515a6b773e35` | `sha256:d86e767e523ae1213bd1b173678f1ebd7318f98ba16cd1faa795f32e35789091` |

`git diff --name-status 7b9ed7a 55a1053 -- app migrations requirements.txt pyproject.toml Dockerfile` 无输出，说明这两个 SHA 在本演练涉及的应用、迁移和依赖范围内没有差异；本次切换仍是真实的镜像标签和容器生命周期回滚，但不应表述为源码行为差异回归。

## 2. 时间线

所有时间均为 UTC。

| 事件 | 时间 |
| --- | --- |
| 回滚开始 | `2026-10-18T15:44:40Z` |
| 基线 API / Worker started | `2026-10-18T15:44:43Z` |
| 基线 API / Worker healthy | `2026-10-18T15:44:43Z` 启动后完成探针 |
| 租约测试任务完成 | `2026-10-18T15:45:14Z` |
| 回滚窗口结束 | `2026-10-18T15:45:22Z` |
| 当前版本重新启动 | `2026-10-18T15:45:25Z` |
| 当前版本恢复完成 | `2026-10-18T15:45:31Z` |

回滚从开始到基线容器 healthy 约 3 秒；从前一版本开始切回当前版本到 API/Worker healthy 约 6 秒。上述耗时只代表本次本地隔离环境，不替代生产 RTO 承诺。

## 3. 健康与数据库兼容

| 检查项 | 回滚后基线版本 | 恢复当前版本 |
| --- | --- | --- |
| `GET /health/live` | 未单独抓取 | 未单独抓取 |
| `GET /health/ready` | `ok`；PostgreSQL、Redis 均为 `ok` | `ok`；PostgreSQL、Redis 均为 `ok` |
| API 容器健康 | `healthy` | `healthy` |
| Worker 容器健康 | `healthy`，心跳状态 `running` | `healthy` |
| `alembic_version.version_num` | `3b7e1c9d4a20` | `3b7e1c9d4a20` |

回滚期间没有执行 `alembic downgrade`，保留当前数据库结构，按向前兼容策略运行上一版本应用。

## 4. 租约接管结果

在当前版本完成迁移后，先停止当前 Worker，插入一条 `queued` 的 `delete_data` 测试任务，再启动基线 Worker。任务使用了本地隔离环境中的测试 UUID 和临时对象记录。

| 阶段 | `state` | `fencing_token` | `attempt_count` | `error_code` |
| --- | --- | ---: | ---: | --- |
| 回滚前 | `queued` | 0 | 0 | - |
| 基线 Worker 接管后 | `succeeded` | 1 | 1 | - |

基线 Worker 领取后递增 fencing token，完成租约写入；关联的 `resume_files` 记录状态变为 `deleted`，证明使用当前 schema 的队列任务可以在上一版本 Worker 上完成。

另外验证了两种兼容路径：

- 基线 Worker 遇到当前 schema 中已存在的 `password_reset_delivery` 任务时，测试 token 不存在，按幂等路径成功结束，结果为 `succeeded`，fencing token 为 1。
- 当前版本恢复后再次领取旧格式 `delete_data` 任务，结果为 `succeeded`，fencing token 为 1，证明旧任务类型没有因新版本部署而退化。

## 5. 结论与限制

本次演练通过：上一已验证版本可以在保留当前 `3b7e1c9d4a20` 数据库结构的前提下启动 API 和 Worker，健康检查通过，Worker 能接管并完成租约任务；随后当前版本可以恢复启动并保持健康。

限制：

- 使用本地 Docker 和临时密钥，不是生产网络、生产数据库或真实灾备环境。
- 镜像未推送至生产镜像仓库；生产回滚仍须使用同一不可变镜像摘要或已发布镜像 tag。
- 未执行真实用户流量回放、连接池压力、跨可用区网络故障和长时间观察。
- 应用与 Worker 的回滚窗口约 3 到 6 秒仅是本次本地环境数据，不能作为生产 SLA。

## 6. 证据文件

本次临时证据位于 `/private/tmp/technical-interview-agent-rollback-drill/`：

- `compose.yaml`
- `staging.env`（仅本地临时测试值，禁止提交）
- `current-ready.json`
- `seed-before-rollback.txt`
- `timestamp.txt`
- `lease-handoff-result.txt`
- `unsupported-job-result.txt`
- `forward-result.txt`

演练结束后应清理临时 Compose 项目、volume、镜像和环境文件。

## 7. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-18 | 完成 API + Worker 从 `55a1053` 回滚到 `7b9ed7a` 的隔离演练；验证健康检查、当前 schema 保留、Worker 租约接管和恢复当前版本 |
