# ADR-0012：复习分页统一为不透明游标并保留明文兼容期

| 项目 | 内容 |
| --- | --- |
| 状态 | `accepted` |
| 日期 | 2026-11-09 |
| 关联 | ADR-0002、ADR-0011 |
| 影响 | 错题、薄弱点列表接口、service 层分页公共模块 |

## 背景

`wrong-questions` 与 `weak-points` 列表使用 `timestamp|uuid` 明文游标
（`app/services/interviews.py` 的 `decode_review_cursor` / `_review_cursor`）。客户端可自行构造
任意时间戳与 UUID，游标不是不透明数据；而历史、私有资料与共享资料已统一使用
`app/services/_pagination.py` 的 base64+JSON 不透明游标。三套游标中的明文实现既造成重复，
也让「游标是服务端签发的稳定位置」这一契约无法成立。

## 决策

- 复习列表新发出的 `next_cursor` 改为与 `_pagination` 一致的不透明 `created_at + id` 格式。
- 在一个兼容期内，`decode_review_cursor` 同时接受不透明游标与旧明文 `timestamp|uuid`；
  旧格式只用于已发出客户端页面的后续翻页，不再生成。
- 兼容期结束后（下一 major 版本或明确公告日期）删除明文解析分支，并更新接口契约文档。
- 拒绝无时区时间戳、非法 UUID 和畸形载荷时继续返回 `400 invalid_request / 分页游标不合法`。
- `_cursor_condition` 复用 `_pagination.cursor_condition`，不再保留第三套比较表达式。

## 替代方案

1. 直接删除明文解析：契约最干净，但会立即使已打开页面携带的旧游标失效，属于破坏性变更。
2. 对明文游标加 HMAC 签名：同样不透明，但引入密钥轮换与额外验证逻辑，对当前分页场景过重。
3. 维持明文、只抽取公共函数：改动最小，但保留可伪造游标和三套实现分叉。

## 后果

- 新旧客户端在一个兼容期内都能翻页；服务端只签发不透明游标。
- `interviews.py` 不再拥有独立的游标编解码与比较逻辑。
- 兼容期结束前需要保留旧格式解析分支及其测试，不能提前当作死代码删除。

## 影响文件

- `app/services/interviews.py`
- `app/services/_pagination.py`
- `docs/api-contract.md`、`docs/technical-design.md`
- `tests/test_interview_api.py`、`tests/test_service_common.py`

## 验证

- 新游标不可被客户端直接读出时间戳与 UUID，且往返解码一致。
- 旧明文游标在兼容期内仍返回同一页的后续数据。
- 无时区、非法 UUID、畸形载荷统一返回 `400 invalid_request`。
- `RUN_INTEGRATION=1 uv run pytest -q`、`uv run pytest evals -q`、ruff 与 mypy 通过。

## 审批

项目负责人于 2026-11-09 确认按推荐方向执行；本 ADR 承接第 3 期「对外行为变更需补 ADR」的要求。
