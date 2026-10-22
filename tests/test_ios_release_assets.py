"""iOS wrapper project and release-asset contracts."""

from __future__ import annotations

import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios"
APP = IOS / "TechnicalInterviewAgent"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_ios_project_is_self_contained_and_shared_scheme_is_present() -> None:
    project = _read("ios/TechnicalInterviewAgent.xcodeproj/project.pbxproj")
    scheme = _read(
        "ios/TechnicalInterviewAgent.xcodeproj/"
        "xcshareddata/xcschemes/TechnicalInterviewAgent.xcscheme"
    )

    for file_name in (
        "AppDelegate.swift",
        "SceneDelegate.swift",
        "AppConfig.swift",
        "WebViewController.swift",
        "Assets.xcassets",
        "PrivacyInfo.xcprivacy",
    ):
        assert file_name in project

    assert 'productType = "com.apple.product-type.application"' in project
    assert "INFOPLIST_FILE = TechnicalInterviewAgent/Info.plist" in project
    assert 'PRODUCT_BUNDLE_IDENTIFIER = "$(APP_PRODUCT_BUNDLE_IDENTIFIER)"' in project
    assert 'DEVELOPMENT_TEAM = "";' in project
    assert "IPHONEOS_DEPLOYMENT_TARGET = 17.0" in project
    assert 'buildForArchiving = "YES"' in scheme
    assert "<ArchiveAction" in scheme
    assert "xcodeproj/project.pbxproj" not in scheme


def test_ios_candidate_config_contains_no_signing_material() -> None:
    config = _read("ios/Config/App.xcconfig")

    assert "APP_PRODUCT_BUNDLE_IDENTIFIER = top.rainstone.technicalinterviewagent" in config
    assert "APP_DEVELOPMENT_TEAM =" in config
    assert "APP_SITE_URL = https:/$()/it.rainstone.top" in config
    assert '#include? "Signing.xcconfig"' in config
    assert "BEGIN PRIVATE KEY" not in config
    assert "PROVISIONING_PROFILE_SPECIFIER" not in config


def test_ios_info_plist_is_https_only_and_has_upload_permissions() -> None:
    info = plistlib.loads((APP / "Info.plist").read_bytes())

    assert info["InterviewSiteURL"] == "$(APP_SITE_URL)"
    assert info["CFBundleIdentifier"] == "$(PRODUCT_BUNDLE_IDENTIFIER)"
    assert info["LSRequiresIPhoneOS"] is True
    assert info["NSCameraUsageDescription"]
    assert info["NSPhotoLibraryUsageDescription"]
    assert info["NSAppTransportSecurity"]["NSAllowsArbitraryLoads"] is False
    assert info["ITSAppUsesNonExemptEncryption"] is False


def test_ios_wrapper_keeps_same_origin_auth_and_handles_native_web_events() -> None:
    source = _read("ios/TechnicalInterviewAgent/WebViewController.swift")
    config = _read("ios/TechnicalInterviewAgent/AppConfig.swift")

    for fragment in (
        "configuration.websiteDataStore = .default()",
        "webView.load(URLRequest(url: siteURL))",
        "url.host?.lowercased() == siteURL.host?.lowercased()",
        "runOpenPanelWith",
        "UIDocumentPickerViewController",
        "runJavaScriptConfirmPanelWithMessage",
        "createWebViewWith",
        "SFSafariViewController",
        "isInspectable = true",
    ):
        assert fragment in source

    assert 'url.scheme == "https"' in config
    assert "IT.rainstone.top" not in source
    web_view_block = source.split("let webView = WKWebView", 1)[1].split("reloadButton", 1)[0]
    assert "translatesAutoresizingMaskIntoConstraints = false" not in web_view_block


def test_privacy_manifest_and_app_icon_are_release_ready() -> None:
    privacy_path = APP / "Resources/PrivacyInfo.xcprivacy"
    icon_path = APP / "Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png"
    contents = (APP / "Assets.xcassets/AppIcon.appiconset/Contents.json").read_text(
        encoding="utf-8"
    )
    privacy = plistlib.loads(privacy_path.read_bytes())

    assert privacy["NSPrivacyTracking"] is False
    assert privacy["NSPrivacyTrackingDomains"] == []
    assert privacy["NSPrivacyCollectedDataTypes"] == []
    assert privacy["NSPrivacyAccessedAPITypes"]
    assert icon_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert '"filename" : "AppIcon-1024.png"' in contents
    assert '"size" : "1024x1024"' in contents
    assert not (APP / "PrivacyInfo.xcprivacy").exists()


def test_export_options_example_uses_app_store_connect_without_credentials() -> None:
    export_options = plistlib.loads((IOS / "ExportOptions.plist.example").read_bytes())

    assert export_options["method"] == "app-store-connect"
    assert export_options["signingStyle"] == "automatic"
    assert export_options["manageAppVersionAndBuildNumber"] is False
    rendered = (IOS / "ExportOptions.plist.example").read_text(encoding="utf-8")
    for forbidden in (
        "issuer_id",
        "api_key",
        "api_key_id",
        "provisioningProfiles",
        "PRIVATE KEY",
    ):
        assert forbidden not in rendered


def test_ios_private_signing_paths_are_gitignored() -> None:
    gitignore = _read(".gitignore").splitlines()

    for ignored in (
        "*.mobileprovision",
        "*.p12",
        "*.p8",
        "*.ipa",
        "*.xcarchive",
        "ios/DerivedData/",
        "ios/ExportOptions.plist",
        "ios/Config/Signing.xcconfig",
    ):
        assert ignored in gitignore
