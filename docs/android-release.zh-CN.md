# Android 发布

原生 Capacitor 壳位于 `web/android`，加载
`https://it.rainstone.top` 的同源生产站点，因此现有 HttpOnly 会话 Cookie、
可读 CSRF Cookie、multipart 上传和 SSE 行为保持不变。

- 应用名称：`技术面试`
- 应用 ID：`top.rainstone.technicalinterviewagent`
- 版本：`versionName=0.1.0`、`versionCode=1`
- 最低 SDK：26
- 编译 SDK：36；目标 SDK：35

## 本地 debug 构建

安装 JDK 21 和 Android SDK platform 36，然后执行：

```bash
cd web
npm ci
npm run build
npx cap sync android
cd android
./gradlew assembleDebug
```

debug APK 位于
`web/android/app/build/outputs/apk/debug/app-debug.apk`，使用标准 debug
签名，并带 `.debug` 应用 ID 后缀。安装命令：

```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

## Release 签名

在仓库外创建 release keystore，并保存在密钥管理器中。不要提交 keystore
或密码：

```bash
keytool -genkeypair -v -keystore /secure/path/interview-release.p12 \
  -storetype PKCS12 -alias interview-release \
  -keyalg RSA -keysize 4096 -validity 10000
```

只在构建环境中导出四个签名变量：

```bash
export ANDROID_KEYSTORE_PATH=/secure/path/interview-release.p12
export ANDROID_KEYSTORE_PASSWORD='...'
export ANDROID_KEY_ALIAS=interview-release
export ANDROID_KEY_PASSWORD='...'
cd web/android
./gradlew bundleRelease assembleRelease
```

缺少签名变量时 release 任务会失败。产物位于
`app/build/outputs/bundle/release/app-release.aab` 和
`app/build/outputs/apk/release/app-release.apk`。

## GitHub Actions

`android` workflow 在 Pull Request 中构建并验证 debug 产物。匹配 `v*`
的 tag 会构建签名 release，并将 APK、AAB 和校验和上传到 GitHub Release。

配置以下仓库 Secrets：

- `ANDROID_KEYSTORE_BASE64`：PKCS12 keystore 的 base64 内容
- `ANDROID_KEYSTORE_PASSWORD`
- `ANDROID_KEY_ALIAS`
- `ANDROID_KEY_PASSWORD`

创建并推送发布 tag：

```bash
git tag -a v0.1.0 -m "Android v0.1.0"
git push origin v0.1.0
```

## 验证与商店提交

验证 APK 签名和校验和：

```bash
apksigner verify --print-certs app/build/outputs/apk/release/app-release.apk
shasum -a 256 app/build/outputs/apk/release/app-release.apk \
  app/build/outputs/bundle/release/app-release.aab
```

Google Play Console 提交流程需要人工完成：上传签名 AAB、填写数据安全与内容
分级表单、配置应用签名密钥、补充商店素材并提交审核。这些操作依赖项目负责人
的 Play Console 账号和审批，无法由仓库 workflow 自动完成。
