# Android 发布接入设计

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.1 |
| 文档状态 | `accepted`，按修订方案实现 |
| 更新日期 | 2026-10-23 |
| 实现修订 | 原设计选择原生 `WebView`；实际采用 Capacitor 8 壳 |

## 目标与范围

为现有 React Web 应用增加可安装的 Android 客户端，在 `https://it.rainstone.top`
同源生产站点上加载完整功能；交付可复现的 debug APK、签名 release APK/AAB、
GitHub Actions 构建与 tag Release 流程，以及中文构建、签名、安装和发布文档。

本设计不修改 Web 业务行为，不引入离线 Web 副本，不提交签名私钥或密码。Google Play
Console 提交、商店审核与生产签名密钥生成只能在受控账户中由人工完成。

## 架构决策

原设计选择稳定的 Android 原生 `WebView` 壳，而不是 Capacitor；实施阶段为复用现有
Web 构建链、导航和文件选择能力，改为 Capacitor 8 壳。应用仍只加载
`https://it.rainstone.top`，不引入离线 Web 副本。当前实现由 Capacitor 与原生配置共同负责：

- 只加载 `https://it.rainstone.top`；拒绝非 HTTPS 页面、非应用域名和外部 scheme。
- 保留默认 CookieManager，允许 WebView 持久化 HttpOnly 会话 Cookie 与可读 CSRF Cookie。
- 将 Web `input[type=file]` 交给系统文件选择器，支持单文件和多文件，拒绝来自任意
  `content://` URI 的持久权限泄漏。
- 将应用域名内的链接留在 WebView；其他 HTTP(S) 链接交给系统浏览器。
- 处理 `https://it.rainstone.top/...` 深链接：站点内路径直接导航，非站点路径拒绝。
- 使用 `WebViewAssetLoader`？不采用：资产加载器会制造第二个源，破坏 Cookie/CSRF 同源边界。

本次实施修订的原因是：Capacitor 8 提供可维护的 WebView 生命周期、文件选择和构建集成，
同时保留同源 HTTPS 加载、默认 Cookie 语义和 App Link。代价是增加 `@capacitor/android`
依赖和 Gradle 同步步骤；安全边界仍由应用域名 allowlist、HTTPS-only 清单、CSRF 和
签发 Cookie 的浏览器语义保证。当前实现与验收以 [Android 发布](../../android-release.md)
和 `tests/test_android_release_assets.py` 为准。

站点由后端和 Nginx 共同提供 SPA fallback，因此 `/workspace`、`/history`、
`/documents` 等深链接不需要额外 Web 路由改动。生产 Nginx 已把 `/api/*` 与 Web 放在同一
HTTPS 源，登录写请求继续发送 `X-CSRF-Token`，Credentials 保持 `include`。

## Android 工程

| 项目 | 值 |
| --- | --- |
| 显示名称 | 技术面试 |
| application ID | `top.rainstone.technicalinterviewagent` |
| 版本 | `versionName=0.1.0`、`versionCode=1` |
| 最低 SDK | 26 |
| 编译/目标 SDK | 35 / 36（Capacitor 8 依赖要求 compileSdk 36） |
| 站点 | `https://it.rainstone.top` |
| 证书格式 | PKCS12，文件与环境变量都放在仓库外 |

工程提交 Gradle wrapper 和 wrapper 校验信息，依赖解析通过版本目录锁定。debug 构建使用
Android debug keystore；release 由 Gradle 读取 `ANDROID_KEYSTORE_PATH`、
`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD`。缺少任意一项时
release 构建必须以清晰错误失败，不能退回 debug 签名。

原生清单禁止明文流量，启用 `INTERNET`，导出启动 Activity 并声明 HTTPS App Link。
启动页使用系统 SplashScreen API 和应用图标。图标、启动背景从现有品牌资源派生，不引入
新视觉体系。

## 构建与发布

本地命令：

```bash
cd android
./gradlew assembleDebug
./gradlew testDebugUnitTest
./gradlew bundleRelease assembleRelease
```

CI 在 PR/push 时无条件构建 debug APK 并运行单元测试。release 构建仅在签名 Secrets 齐全时
执行，避免 empty 环境变量生成未签名或被误认为可发布的 AAB。tag `v*` 触发完整 release
构建后创建 GitHub Release 并上传 APK、AAB、SHA-256 文件。签名缺失时 tag 工作流失败，
不会发布不可验证的产物。

## 测试策略

先写 Python 发布资产契约测试，验证包名、站点 URL、HTTPS-only 清单、Cookie/文件选择器/
深链接代码、签名模板、Gradle 版本和 Actions 触发条件。再写 Android JVM 单元测试验证
URL 策略和文件选择 MIME/多选策略。构建集成验证使用 Gradle 编译和 `aapt2`/`apkanalyzer`
检查清单与包名；签名状态用 `apksigner verify` 确认。

测试不会伪造生产签名成功：本机签名使用临时测试 keystore，产物明确标注测试签名；生产
签名密钥只由用户或 GitHub Secrets 提供。

## 错误处理与安全

- 拒绝 `http://`、非站点 host、非允许 scheme 的外部导航。
- 文件读取失败回传空选择结果，不抛出原生栈。
- 网络错误显示可重试错误页，恢复后继续原导航。
- 不启用 JavaScript bridge，不暴露本地文件访问，不弱化 WebView TLS。
- release 签名变量只从环境读取；仓库保存 `.example` 模板和 `.gitignore` 规则。
- CI 先做 secret scan 和资产契约测试，再构建；Release 权限最小化为 `contents: write`。

## 文档与验收

更新 `docs/android-release.md`。文档覆盖本地 debug 安装、临时/生产 keystore 创建、
GitHub Secrets 名称、tag 发布、版本号同步、产物校验及 Google Play Console 的人工步骤。

验收证据必须包含：

- 完整 pytest、ruff、mypy、前端测试/构建和 Gradle 单元测试。
- 可安装 debug APK 与签名 release APK/AAB 的绝对路径、版本号、签名状态、SHA-256。
- GitHub Actions 成功结果、PR 合并和 GitHub Release 链接。
- 未能自动完成的 Google Play 商店提交、审核与正式签名密钥生成步骤。

## 已知限制

- Android WebView 使用系统 Chromium 版本，极旧设备可能无法支持全部现代 CSS；最低 SDK
  26 与 CI 的 API 35 构建只证明编译兼容，不能替代真机矩阵。
- 用户手动粘贴的密码重置链接如果指向应用域名，会由 App Link 唤起；如果邮件客户端不支持
  App Link，链接仍会在浏览器打开，Web 行为不变。
- Google Play 要求 AAB、隐私表单、内容分级、签名密钥和商店素材，这些账户级步骤无法由
  代码仓库自动提交。

## 实现状态

Capacitor 8 Android 工程、debug/release 构建、签名变量模板、GitHub Actions 和资产契约
测试已经落地。Google Play Console 提交仍需由账号持有人在受控环境中完成。
