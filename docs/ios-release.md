# iOS 打包与发布准备

| 项目 | 内容 |
| --- | --- |
| 文档版本 | v1.0 |
| 更新日期 | 2026-10-22 |
| 工程 | `ios/TechnicalInterviewAgent.xcodeproj` |
| 共享 Scheme | `TechnicalInterviewAgent` |
| 候选 Bundle ID | `top.rainstone.technicalinterviewagent` |
| 生产站点 | `https://it.rainstone.top` |
| 最低系统 | iOS 17.0 |

> 本文件记录包装方案、可复现的本地构建步骤和商店发布所需的受控材料。
> 当前仓库与构建产物中不得出现 Apple 私钥、`.p12`、`.mobileprovision`
> 或 App Store Connect API Key。

## 1. 现状结论

仓库原先没有 iOS/SwiftUI 工程、Xcode 共享 Scheme、Bundle ID、签名证书、
Provisioning Profile 或 App Store Connect 配置。现有用户界面是
`web/` 中的 React + TypeScript + Vite 单页应用，生产环境由 Nginx 同源
托管 SPA 并代理 `/api`。

本次采用原生 SwiftUI 风格的基础外壳加 `WKWebView`：UIKit 负责应用生命周期，
`WKWebView` 直接加载现有生产站点。没有引入 Capacitor、Cordova 或第三方
iOS 依赖。该方案保留现有路由、登录会话 Cookie、CSRF、SSE 事件流和
同源认证语义。

## 2. 为什么不是离线静态包

当前前端依赖以下浏览器行为：

- `interview_session` 是 `HttpOnly`、`Secure`、`SameSite=Lax` Cookie。
- `interview_csrf` 由前端读取并随写请求发送。
- API 通过同源 Nginx 提供，不能拆成任意第三方 Origin。
- 问答使用可重连 SSE，不能替换为简单一次性请求。

因此不能把 `web/dist` 直接拷入 WebView 后以 `file://` 或自定义 Origin
运行。那会让 Cookie、Origin/Referer allowlist、上传和 SSE 连接失效。
包装层必须加载受控的 HTTPS 站点，并允许它访问同一站点的 `/api`。

## 3. 工程结构

```text
ios/
  Config/
    App.xcconfig                  # Bundle ID、版本、站点和可选 Team ID
    Signing.xcconfig.example      # 只含 Team ID 的本机配置模板
  TechnicalInterviewAgent/
    AppDelegate.swift             # UIKit 生命周期
    SceneDelegate.swift           # 窗口、导航外观
    AppConfig.swift               # HTTPS 与允许域名校验
    WebViewController.swift       # WKWebView、Cookie、上传、外链和离线态
    Info.plist
    Resources/
      PrivacyInfo.xcprivacy
      InfoPlist.strings
    Assets.xcassets/
      AppIcon.appiconset/         # 1024x1024、无透明通道
  TechnicalInterviewAgent.xcodeproj
  ExportOptions.plist.example     # 不含凭据的导出模板
```

候选 Bundle ID 只记录在 `ios/Config/App.xcconfig`，不是已注册的 Apple
Developer 标识。签入代码不代表 Apple Developer 或 App Store Connect 已接受
该标识；正式签名前由账号持有人注册并确认。

## 4. 本地构建步骤

前置条件：

- macOS 13 或更高版本。
- 完整安装 Xcode 15 或更高版本，并在 `xcode-select` 中选择 Xcode.app。
- Xcode 已接受许可协议，iOS SDK 和至少一个 iOS Simulator 可用。
- 如需真机或归档，本机 Keychain 必须有有效 Apple Development 或
  Apple Distribution 身份。

只做无签名预检和 Web 构建：

```bash
grep -q '^web/dist/' .gitignore  # 构建输出不进入版本库
uv run python scripts/ios_release.py --mode preflight \
  --report ios/build/preflight.json
```

预期：

- `web_build` 为 `pass`。
- `xcode` 为 `pass`。
- 未提供 Team ID 时 `development_team` 为 `blocked`，这是正常的安全性阻塞，
  不是脚本错误。
