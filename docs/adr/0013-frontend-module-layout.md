# ADR-0013：前端模块布局与单向依赖

- 状态：`proposed`（已实现，待架构评审确认）
- 日期：2026-11-13
- 影响范围：`web/` 前端工程；不改变 HTTP API、页面路由、用户可见行为

## 背景

v0.1.0 发布后，`web/src` 约 13,700 行源码按技术层平铺：15 个页面与 12 个测试全部放在
`src/pages/`，`src/styles.css` 单文件 4,571 行（占源码 33%），`src/api/client.ts` 632 行同时
承担 fetch 封装、错误解析、SSE 协议实现与 30 多个端点定义，`src/api/types.ts` 419 行混合
全部业务域 DTO。`src/components/` 只有通用组件，域内展示组件全部内联在页面文件里。

由此产生散弹式修改：改一个 QA 需求要碰页面、`client.ts`、`types.ts`、`queryKeys.ts`、
`styles.css`、MSW handler 和 E2E spec 共 7 处。全仓 197 处相对 import 且没有路径别名，
任何目录调整都要改大量 `../`；`src/hooks/` 是空目录。

本 ADR 只固化前端源码布局，不改动后端分层（见 ADR-0001、ADR-0011）。

## 决策

### 1. 三层布局

```
web/src/
├── app/          应用装配：main、App 路由、queryClient、analytics、
│                 AppShell、NotFoundPage、styles.css 入口
├── features/     按业务域内聚：页面 + 共置测试 + 域内组件
│   └── auth|workspace|history|resumes|documents|qa|interviews|reviews/
├── shared/       无业务语义的复用能力，禁止知道上层存在
│   ├── api/      http / sse / endpoints / types / csrf / idempotency / queryKeys
│   ├── ui/       通用展示组件
│   ├── lib/      validation / format / errors / navigation / clearSession
│   ├── hooks/    cursorPageParams
│   └── styles/   base / controls / forms / shell / pages / qa / documents / interviews
└── test/         MSW server、render、fixtures、setup（保留在 src 内，见下）
```

依赖方向锁死为 `app → features → shared`：

- `shared/**` 不得 import `@/app/*` 或 `@/features/*`；
- `features/**` 不得 import `@/app/*`；
- 用 ESLint 核心规则 `no-restricted-imports` 固化，不引入新依赖。

落地时修掉两处既有反向引用：`AppShell` 依赖登录态，从 `shared/ui` 上移到 `app/`；
`clearSession()` 是纯函数，从 `queryClient.ts` 下沉到 `shared/lib/clearSession.ts`，
供 `app/queryClient.ts` 与 `features/auth/AuthProvider.tsx` 共同使用。

### 2. `@/` 路径别名

`tsconfig.json` 的 `paths` 与 `vite.config.ts` 的 `resolve.alias` 一致指向 `src/`；
`vitest.config.ts` 通过 `mergeConfig(viteConfig, ...)` 继承，避免三处漂移。
全仓本地模块引用统一用 `@/`，不再出现 `../` 跨目录引用。

### 3. 单文件拆分，但保留对外门面

- `styles.css` 按原有 8 个分节注释纯剪切为 `shared/styles/*.css`，入口按顺序 `@import`；
  构建产物 CSS 与拆分前**字节完全一致**（73,167 B）。
- `client.ts` 拆为 `http.ts`（request / ApiError / 超时 / parseError）、`sse.ts`
  （parseSseStream / 重连 / streamQa）、`endpoints/<域>.ts`（8 个域对象）；
  `client.ts` 保留 `api` 对象门面与 `ApiError`、`parseSseStream` 等重导出，
  19 处 `api.xxx` 调用点一行未改。
- `types.ts` 按域拆为 `types/*.ts`，`types.ts` 仅做 `export type *` 类型重导出；
  跨域引用（`interviews → reviews`、`workspace → auth`）用显式 `import type` 声明。

### 4. 明确不做的事

- **不加运行时 `index.ts` barrel**：会破坏按路由 `React.lazy` 代码分割，把整域模块拉回入口
  chunk。只允许纯类型 barrel。
- **不抽 `usePollingQuery`**：4 处 `refetchInterval` 判定条件完全不同（无限列表处理中、
  面试评分 900/2500ms 动态、简历终态、数据删除终态），统一只会得到"接受任意回调的壳"，
  无复用价值。仅抽取真正同质的 `cursorPageParams` 样板（3 处）。
- **不拆 `InterviewDetailPage` 的报告展示组件**：`InterviewResult` / `ReportTurn` 与
  6 个辅助函数及多个图标强耦合，机械搬运约 200 行，收益低于风险；该文件已在
  `features/interviews/` 域内，内聚目标已达成。
