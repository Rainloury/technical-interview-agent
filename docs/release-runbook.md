# 发布与回滚运行手册

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v0.8 |
| 文档状态 | 发布候选；运行手册已建立，发布批准与上线执行待完成 |
| 更新日期 | 2026-10-18 |
| 发布基线 | `7b9ed7a` |
| 迁移头 | `3b7e1c9d4a20` |

> 本手册区分“已验证”和“上线前必须补齐”。未关闭的阻断项不得通过口头豁免进入生产。

## 1. 当前发布事实

| 项目 | 当前状态 | 证据或限制 |
| --- | --- | --- |
| 代码质量 | 通过 | 最终验证 run `39136496514` 的 `quality` 与 `container` job 成功 |
| WebKit 兼容 | 通过 | 最终验证 run `39136496514` 的 WebKit Desktop Safari + iPhone 13 实跑 `14 passed`（1.7 min） |
| 生产邮件 | 部分验证 | DirectMail `smtpdm.aliyun.com:465` + SSL 已通过 TLS、登录和 SMTP 接受 |
| 生产对象存储 | 通过 | 阿里云 OSS 私有桶 PUT/GET/DELETE 已通过 |
| 生产配置 fail-fast | 本次新增 | `staging` / `production` 启动时校验 LLM、SMTP、OSS、HTTPS 和 Cookie/CORS 安全项 |
| API 启动 | 已验证开发流程 | `uv run uvicorn app.main:app` |
| 生产 Worker 入口 | 已提供 | `technical-interview-agent worker`；具备配置 fail-fast、信号停机、并发上限、运行时限和资源清理 |
| 容器镜像与生产编排 | 已提供 | 非 root 生产镜像、独立 migrate/API/Worker Compose、健康检查、只读根文件系统和 CI 镜像构建门禁 |
| 备份恢复演练 | 未执行 | 必须在上线前完成并留存结果 |
| 密码重置投递 | 已提供 | 请求事务只保存加密投递密文和 `password_reset_delivery` 任务；Worker 异步发送、有限重试，终态失败清除密文 |

## 2. 上线阻断项

以下任一未关闭，Go/No-Go 结论必须为 `NO-GO`：

1. **备份恢复**：至少完成一次 PostgreSQL 从备份恢复到独立实例的演练，并验证迁移头和关键表。
2. **回滚演练**：在预发布环境执行上一应用版本回滚，验证数据库兼容策略和健康检查。
3. **监控告警**：为 `/health/ready`、`dead_letter`、`scoring_failed`、删除失败、Worker 心跳和 LLM 成本配置可通知的告警。
4. **发布审批**：项目负责人明确批准灰度范围、观察窗口、回滚负责人和 No-Go 阈值。

## 3. 发布前配置

### 3.1 必填密钥

密钥只通过部署平台的密钥管理或环境变量注入，不写入仓库、镜像、命令行参数或日志。

| 类别 | 必须配置 |
| --- | --- |
| 运行环境 | `APP_ENV=production`、`APP_DEBUG=false` |
| 数据库 | `DATABASE_URL`、连接池参数 |
| Redis | `REDIS_URL` |
| LLM | `LLM_API_KEY`、`LLM_FAST_MODEL`、`LLM_DEFAULT_MODEL`、`LLM_REASONING_MODEL` |
| DirectMail | `SMTP_HOST=smtpdm.aliyun.com`、`SMTP_PORT=465`、`SMTP_SECURITY=ssl`、账号、密码、发件地址 |
| OSS | `RESUME_STORAGE_BACKEND=oss`、Endpoint、私有 Bucket、Access Key ID、Secret |
| 会话 | `COOKIE_SECURE=true`、生产域名对应 Cookie 配置 |
| 来源 | `APP_ALLOWED_ORIGINS`、`CSRF_ALLOWED_ORIGINS` 仅允许生产 HTTPS 域名 |
| 重置链接 | `PASSWORD_RESET_BASE_URL` 使用生产 HTTPS 地址 |
| Worker | `WORKER_CONCURRENCY`、`WORKER_MAX_RUNTIME_SECONDS`、`WORKER_IDLE_SECONDS`、`WORKER_SHUTDOWN_GRACE_SECONDS` |
| 运维 | `OPS_METRICS_TOKEN` 使用高熵随机值 |
| 加密 | `DATA_ENCRYPTION_KEY` 使用 32 字节随机密钥的 URL-safe Base64 编码；不要轮换后直接丢弃旧密钥，否则在途重置邮件将无法解密 |

### 3.2 配置核验