- 未确认 App Store Connect App 记录和商店元数据时
  `app_store_connect` 为 `blocked`。

在 Xcode 中打开工程：

```bash
open ios/TechnicalInterviewAgent.xcodeproj
```

选择 `TechnicalInterviewAgent` Scheme 和 iPhone Simulator 后运行。首次运行
会请求网络权限；应用会加载 `https://it.rainstone.top`。

## 5. 签名与归档

### 5.1 Bundle ID

当前候选值：

```text
top.rainstone.technicalinterviewagent
```

正式提交前，账号持有人必须确认：

- Bundle ID 在 Apple Developer 中可用并归属于目标团队。
- App Store Connect 已创建对应 App 记录。
- App Store Connect 的 SKU、主语言、年龄分级、隐私政策和审核联系人已填写。
- 生产站点、API 域名和 Cookie 域与 `APP_ALLOWED_ORIGINS`、
  `CSRF_ALLOWED_ORIGINS` 完全一致。

若最终 Bundle ID 不同，只修改 `ios/Config/App.xcconfig` 中的
`APP_PRODUCT_BUNDLE_IDENTIFIER`，同步更新测试和发布文档，不要散落在源码中。

### 5.2 Team ID

不要把 Team ID 和证书提交到仓库。可选做法：

```bash
cp ios/Config/Signing.xcconfig.example ios/Config/Signing.xcconfig
# 仅在本机填写 APP_DEVELOPMENT_TEAM = ABCDE12345
```

或者只在当前 shell 提供：

```bash
export APPLE_DEVELOPMENT_TEAM=ABCDE12345
```

`ios/Config/Signing.xcconfig` 已被 `.gitignore` 忽略。Team ID 不是私钥，
但仍属于受控账号信息，发布报告中只记录“已配置/未配置”，不写入日志。

### 5.3 Provisioning Profile

本机 `~/Library/MobileDevice/Provisioning Profiles/` 必须存在满足以下条件的
未过期 Profile：

- Team ID 与应用配置一致。
- `application-identifier` 结尾为候选 Bundle ID。
- 证书与 Xcode 选择的签名身份匹配。

脚本只读取 Profile 元数据，检查 Team ID、Bundle ID 和过期时间；不会复制
Profile 到仓库，也不会打印私钥或设备 UDID。若使用自动签名，先启用
`-allowProvisioningUpdates` 并确保 Xcode 已登录对应 Apple Developer 账号。

### 5.4 证书

归档需要本机 Keychain 中存在有效的 Apple Development 或 Apple Distribution
身份。不要把以下文件提交到仓库：

- `*.cer`
- `*.p12`
- `*.p8`
- `*.mobileprovision`

证书丢失时，由 Apple Developer 账号持有人重新签发；不得通过关闭签名校验、
修改 Bundle ID 或使用他人 Profile 绕过。

### 5.5 归档与导出

在签名材料就绪后执行：

```bash
uv run python scripts/ios_release.py --mode archive \
  --team-id ABCDE12345 \
  --build-number 1 \
  --report ios/build/archive-report.json
```

成功产物：

```text
ios/build/TechnicalInterviewAgent.xcarchive
```

归档后由 Xcode Organizer 或同一受控 Mac 执行 App Store Connect 导出。
仓库提供不含凭据的 `ios/ExportOptions.plist.example`；正式导出前在本地复制为
`ios/ExportOptions.plist`，不要提交。示例使用：

```xml
<key>method</key>
<string>app-store-connect</string>
<key>signingStyle</key>
<string>automatic</string>
```

如使用导出脚本模式：

```bash
uv run python scripts/ios_release.py --mode release \
  --team-id ABCDE12345 \
  --build-number 1 \
  --report ios/build/release-report.json
```

人工上传前应满足以下条件：

- 本机有有效签名身份。
- Team ID、Bundle ID 与未过期 Profile 匹配。
- 导出 IPA 成功。

