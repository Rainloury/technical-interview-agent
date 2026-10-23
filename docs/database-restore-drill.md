# 数据库备份恢复演练记录

| 项目 | 结果 |
| --- | --- |
| 演练日期 | 2026-10-18 |
| 演练状态 | `passed` |
| 执行环境 | 本地 Docker；源库与恢复库为独立容器 |
| 源实例 | `technical-interview-agent-postgres-1`，PostgreSQL 16.15 |
| 恢复实例 | `technical-interview-agent-restore-20261018T145010Z`，PostgreSQL 16.15 |
| 恢复端口 | `55433` |
| 恢复目标库 | `interview_restore` |
| 应用基线 | `7b9ed7a` |
| 迁移头 | `3b7e1c9d4a20` |

> 本文只记录聚合计数和校验结果，不包含数据库密码、账号、简历、问答或面试正文。

## 1. 备份

| 项目 | 结果 |
| --- | --- |
| UTC 时间 | 2026-10-18T14:50:10Z |
| 文件名 | `release-20261018T145010Z.dump` |
| 格式 | PostgreSQL custom |
| 文件大小 | 648670 bytes |
| SHA-256 | `9f75d1d84204386a19f8ba887a6917976823dcf2b7c9e1dd0a0a4946a306d39e` |
| 导出参数 | `--format=custom --no-owner --no-acl` |

备份暂存于 `/private/tmp/technical-interview-agent-db-restore/`，用于本次演练；生产备份仍需写入独立于主库的加密存储。

## 2. 恢复

在独立 PostgreSQL 16 容器中创建空库 `interview_restore`，从指定备份恢复：

```bash
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname=postgresql://<recovery-host>/interview_restore \
  release-20261018T145010Z.dump
```

结果：

- `pg_restore` 退出码为 `0`。
- 恢复日志 940 行，未发现 error、fatal、failed 或 warning。
- 恢复库通过 `BEGIN / INSERT / ROLLBACK` 可写性探针。
- 源库与恢复库 PostgreSQL 主版本一致，均为 16.15。

## 3. 结构与行数核对

恢复库包含：

- `public`：27 张表
- `osscheck_10a16921ccc041408c2b2f1a559fa2a8`：26 张测试残留表
- `osscheck_dabaa505fd384c14a21fe30e8eb22fbc`：26 张测试残留表

两个 `osscheck_*` schema 属于源库中的既有测试残留对象，本次整库备份一并恢复；业务核验以 `public` 为准。所有 schema 的表名与实际 `COUNT(*)` 均与源库一致。

| `public` 表 | 源库 | 恢复库 |
| --- | ---: | ---: |
| `alembic_version` | 1 | 1 |
| `async_jobs` | 358 | 358 |
| `audit_events` | 825 | 825 |
| `auth_sessions` | 353 | 353 |
| `data_deletion_requests` | 29 | 29 |
| `follow_up_chains` | 335 | 335 |
| `generated_questions` | 380 | 380 |
| `interview_operations` | 100 | 100 |
| `interview_reports` | 0 | 0 |
| `interview_turns` | 399 | 399 |
| `interviews` | 607 | 607 |
| `knowledge_source_sections` | 1 | 1 |
| `knowledge_source_versions` | 1 | 1 |
| `knowledge_sources` | 1 | 1 |
| `password_reset_tokens` | 42 | 42 |
| `qa_evidence` | 76 | 76 |
| `qa_requests` | 76 | 76 |
| `qa_stream_events` | 228 | 228 |
| `resume_analyses` | 38 | 38 |
| `resume_files` | 40 | 40 |
| `resume_tasks` | 40 | 40 |
| `resume_texts` | 40 | 40 |
| `scoring_attempts` | 64 | 64 |
| `users` | 269 | 269 |
| `weak_point_evidence` | 0 | 0 |
| `weak_points` | 0 | 0 |
| `wrong_questions` | 0 | 0 |

## 4. 外键与迁移头

| 检查项 | 孤立记录数 |
| --- | ---: |
| `auth_sessions.user_id -> users.id` | 0 |
| `async_jobs.owner_user_id -> users.id` | 0 |
| `resume_tasks.owner_user_id -> users.id` | 0 |
| `qa_requests.owner_user_id -> users.id` | 0 |
| `interviews.owner_user_id -> users.id` | 0 |

源库与恢复库的 `alembic_version.version_num` 均为 `3b7e1c9d4a20`。

## 5. 结论与限制

本次演练确认：指定 custom dump 可以成功恢复到独立 PostgreSQL 16 实例，迁移头正确，业务 schema 的表结构、全表行数和关键 owner 外键一致，恢复库可正常执行事务。

本次演练使用本地临时容器和明文临时目录，不等同于生产灾备验收。生产灾备存储复核、隔离网络恢复和回滚演练仍须关闭；生产上线前还须：

- 将备份保存到独立、加密、具备访问控制的存储；
- 在隔离网络或灾备环境执行恢复，并验证应用健康检查和 Worker 租约接管；
- 记录生产备份的保留周期、恢复 RPO/RTO、操作者和审批人；
- 演练完成后删除临时备份和恢复实例，避免敏感数据长期留在开发机。

## 6. 证据文件

本次临时证据位于 `/private/tmp/technical-interview-agent-db-restore/`：

- `release-20261018T145010Z.dump`
- `release-20261018T145010Z.dump.sha256`
- `pg_restore-20261018T145010Z.log`
- `table-counts-20261018T145010Z.txt`

临时证据和恢复容器需由执行者按第 5 节清理；不得把 dump 或完整恢复日志提交到仓库。

## 7. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-18 | 完成本地独立 PostgreSQL 恢复演练；验证迁移头、全表行数、关键外键、可写性和恢复日志，明确生产灾备仍需独立存储与网络环境 |
