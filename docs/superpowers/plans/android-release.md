# Android 发布接入实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 subagent-driven-development（推荐）或 executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为现有 Web 应用交付可安装、可签名、可由 GitHub Actions 构建和发布的 Android 原生壳。

**架构：** 单一 Android 原生 WebView 加载 `https://it.rainstone.top`，通过系统 CookieManager、文件选择器和 App Link 保持同源认证与原生交互；Gradle 与 GitHub Actions 提供 debug/release 可复现构建。

**技术栈：** Android Gradle Plugin、Kotlin、AndroidX Activity/WebKit、Gradle wrapper、GitHub Actions、Python pytest 资产契约。

**规格：** `docs/superpowers/specs/android-release-design.md`

## 全局约束

- 应用名必须为 `技术面试`，包名必须为 `top.rainstone.technicalinterviewagent`。
- 站点根地址必须为 `https://it.rainstone.top`，不允许生产 HTTP 回退。
- 最低 SDK 26、target SDK 35、compile SDK 36（Capacitor 8 依赖要求），
  `versionName=0.1.0`，`versionCode=1`。
- 不提交真实 keystore、密码、token 或签名产物。
- release 签名只通过 `ANDROID_KEYSTORE_PATH`、`ANDROID_KEYSTORE_PASSWORD`、
  `ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD` 注入。
- 不破坏 Web 端现有 API、Cookie、CSRF、上传和响应式行为。
- tag `v*` 必须构建 release 产物并上传 APK、AAB 和 SHA-256 文件。
- 按仓库规则运行 ruff、mypy、pytest、前端检查与 Android 构建。

## 审查重点（Review Focus）

- 非 `https` URL 或非站点 host 被错误加载：必须拒绝并显示错误，而不是降级到 HTTP。
- `file` 输入选择器的多选、取消和 URI 权限失败：必须返回空结果或有效 URI，不能崩溃。
- 缺少签名 Secrets 时 tag 构建：必须明确失败，不能把 debug 签名当作 release 发布。
- 深链接进入 SPA 路由或密码重置路径：必须保留同源路径并支持应用被冷启动。
- Cookie 与 CSRF 在跨页面导航后失效：必须保留默认 CookieManager、Secure/HttpOnly 语义，
  不通过桥接读取 HttpOnly 值。

---

### 任务 1：发布资产契约与 Android 工程骨架

**文件：**
- 创建：`tests/test_android_release_assets.py`
- 创建：`android/settings.gradle.kts`
- 创建：`android/build.gradle.kts`
- 创建：`android/gradle.properties`
- 创建：`android/gradle/libs.versions.toml`
- 创建：`android/gradle/wrapper/gradle-wrapper.properties`
- 创建：`android/gradle/wrapper/gradle-wrapper.jar`
- 创建：`android/gradlew`
- 创建：`android/gradlew.bat`
- 创建：`android/app/build.gradle.kts`
- 创建：`android/app/src/main/AndroidManifest.xml`
- 创建：`android/app/proguard-rules.pro`
- 创建：`android/app/src/main/res/values/strings.xml`
- 创建：`android/app/src/main/res/values/colors.xml`
- 创建：`android/app/src/main/res/values/themes.xml`
- 创建：`android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml`
- 创建：`android/app/src/main/res/drawable/ic_launcher_foreground.xml`
- 创建：`android/app/src/main/res/drawable/ic_launcher_background.xml`
- 创建：`android/app/src/main/res/drawable/splash_background.xml`
- 创建：`android/app/src/main/res/values-night/themes.xml`
- 创建：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/MainActivity.kt`
- 创建：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/AppConfig.kt`
- 创建：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/UrlPolicy.kt`
- 创建：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/WebAppClient.kt`
- 修改：`.gitignore`

- [ ] **步骤 1：编写失败的资产契约测试**

在 `tests/test_android_release_assets.py` 断言：

```python
def test_android_manifest_is_https_only_and_has_deep_link() -> None:
    manifest = _read("android/app/src/main/AndroidManifest.xml")
    assert 'android:usesCleartextTraffic="false"' in manifest
    assert "https" in manifest
    assert "it.rainstone.top" in manifest
    assert "android.intent.action.VIEW" in manifest
    assert "android.intent.category.BROWSABLE" in manifest
```

另断言包名、版本、签名环境变量、wrapper、WebView Cookie/文件选择器和 Actions 配置。

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：FAIL，提示 Android manifest 文件不存在。

- [ ] **步骤 3：创建最小 Android 工程**

生成 Gradle wrapper，创建 Kotlin `MainActivity`、`WebAppClient`、`UrlPolicy` 与资源；
`build.gradle.kts` 读取四个签名环境变量，release 缺少任一项时抛出 GradleException。

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add tests/test_android_release_assets.py android .gitignore
git commit -m "feat(android): add native web shell"
```

### 任务 2：URL 与文件选择策略的 JVM 单元测试

**文件：**
- 创建：`android/app/src/test/kotlin/top/rainstone/technicalinterviewagent/AppConfigTest.kt`
- 创建：`android/app/src/test/kotlin/top/rainstone/technicalinterviewagent/UrlPolicyTest.kt`
- 修改：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/UrlPolicy.kt`
- 修改：`android/app/src/main/kotlin/top/rainstone/technicalinterviewagent/AppConfig.kt`

- [ ] **步骤 1：编写失败的单元测试**