脚本完成 `archive + export` 后会停在人工上传步骤；本环境没有完整 Xcode 和
`xcrun altool`，不能用未验证的参数伪报上传成功。使用 Xcode Organizer 或由
发布负责人按当前 Apple Transporter/App Store Connect CLI 的官方参数完成上传。

如果后续把上传接入受控 CI，凭据只允许来自平台 Secret：

```bash
export APP_STORE_CONNECT_API_KEY_PATH="$HOME/.appstoreconnect/private_keys/AuthKey_XXXX.p8"
export APP_STORE_CONNECT_API_KEY_ID=XXXX
export APP_STORE_CONNECT_API_ISSUER_ID=00000000-0000-0000-0000-000000000000
```

不要在命令行参数、截图、日志、Issue、PR 或 shell history 中写入密钥内容。
生产 CI 使用平台 Secret 注入，并把报告作为脱敏构建产物保存。

## 6. 当前阻塞项

本次执行环境中：

- `xcodebuild` 不可用：`xcode-select -p` 指向 Command Line Tools，未指向完整
  Xcode.app。
- `xcrun simctl` 不可用，无法启动 iOS Simulator 做截图或运行验证。
- `security find-identity -v -p codesigning` 返回 0 个有效身份。
- 本机 Profile 均属于其他历史应用，未发现当前候选 Bundle ID 的 Profile。
- 未发现 App Store Connect API Key、Issuer ID、App Store Connect App 记录。
- 未发现项目 Apple Developer Team ID。

因此本次只能完成工程结构、Web 生产构建、静态契约测试和无签名预检；不能
声称已完成可提交 App Store 的签名 IPA、TestFlight 上传或审核提交。

补齐这些材料后，按以下顺序解除阻塞：

1. 安装并选择完整 Xcode，接受许可协议并安装 iOS SDK/Simulator。
2. 由 Apple Developer 账号持有人确认或创建 Bundle ID 和 App 记录。
3. 在本机导入有效签名证书，配置 Team ID 和匹配 Profile。
4. 注入 App Store Connect API Key，运行 `archive` 预检。
5. 在 TestFlight 完成至少一轮真机安装、登录、上传和 SSE 问答验证。
6. 补齐 App Store 元数据、隐私政策、支持 URL、截图和审核说明后提交审核。

## 7. App 审核风险

Apple 对“网站封装”类应用存在 4.2 最低功能要求风险。当前包装层具备原生
生命周期、文件上传、系统浏览器外链、离线提示和同源会话保持，但这些不能
保证一定通过审核。若审核认为应用缺乏足够原生价值，优先考虑增加与面试
工作流直接相关的原生能力，例如推送提醒、离线练习、原生录音转写或本地
错题复习，而不是通过隐藏 WebView 或伪造内容规避审核。

## 8. 隐私与数据边界

应用会加载生产站点，生产站点的账号、简历、资料、问答和面试数据仍按
后端现有权限和保留规则处理。`PrivacyInfo.xcprivacy` 当前声明不跟踪、
不收集第三方广告数据；如果后续接入统计、推送、崩溃收集或第三方 SDK，
必须同步更新 Manifest、隐私政策和 App Store 隐私问卷。

## 9. 验证清单

- [x] Web 生产构建通过。
- [x] 工程、Scheme、Info.plist、隐私 Manifest 和 1024 图标结构测试通过。
- [x] 图标为 1024x1024 RGB PNG，无 alpha。
- [x] `.gitignore` 排除证书、Profile、`.p8`、`.ipa`、`.xcarchive` 和
  `Signing.xcconfig`。
- [ ] 完整 Xcode、Simulator、签名身份和匹配 Profile 可用。
- [ ] 真机/TestFlight 安装与核心流程回归。
- [ ] App Store Connect App 记录、截图、隐私政策和审核材料齐全。

## 10. 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v1.0 | 2026-10-22 | 建立原生 WKWebView 包装工程、共享 Scheme、配置模板、发布预检脚本和阻塞项清单 |
