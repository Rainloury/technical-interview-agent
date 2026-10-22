"""Android wrapper, signing, CI, and release documentation contracts."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "web" / "android"
APP = ANDROID / "app"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_android_project_uses_expected_package_sdk_and_version() -> None:
    app_build = _read("web/android/app/build.gradle")
    settings = _read("web/android/settings.gradle")
    variables = _read("web/android/variables.gradle")
    wrapper = _read("web/android/gradle/wrapper/gradle-wrapper.properties")
    strings = _read("web/android/app/src/main/res/values/strings.xml")

    assert "top.rainstone.technicalinterviewagent" in app_build
    assert "versionCode 1" in app_build
    assert 'versionName "0.1.0"' in app_build
    assert "minSdkVersion = 26" in variables
    assert "compileSdkVersion = 36" in variables
    assert "targetSdkVersion = 35" in variables
    assert "include ':app'" in settings
    assert "gradle-8.14.3-bin.zip" in wrapper
    assert "bd71102213493060956ec229d946beee57158dbd89d0e62b91bca0fa2c5f3531" in wrapper
    assert '<string name="app_name">技术面试</string>' in strings
    assert 'android:label="@string/app_name"' in _read(
        "web/android/app/src/main/AndroidManifest.xml"
    )
    assert (ANDROID / "gradlew").is_file()
    assert (ANDROID / "gradle/wrapper/gradle-wrapper.jar").is_file()
    assert "@capacitor/core" in _read("web/package.json")
    assert "@capacitor/android" in _read("web/package.json")
    assert 'url: "https://it.rainstone.top"' in _read("web/capacitor.config.ts")
    assert "AppConfigTest" in _read(
        "web/android/app/src/test/java/top/rainstone/technicalinterviewagent/AppConfigTest.java"
    )


def test_android_manifest_is_https_only_and_declares_app_link() -> None:
    manifest = _read("web/android/app/src/main/AndroidManifest.xml")

    assert 'android:usesCleartextTraffic="false"' in manifest
    assert "android.permission.INTERNET" in manifest
    assert 'android:exported="true"' in manifest
    assert "android.intent.action.VIEW" in manifest
    assert "android.intent.category.BROWSABLE" in manifest
    assert 'android:scheme="https"' in manifest
    assert 'android:host="it.rainstone.top"' in manifest
    assert 'android:autoVerify="true"' in manifest
    assert "networkSecurityConfig" not in manifest


def test_android_webview_preserves_same_origin_auth_and_upload() -> None:
    main = _read(
        "web/android/app/src/main/java/top/rainstone/technicalinterviewagent/MainActivity.java"
    )
    client = _read(
        "web/android/app/src/main/java/top/rainstone/technicalinterviewagent/WebAppClient.java"
    )
    config = _read(
        "web/android/app/src/main/java/top/rainstone/technicalinterviewagent/AppConfig.java"
    )

    assert 'static final String SITE_URL = "https://it.rainstone.top"' in config
    assert "CookieManager.getInstance()" in main
    assert "setAcceptCookie(true)" in main
    assert "setAcceptThirdPartyCookies(webView, false)" in main
    assert "CookieManager.getInstance().flush()" in main
    capacitor_config = _read("web/capacitor.config.ts")
    lockfile = json.loads(_read("web/package-lock.json"))
    assert 'appId: "top.rainstone.technicalinterviewagent"' in capacitor_config
    assert "captureInput: true" in capacitor_config
    assert lockfile["packages"]["node_modules/@capacitor/android"]["version"] == "8.5.3"
    assert 'type="file"' in _read("web/src/pages/ResumeUploadPage.tsx")
    assert 'type="file"' in _read("web/src/pages/DocumentsPage.tsx")
    assert "multiple" in _read("web/src/pages/DocumentsPage.tsx")
    assert "addJavascriptInterface" not in main
    assert "setAllowFileAccess(false)" in main
    assert "setAllowContentAccess(false)" in main
    assert "setDomStorageEnabled(true)" in main
    assert "loadDeepLink" in main
    assert "AppConfig.isSiteUri" in client
    assert "Intent.ACTION_VIEW" in client
    assert "AppConfig.isSiteUri" in client


def test_android_release_signing_uses_environment_only() -> None:
    app_build = _read("web/android/app/build.gradle")
    template = _read("web/android/keystore.properties.example")
    gitignore = _read(".gitignore").splitlines()

    for variable in (
        "ANDROID_KEYSTORE_PATH",
        "ANDROID_KEYSTORE_PASSWORD",
        "ANDROID_KEY_ALIAS",
        "ANDROID_KEY_PASSWORD",
    ):
        assert variable in app_build
        assert variable in template

    assert "System.getenv" in app_build
    assert "GradleException" in app_build
    assert "signingConfig signingConfigs.release" in app_build
    assert "storeFile" in app_build
    assert "BEGIN PRIVATE KEY" not in app_build
    assert "top.rainstone.technicalinterviewagent" in template
    for ignored in (
        "android/.gradle/",
        "web/android/.gradle/",
        "web/android/build/",
        "web/android/local.properties",
        "web/android/app/build/",
        "web/android/keystore.properties",
        "*.jks",
        "*.keystore",
    ):
        assert ignored in gitignore


def test_android_ci_builds_debug_and_publishes_tagged_release() -> None:
    workflow_path = ROOT / ".github/workflows/android.yml"
    workflow_text = workflow_path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(workflow_text)
    triggers = workflow.get("on", workflow.get(True))
    assert triggers is not None

    assert "pull_request" in triggers
    assert "workflow_dispatch" in triggers
    assert "v*" in triggers["push"]["tags"]
    assert workflow["permissions"]["contents"] == "write"
    jobs = workflow["jobs"]
    assert "build" in jobs
    assert "release" in jobs
    build_steps = jobs["build"]["steps"]
    release_steps = jobs["release"]["steps"]
    assert any(
        "gradlew" in str(step.get("run", "")) and "assembleDebug" in str(step.get("run", ""))
        for step in build_steps
    )
    assert any(
        "gradlew" in str(step.get("run", ""))
        and "bundleRelease" in str(step.get("run", ""))
        and "assembleRelease" in str(step.get("run", ""))
        for step in release_steps
    )
    assert "softprops/action-gh-release" in workflow_text
    assert "app-release.apk" in workflow_text
    assert "app-release.aab" in workflow_text
    assert "ANDROID_KEYSTORE_BASE64" in workflow_text
    assert "ANDROID_KEYSTORE_PASSWORD" in workflow_text
    assert "ANDROID_KEY_ALIAS" in workflow_text
    assert "ANDROID_KEY_PASSWORD" in workflow_text
    assert 'java-version: "21"' in workflow_text
    assert "BEGIN PRIVATE KEY" not in workflow_text


def test_android_release_assets_have_brand_and_splash() -> None:
    strings = _read("web/android/app/src/main/res/values/strings.xml")
    theme = _read("web/android/app/src/main/res/values/styles.xml")
    launcher = _read("web/android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml")
    foreground = _read("web/android/app/src/main/res/drawable-v24/ic_launcher_foreground.xml")
    background = _read("web/android/app/src/main/res/drawable/ic_launcher_background.xml")

    assert "技术面试" in strings
    assert "windowSplashScreenAnimatedIcon" in theme
    assert "postSplashScreenTheme" in theme
    assert "ic_launcher_foreground" in launcher
    assert "ic_launcher_background" in launcher
    assert "#3447D8" in foreground or "#3447D8" in background


def test_android_release_docs_cover_build_signing_install_and_store_steps() -> None:
    documents = (
        _read("docs/android-release.md"),
        _read("docs/android-release.zh-CN.md"),
    )

    for document in documents:
        for fragment in (
            "top.rainstone.technicalinterviewagent",
            "https://it.rainstone.top",
            "assembleDebug",
            "bundleRelease",
            "ANDROID_KEYSTORE_PATH",
            "ANDROID_KEYSTORE_PASSWORD",
            "ANDROID_KEY_ALIAS",
            "ANDROID_KEY_PASSWORD",
            "GitHub Actions",
            "Google Play Console",
            "v0.1.0",
        ):
            assert fragment in document

    english = _read("README.md")
    chinese = _read("README.zh-CN.md")
    assert "Android" in english
    assert "Android" in chinese
    assert "docs/android-release.md" in english
    assert "docs/android-release.zh-CN.md" in chinese


def test_android_private_signing_material_is_ignored() -> None:
    gitignore = _read(".gitignore").splitlines()

    for ignored in (
        "web/android/local.properties",
        "web/android/keystore.properties",
        "web/android/app/build/",
        "*.jks",
        "*.keystore",
    ):
        assert ignored in gitignore