测试 `UrlPolicy.isTrusted("https://it.rainstone.top/login")` 为 true，HTTP 和外部 host 为
false，scheme 分类正确，`FileChooserPolicy` 的 accept/多选行为覆盖单文件、多文件、取消。

- [ ] **步骤 2：运行测试验证失败**

运行：`cd android && ./gradlew testDebugUnitTest --tests '*UrlPolicyTest'`
预期：FAIL，找不到策略实现。

- [ ] **步骤 3：实现最小策略**

实现无 Android Context 依赖的 `UrlPolicy`、`FileChooserPolicy`，并让 WebAppClient 使用它们。

- [ ] **步骤 4：运行测试验证通过**

运行：`cd android && ./gradlew testDebugUnitTest`
预期：`BUILD SUCCESSFUL`，所有 JVM 测试通过。

- [ ] **步骤 5：Commit**

```bash
git add android/app/src/main android/app/src/test
git commit -m "test(android): cover URL and file chooser policy"
```

### 任务 3：签名模板、构建脚本与发布工作流

**文件：**
- 创建：`android/keystore.properties.example`
- 创建：`scripts/build_android_release.sh`
- 创建：`.github/workflows/android.yml`
- 修改：`.gitignore`
- 修改：`tests/test_android_release_assets.py`

- [ ] **步骤 1：编写失败的工作流契约测试**

断言 workflow 包含 `pull_request`、`workflow_dispatch`、`v*` tag 触发、Java 21、Gradle
`assembleDebug`/`bundleRelease`/`assembleRelease`、`softprops/action-gh-release`，并断言
签名 Secrets 不存在明文值。

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：FAIL，workflow 不存在。

- [ ] **步骤 3：实现签名注入与工作流**

脚本在临时目录解码 base64 keystore，调用 Gradle 后清理临时文件；workflow 在 tag 时上传
`app-release.apk`、`app-release.aab` 和 `.sha256`。PR 只做 debug 与测试，release 需要
仓库 Secrets。

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add scripts/build_android_release.sh .github/workflows/android.yml android/keystore.properties.example tests/test_android_release_assets.py .gitignore
git commit -m "ci(android): build and release signed artifacts"
```

### 任务 4：中文文档、品牌资产与版本同步

**文件：**
- 创建：`docs/android-release.md`
- 修改：`README.md`
- 修改：`README.zh-CN.md`
- 修改：`CHANGELOG.md`
- 修改：`android/app/src/main/res/values/strings.xml`
- 修改：`android/app/build.gradle.kts`
- 修改：`tests/test_android_release_assets.py`

- [ ] **步骤 1：编写失败的文档契约测试**

断言中文文档包含 Android 包名、站点 URL、本地 debug、release 签名环境变量、GitHub
Actions tag 发布、Google Play Console 人工步骤、版本号与产物校验命令。

- [ ] **步骤 2：运行测试验证失败**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：FAIL，文档不存在。

- [ ] **步骤 3：补齐文档与版本信息**

写清 debug APK 安装、release AAB/APK 签名、secrets、安装、校验和商店提交；更新
README 与中文 README 的发布段落，版本保持 `0.1.0 / 1`。

- [ ] **步骤 4：运行测试验证通过**

运行：`uv run pytest tests/test_android_release_assets.py -q`
预期：PASS。

- [ ] **步骤 5：Commit**

```bash
git add README.md README.zh-CN.md CHANGELOG.md docs/android-release.md android/app tests/test_android_release_assets.py
git commit -m "docs(android): document build signing and release"
```

### 任务 5：本地完整验证、构建证据与发布

**文件：**
- 修改：`tests/test_android_release_assets.py`（仅补齐真实构建检查）
- 创建：本地临时签名 keystore（仓库外，忽略）
- 生成：`android/app/build/outputs/**`（仓库外/忽略）

- [ ] **步骤 1：运行全部相关测试**

运行：
```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests evals migrations
uv run pytest -q
cd web && npm test -- --run && npm run lint && npm run build
cd ../android && ./gradlew testDebugUnitTest assembleDebug
```
预期：全部 exit 0；Android 构建生成 APK。

- [ ] **步骤 2：构建签名 release**

在仓库外生成临时 PKCS12 keystore，注入四个环境变量，运行：
```bash
cd android
./gradlew clean bundleRelease assembleRelease
```
预期：生成 `app-release.apk` 和 `app-release.aab`。

- [ ] **步骤 3：验证产物**

运行 `apksigner verify --print-certs`、`aapt2 dump badging`、`sha256sum`，记录绝对路径、
版本、签名状态与校验和；确认仓库未出现 keystore、密码或未跟踪产物。

- [ ] **步骤 4：提交并创建 PR**

```bash
git add android tests docs README.md README.zh-CN.md CHANGELOG.md scripts .github
git commit -m "feat(android): add installable release pipeline"
git push -u origin codex/android-release
gh pr create --fill
```

- [ ] **步骤 5：等 CI、合并并发布**

在 CI 全绿后合并 PR；创建 `v0.1.1-android.1` annotated tag，等待 Android Release workflow
上传产物，检查 GitHub Release 链接与 SHA-256。

**任务自检：** 规格中的 HTTPS 同源、Cookie/CSRF、文件上传、深链接、签名、Actions、双语
文档、版本和商店人工步骤均有对应任务；测试覆盖了非 HTTPS、外部 host、取消、缺少 Secrets
和 tag 发布风险。
