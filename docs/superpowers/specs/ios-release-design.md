# iOS 发布接入设计

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 文档状态 | `accepted`，工程与预检已实现 |
| 更新日期 | 2026-10-23 |
| 需求依据 | 现有 Web 产品与 `DR-01` 至 `DR-09` 的已批准边界 |
| 关联文档 | [iOS 发布手册](../../ios-release.md)、[方案总览](../../solution-map.md) |

## 1. 目标与范围

为现有 React Web 应用提供可安装、可签名、可提交 App Store 的 iOS 客户端。客户端加载
`https://it.rainstone.top` 的同源生产站点，复用账号、资料、问答、模拟面试、报告和隐私能力。

首版只提供原生外壳、构建预检、签名准备和发布文档；不修改 Web 业务行为，不提供离线
Web 副本，不在仓库保存 Apple 私钥、Profile、App Store Connect API Key 或导出产物。

## 2. 架构决策

采用 UIKit 生命周期 + 原生 `WKWebView`，不使用 Capacitor、Cordova 或第三方 iOS 依赖。
应用只接受 HTTPS 和站点允许域名；同源加载保证 `Interview_session`、`interview_csrf`、
`X-CSRF-Token`、multipart 上传和 SSE 的浏览器语义不变。

不使用 `file://`、自定义 Origin 或打包静态资源；这些方式会破坏 Cookie、Origin/Referer
allowlist 和 SSE。原生层负责文件选择、外链、确认框、网络错误和可重试状态，不注入
业务 JavaScript bridge，不暴露本地文件系统。

## 3. 工程结构

```text
ios/
  Config/App.xcconfig
  Config/Signing.xcconfig.example
  TechnicalInterviewAgent/AppDelegate.swift
  TechnicalInterviewAgent/SceneDelegate.swift
  TechnicalInterviewAgent/AppConfig.swift
  TechnicalInterviewAgent/WebViewController.swift
  TechnicalInterviewAgent/Info.plist
  TechnicalInterviewAgent/Resources/PrivacyInfo.xcprivacy
  TechnicalInterviewAgent/Assets.xcassets/AppIcon.appiconset
  TechnicalInterviewAgent.xcodeproj
  ExportOptions.plist.example
```

候选 Bundle ID 为 `top.rainstone.technicalinterviewagent`，最低系统为 iOS 17.0。Bundle ID、
Team ID、版本号和站点地址集中在 `App.xcconfig`，不散落在 Swift 源码。

## 4. 签名与发布

- 本机仅在 `Signing.xcconfig` 或环境变量提供 Team ID；该文件不进入版本库。
- 归档需要有效 Apple Development 或 Distribution 身份和匹配的 Profile。
- `scripts/ios_release.py` 提供无签名预检、archive、release 三种模式；缺失签名材料时
  明确返回 `blocked`，不伪造签名或上传成功。
- `ExportOptions.plist.example` 使用 `app-store-connect` 和 automatic signing，不含凭据。
- TestFlight 上传、App Store Connect 元数据、审核提交和正式签名密钥由账号持有人完成。

## 5. 安全与隐私

- `NSAllowsArbitraryLoads=false`；只允许 HTTPS 与受控站点域名。
- 默认 `WKWebsiteDataStore` 保留同源 Cookie；不读取 HttpOnly Cookie。
- 文件选择使用系统 `UIDocumentPickerViewController`，只把用户选择的文件交给 Web 表单。
- 外部 HTTP(S) 链接使用系统浏览器，不把任意页面加载到应用 WebView。
- 不记录账号、文件内容、Token 或私钥；发布报告只记录签名是否可用和阻塞原因。
- `PrivacyInfo.xcprivacy` 声明不跟踪；接入统计、推送、崩溃收集或第三方 SDK 时必须更新。

## 6. 测试与验收

先写 Python 发布资产契约测试，验证共享 Scheme、Bundle ID、HTTPS-only、上传权限、
Cookie 数据存储、文件选择器、外链策略、隐私 Manifest 和 `.gitignore`。再运行 Web 生产
构建、无签名预检和 Xcode 可用时的模拟器/归档验证。

验收证据必须包含：

- `tests/test_ios_release_assets.py` 通过。
- `uv run python scripts/ios_release.py --mode preflight` 的脱敏报告。
- 完整 Xcode、签名身份、匹配 Profile 可用时，archive 成功。
- 真机或 TestFlight 至少完成登录、简历上传、资料上传、问答和模拟面试回归。
- App Store Connect App 记录、截图、隐私政策和审核材料齐全。

## 7. 已知限制与阻塞

- 当前环境无完整 Xcode、Simulator、有效签名身份和匹配 Profile，不能产出可提交 IPA。
- 当前没有 App Store Connect App 记录、API Key 和商店元数据。
- Apple 对网页封装类应用存在 4.2 最低功能要求风险；不得通过隐藏 WebView 或伪造内容规避审核。
- 未完成真机/TestFlight 回归前，只能声明工程与预检完成，不能声明可提交商店。

## 8. 审批与实现状态

方案沿用现有 Web 产品和已批准需求，不新增用户可见业务规则。工程结构、静态契约测试、
配置模板、隐私 Manifest 和无签名预检已实现。签名、TestFlight、商店提交和生产发布仍按
[iOS 发布手册](../../ios-release.md)与[方案总览](../../solution-map.md)跟踪。
