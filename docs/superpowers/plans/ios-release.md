# iOS 发布接入实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或
> executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 交付可复现构建、可签名归档并可进入 TestFlight/App Store 流程的 iOS 原生
`WKWebView` 外壳。

**架构：** UIKit 生命周期 + 单站点 `WKWebView`，默认 Cookie 存储、系统文件选择器和
HTTPS-only 策略；Xcode 工程、配置模板、Python 预检脚本和脱敏发布证据共同组成交付。

**技术栈：** Swift、UIKit、WKWebView、Xcode 15+、iOS 17.0、Python 3.11+、pytest。

**规格：** `docs/superpowers/specs/ios-release-design.md`

## 全局约束

- Bundle ID 为 `top.rainstone.technicalinterviewagent`，站点为 `https://it.rainstone.top`。
- 最低 iOS 17.0；生产站点只允许 HTTPS，禁止任意 HTTP 或非站点 host。
- 仓库不得包含证书、Profile、`.p8`、`.p12`、`.ipa`、`.xcarchive` 或签名配置。
- 不改变 Web 业务行为、Cookie/CSRF 语义、上传和 SSE。
- 不改用 Capacitor、Cordova 或离线静态包。
- 所有发布脚本必须区分 `pass`、`blocked` 和失败，不得伪造签名或上传成功。
- 按仓库规则运行 ruff、mypy、pytest 和移动端资产契约；不引入不必要依赖。

## 审查重点

- 非 HTTPS 或非站点域名必须拒绝，而不是静默回退 HTTP。
- Web 文件选择、取消、读取失败和外链必须保持可恢复，不抛原生栈。
- `HttpOnly` Cookie 不得通过 JavaScript bridge 或日志暴露。
- 缺失 Xcode、签名身份、Profile 或 App Store Connect 材料时必须 `blocked`。
- 注销、重置密码、SSE 问答和资料上传在 WebView 中保持同源认证。

## 文件结构

### 已存在

- `ios/TechnicalInterviewAgent/AppConfig.swift`：站点和 HTTPS 校验。
- `ios/TechnicalInterviewAgent/WebViewController.swift`：WebView、Cookie、上传、外链和错误状态。
- `ios/TechnicalInterviewAgent.xcodeproj/`：Xcode 工程与共享 Scheme。
- `ios/Config/App.xcconfig`：Bundle ID、版本、站点和可选 Team ID。
- `ios/ExportOptions.plist.example`：无凭据导出模板。
- `scripts/ios_release.py`：预检、archive、release 和脱敏报告。
- `tests/test_ios_release_assets.py`：发布资产契约。
- `docs/ios-release.md`：构建与签操作手册。

### 后续材料

- 受控发布环境中的有效 Apple 签名身份和匹配 Profile。
- App Store Connect App 记录、API Key、TestFlight 测试账号和商店元数据。
- 真机/TestFlight 回归报告、截图、隐私政策和审核说明。

## 任务 1：工程与资产契约

**文件：**

- 验证：`ios/TechnicalInterviewAgent.xcodeproj/project.pbxproj`
- 验证：`ios/TechnicalInterviewAgent.xcodeproj/xcshareddata/xcschemes/TechnicalInterviewAgent.xcscheme`
- 验证：`ios/TechnicalInterviewAgent/Info.plist`
- 验证：`ios/TechnicalInterviewAgent/Resources/PrivacyInfo.xcprivacy`
- 验证：`ios/TechnicalInterviewAgent/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png`
- 测试：`tests/test_ios_release_assets.py`

- [x] **步骤 1：** 断言工程自包含、共享 Scheme 可归档、Bundle ID 和最低系统正确。
- [x] **步骤 2：** 断言 HTTPS-only、上传权限、隐私 Manifest 和无透明图标。
- [x] **步骤 3：** 运行 `uv run pytest tests/test_ios_release_assets.py -q`。

## 任务 2：WebView 与原生交互

**文件：**

- 验证：`ios/TechnicalInterviewAgent/AppConfig.swift`
- 验证：`ios/TechnicalInterviewAgent/WebViewController.swift`
- 测试：`tests/test_ios_release_assets.py`

- [x] **步骤 1：** 断言默认 `WKWebsiteDataStore`、HTTPS 校验和站点 host 比较。
- [x] **步骤 2：** 断言文件选择器、确认框、外链浏览器和可重试错误状态。
- [x] **步骤 3：** 断言不暴露本地文件或业务 JavaScript bridge。

## 任务 3：签名模板与发布脚本

**文件：**

- 验证：`ios/Config/App.xcconfig`
- 验证：`ios/Config/Signing.xcconfig.example`
- 验证：`ios/ExportOptions.plist.example`
- 验证：`scripts/ios_release.py`
- 测试：`tests/test_ios_release_assets.py`

- [x] **步骤 1：** 运行无签名预检，缺失 Team ID、Profile 和 App Store 材料时返回 `blocked`。
- [x] **步骤 2：** 断言导出模板使用 `app-store-connect` 且不含凭据。
- [x] **步骤 3：** 断言 `.gitignore` 排除私钥、证书、Profile、IPA 和归档。
- [ ] **步骤 4：** 在受控 Mac 提供有效签名材料后运行 archive。

## 任务 4：真机与 TestFlight 验收

**文件：**

- 证据：脱敏 archive/release 报告
- 证据：TestFlight 构建和测试记录
- 文档：`docs/ios-release.md`

- [ ] **步骤 1：** 在完整 Xcode 和 Intel/Apple Silicon 目标环境执行 archive。
- [ ] **步骤 2：** 安装到至少一台真机，验证登录、简历上传、资料上传、问答和模拟面试。
- [ ] **步骤 3：** 验证退出、重置密码、SSE 重连和外链行为。
- [ ] **步骤 4：** 上传 TestFlight，记录构建号、测试账号和问题清单。

## 任务 5：App Store 材料与提交

**文件：**

- 证据：App Store Connect 记录
- 证据：隐私政策和支持 URL
- 证据：截图、分级、审核说明和发布负责人签字

- [ ] **步骤 1：** 在 App Store Connect 创建 App 记录并确认 Bundle ID/Team ID。
- [ ] **步骤 2：** 补齐隐私政策、支持 URL、截图、年龄分级和审核联系人。
- [ ] **步骤 3：** 填写隐私问卷并确认 `PrivacyInfo.xcprivacy` 与实际 SDK 一致。
- [ ] **步骤 4：** 由账号持有人提交审核并记录审核结论。

## 任务 6：收尾与发布证据

- [ ] **步骤 1：** 运行 `uv run pytest tests/test_decision_docs.py tests/test_ios_release_assets.py -q`。
- [ ] **步骤 2：** 运行 `uv run ruff check . && uv run ruff format --check .`。
- [ ] **步骤 3：** 更新[方案总览](../../solution-map.md)和[Superpowers 索引](../README.md)。
- [ ] **步骤 4：** 记录签名、TestFlight、商店提交和生产发布的实际状态，不把 `blocked` 写成完成。

## 交付边界

工程、预检、签名模板和资产契约已实现；签名、真机、TestFlight 和 App Store 提交仍是
受控账号和发布环境的外部工作。后续执行以本计划任务 3 至 6 为准。