```bash
uv run python - <<'PY'
from app.config import get_settings

settings = get_settings()
settings.validate_deployment()
print(
    {
        "environment": settings.app_env,
        "storage": settings.resume_storage_backend,
        "smtp_host": settings.smtp_host,
        "smtp_port": settings.smtp_port,
        "secure_cookie": settings.cookie_secure,
        "origins": settings.app_allowed_origins,
    }
)
PY
```

预期结果：进程正常退出；缺失或危险配置会以非零状态退出。不要输出密钥或完整数据库 URL。

### 3.3 OSS 复核

- Bucket 为私有读写，禁止公共读和公共写。
- 应用身份只拥有所需前缀的对象读写删除权限，不使用账号级全权限密钥。
- 启用服务端加密；按合规要求选择 OSS 托管密钥或 KMS。
- 对象生命周期与 30/90 天业务保留规则对齐；版本控制和删除保护不能延长隐私数据寿命。
- 日志与对象元数据不包含简历正文。

### 3.4 邮件 DNS 与投递复核

- DirectMail 发信域名完成所有权验证。
- SPF、MX、DKIM 记录按 DirectMail 控制台给出的值配置并完成验证。
- 使用 `dig` 或 `nslookup` 核验记录传播，再发送一封真实测试邮件。
- 收件人必须人工确认到达，并核对 SPF、DKIM 和 DMARC 结果。
- 不要为了通过 SPF 验证设置过宽的 `+all`；SPF 的 `all` 限定应与发信范围一致。

## 4. 数据库迁移

### 4.1 迁移前备份

```bash
pg_dump --format=custom --no-owner --no-acl \
  --file="release-$(date -u +%Y%m%dT%H%M%SZ).dump" \
  "$DATABASE_URL_SYNC"
```

将备份写入独立于主库的加密存储，记录文件名、校验和、操作者和 UTC 时间。禁止在日志或发布单中粘贴数据库密码。

### 4.2 迁移

```bash
uv run alembic current
uv run alembic upgrade head
uv run alembic current
```

预期迁移头为 `3b7e1c9d4a20`。迁移完成后再启动新应用版本和 Worker。

### 4.3 恢复

在独立恢复环境执行：

```bash
createdb interview_restore
pg_restore --clean --if-exists --no-owner --no-acl \
  --dbname=interview_restore release-YYYYMMDDTHHMMSSZ.dump
```

随后核验迁移头、用户数、任务数、最近审计时间和关键外键。恢复日志中只记录表名和聚合计数。

## 5. 启动与健康检查

当前 API 启动命令：

```bash
docker compose -f deploy/production.compose.yaml --env-file <deployment.env> up -d migrate
docker compose -f deploy/production.compose.yaml --env-file <deployment.env> up -d api
```

当前 Worker 启动命令：

```bash
docker compose -f deploy/production.compose.yaml --env-file <deployment.env> up -d worker
```

禁止使用 `scripts/e2e_resume_worker.py` 作为生产 Worker。部署平台应在停止时先发送 `SIGTERM`，等待 Worker 退出后再强制终止；`WORKER_CONCURRENCY` 必须与数据库连接池和任务吞吐一起评估。

生产镜像构建：

```bash
docker build --pull -t "$IMAGE_REPOSITORY:$IMAGE_TAG" .
docker push "$IMAGE_REPOSITORY:$IMAGE_TAG"
```

镜像以 UID/GID `10001` 的非 root 用户运行，根文件系统只读，`/tmp` 和 Worker 心跳目录使用受限 tmpfs。API 探针检查 `/health/ready`；Worker 探针检查 `/var/run/technical-interview-agent/worker-health.json` 的 `running` 状态和 30 秒内更新时间。

启动后检查：

```bash
curl --fail --silent --show-error https://<prod-domain>/health/live
curl --fail --silent --show-error https://<prod-domain>/health/ready
```

`/health/live` 只表示进程存活；`/health/ready` 必须同时返回 PostgreSQL 和 Redis 为 `ok`。ready 失败时不得接流量。

## 6. 灰度与观察

### 6.1 建议范围

- 首批只邀请 10 至 20 个已知账号或 5% 以内流量，API 和 Worker 使用同一发布 SHA。
- 先验证注册、登录、密码重置、简历上传处理、一轮问答和一场完整面试。
- 观察窗口至少覆盖一个完整面试时长加一个 Worker 重试周期。

### 6.2 必看指标

