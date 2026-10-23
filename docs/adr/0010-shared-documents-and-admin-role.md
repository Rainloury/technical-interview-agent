# ADR-0010：共享资料采用独立资源与管理员角色

| 项目 | 内容 |
| --- | --- |
| 状态 | `accepted` |
| 审批日期 | 2026-10-22 |
| 关联 | DR-09、ADR-0009 |

## 背景

个人资料已经按 `owner_user_id` 隔离，适合保存用户自己的笔记，但不能表达由管理员维护、
所有账号共同使用的资料。把共享资料塞入 `user_documents` 会迫使检索逻辑区分同一张表内
的不同可见范围，并容易让“管理员”误以为能读取他人的个人资料。

## 决策

- `users.role` 只允许 `user` 和 `admin`，默认 `user`。
- 共享资料使用独立 `shared_documents` 和 `shared_document_chunks` 表。
- 共享资料只能由管理员上传和删除；所有 active 登录用户可列表、详情和检索。
- 个人资料仍只属于 owner，管理员也不能读取、修改或删除他人的个人资料。
- 共享证据使用 `qa_evidence.shared_document_chunk_id` 和
  `source_kind=shared_document`。
- 共享资料删除立即改变可见状态并标记历史证据为 `source_deleted`，异步清除对象和分块。
- 管理员账号删除不级联删除共享资料，创建者外键置空。
- 首个管理员通过 CLI `technical-interview-agent set-role` 任命，不开放注册时选角色。

## 后果

- 查询和索引需要区分 `user_document` 与 `shared_document` 资源类型。
- 前端需要按服务端会话中的角色隐藏写控件，但服务端仍必须独立鉴权。
- 共享资料不参与个人 90 天保留清理，管理员需显式删除。
- 角色变更和共享写操作产生最小审计事件。

## 替代方案

1. 在 `user_documents` 内增加可见范围字段：复用一张表，但会让 owner 过滤、管理员边界和检索条件纠缠，已不采用。
2. 复制一份共享资料到每个用户：读取简单，但对象、分块和删除状态会成倍增长，已不采用。
3. 允许管理员读取所有个人资料：便于集中维护，但违反严格 owner 隔离，已不采用。

## 验证

- `tests/test_shared_documents_api.py` 验证管理员与普通用户的读写边界。
- `tests/test_rag_retrieval.py` 验证个人资料、共享资料与已删除资料的检索范围。
- `tests/test_document_worker.py` 验证共享资料索引、删除和账号删除后的创建者外置空。
- `tests/test_database_constraints.py` 验证角色值域、共享资料约束和证据来源。