- **`src/test/` 不移出 `src`**：`vitest.config.ts` 的 `setupFiles` 与
  `tsconfig.build.json` 的 `exclude` 都依赖该路径，外移会让 `@/test` 别名失效，收益不抵成本。
- **不改历史文档路径**：ADR-0009、`docs/next-steps.md`、
  `docs/superpowers/plans/{shared-documents,user-rag}.md`、
  `docs/superpowers/specs/user-rag-design.md` 里的 `web/src/...` 是历史决策证据，保持原样，
  以本 ADR 的映射表为准。

## 新旧路径映射

| 旧路径 | 新路径 |
| --- | --- |
| `src/pages/<Page>.tsx` | `src/features/<域>/<Page>.tsx`（测试同步共置） |
| `src/pages/NotFoundPage.tsx` | `src/app/NotFoundPage.tsx` |
| `src/auth/*` | `src/features/auth/*` |
| `src/api/client.ts` | `src/shared/api/client.ts`（门面）+ `http.ts` + `sse.ts` + `endpoints/*` |
| `src/api/types.ts` | `src/shared/api/types.ts`（barrel）+ `types/*` |
| `src/api/{csrf,idempotency,queryKeys}.ts` | `src/shared/api/` 同名 |
| `src/components/*` | `src/shared/ui/*` |
| `src/components/AppShell.tsx` | `src/app/AppShell.tsx` |
| `src/utils/*Validation.ts` + `validation.ts` | `src/shared/lib/validation.ts`（4 合 1，导出名不变） |
| `src/utils/{errors,format,navigation}.ts` | `src/shared/lib/` 同名 |
| `src/hooks/`（空） | `src/shared/hooks/cursorPageParams.ts` |
| `src/styles.css` | `src/app/styles.css` + `src/shared/styles/*.css` |
| `src/{App,main,queryClient}.ts(x)` | `src/app/` 同名 |
| `src/analytics/gtm.ts` | `src/app/analytics.ts` |
| `src/test/*` | 不变 |

域归属：`auth`（登录/注册/找回/重置 + Provider 与路由守卫）、`workspace`、`history`、
`resumes`、`documents`（+ `DocumentRow.tsx`）、`qa`（+ `QaAnswerView.tsx`）、
`interviews`、`reviews`。

## 替代方案

1. **完整 Feature-Sliced Design**：端点、DTO、queryKey、MSW handler 全部下沉到域目录。
   内聚度更高，但要改 100+ 文件、破坏 5 份历史文档路径引用，且当前每个域最多 4 个页面，
   收益不足以覆盖回归风险。待某域增长到 3 个以上页面或团队规模扩大后再评估。
2. **只拆大文件、不动目录**：改动最小，但散弹式修改与相对路径问题仍在。
3. **引入 `vite-tsconfig-paths` 自动同步别名**：需新增依赖；本项目 `vite.config.ts` 与
   `vitest.config.ts` 已用 `mergeConfig` 做到单一来源，标准库 3 行即可解决，按依赖门槛不加。

## 后果

- 正向：改一个业务需求的触碰面收敛到 `features/<域>/`；单文件最大规模从 4,571 行降到
  1,580 行（样式）/ 725 行（页面）；共享能力有明确归属，分层违规由 lint 拦截。
- 负向：目录层级变深，新成员需要读本 ADR；5 份历史文档中的路径不再指向现址，
  需靠映射表翻译。
- 中性：`api` 对象仍是全端点门面，未做按域拆分的运行时隔离；入口 chunk 保持约 253 KB。

## 影响文件

`web/tsconfig.json`、`web/tsconfig.build.json`、`web/vite.config.ts`、
`web/vitest.config.ts`、`web/eslint.config.js`、`web/index.html`、`web/src/**`、
本 ADR、`docs/adr/README.md`、`docs/next-steps.md`、`CHANGELOG.md`。
`web/Dockerfile` 无需修改（`COPY src ./src` 覆盖新子目录）。

## 验证方式

- `npm run typecheck`、`npm run lint`（含新增分层规则，0 error / 0 warning）
- `npm test -- --run`：`17 files / 67 tests` 全过
- `npm run build`：入口 JS 约 253 KB / gzip 78.5 KB，15 个页面仍是独立 lazy chunk
- CSS 产物与拆分前字节完全一致（73,167 B，hash 未变）
- 分层规则生效检查：`npx eslint --print-config src/shared/ui/Feedback.tsx`
- 未跑：Playwright E2E（需完整后端栈 + PG/Redis）、Docker 构建与 `nginx -t`（本机无 Docker）