| 指标 | 来源 | No-Go 示例 |
| --- | --- | --- |
| API 存活与就绪 | `/health/live`、`/health/ready` | 连续 5 分钟 ready 失败 |
| 任务状态 | ops metrics `jobs_by_state` | `dead_letter` 持续增加 |
| 任务类型 | ops metrics `jobs_by_type` | 单一类型失败集中且无法重试 |
| 评分失败 | `interview_scoring_failed` | 出现非预期持续增长 |
| 面试分支终止 | ops metrics `interview_termination_reasons` | 异常原因比例显著偏离基线 |
| 删除任务 | `deletion_requests_by_state` | 出现持续 `failed` |
| 审计到期 | `expired_audit_events` | 持续堆积说明清理未运行 |
| LLM 成本 | trace 与供应商账单 | 超出整场 P95 ¥3.00 或预算异常 |
| 邮件送达 | DirectMail 投递记录与人工抽样 | 认证失败、退信率异常或重置邮件未达 |

运维聚合接口：`GET /api/v1/ops/metrics`，使用 `Authorization: Bearer <OPS_METRICS_TOKEN>`。不得在浏览器、日志或截图里暴露该令牌。

## 7. Go/No-Go

进入发布前逐项签字：

- [ ] 发布 SHA 已冻结，质量与 WebKit CI 对同一 SHA 全绿。
- [ ] 生产配置核验通过，密钥未进入仓库或构建产物。
- [ ] 镜像和编排已补齐，CI 构建门禁通过，API 与 Worker 使用同一发布 SHA。
- [ ] 数据库备份完成，恢复演练通过。
- [ ] 上一版本回滚演练通过，数据库向前兼容策略明确。
- [ ] `/health/live` 与 `/health/ready` 通过，告警可实际送达。
- [ ] DirectMail DNS 验证和真实投递人工确认通过。
- [ ] OSS 私有、加密、权限与生命周期复核通过。
- [ ] 密码重置投递由持久 Worker 任务完成，SMTP 失败不影响中性响应；待发布演练复核。
- [ ] 灰度范围、观察窗口、回滚负责人和 No-Go 阈值已批准。

## 8. 回滚

### 8.1 应用回滚

1. 停止继续扩大灰度，保留数据库和日志供排查。
2. 将 API 和 Worker 同时切回上一已验证 SHA。
3. 等待 `/health/ready` 恢复，确认任务租约由新实例接管。
4. 检查 `dead_letter`、`scoring_failed`、删除失败和重复处理情况。
5. 记录回滚开始/结束 UTC 时间、影响范围、失败版本和观察结果。

### 8.2 数据库策略

默认采用“应用可回滚、数据库向前兼容”的扩展/收缩迁移策略。不要直接 `alembic downgrade` 生产库，除非：

- 已确认无新版本写入的新字段/新枚举值；
- 已做独立备份并验证可恢复；
- 迁移作者和发布负责人书面批准；
- 降级命令、影响表和预计锁时间已写入变更单。

## 9. 已知限制与负责人

| 限制 | 影响 | 当前处理 | 负责人 | 目标日期 |
| --- | --- | --- | --- | --- |
| 备份恢复与回滚未演练 | 故障恢复证据不足 | 上线阻断 | 待指定 | 上线前 |

## 10. 版本记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-10-18 | 建立发布与回滚运行手册；记录候选基线、生产依赖事实、上线阻断项、配置核验、迁移备份恢复、灰度观察、Go/No-Go 与回滚流程 |
| v0.2 | 2026-10-18 | 冻结发布基线 `e5e2073`；记录该 SHA 的 quality 与 WebKit CI 实跑结果 |
| v0.3 | 2026-10-18 | 将发布基线更新为 `f6fc0af`，记录该 SHA 的 quality 与 WebKit CI 全绿结果 |
| v0.4 | 2026-10-18 | 新增生产 Worker 命令、信号停机、并发与运行时限配置；关闭 Worker 入口阻断项，保留镜像编排、邮件异步投递、恢复回滚和告警阻断项 |
| v0.5 | 2026-10-18 | 新增非 root 生产镜像、独立 migrate/API/Worker Compose、Worker 心跳、只读容器和 CI 镜像构建门禁；关闭部署资产阻断项 |
| v0.6 | 2026-10-18 | 密码重置改为加密密文 + 持久任务异步投递；新增 `DATA_ENCRYPTION_KEY`、`password_reset_delivery` 任务、重试/死信和密文清理，关闭邮件同步阻断项 |
| v0.7 | 2026-10-18 | 发布基线推进至 `067f34e`；E2E 启动器同时拉起 API、确定性 Worker 和前端，异步重置投递已纳入 Chromium/WebKit 全链路验证 |
| v0.8 | 2026-10-18 | 发布基线推进至 `7b9ed7a`；修复 E2E 进程组清理与超时退出，最终验证 run `39136496514` 的 quality、container 与 WebKit 实跑 `14 passed` 全绿 |
