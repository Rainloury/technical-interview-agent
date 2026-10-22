import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_open_source_release_metadata_and_governance_files_exist() -> None:
    required_files = (
        "LICENSE",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "SUPPORT.md",
        "CHANGELOG.md",
        "NOTICE",
        "README.zh-CN.md",
        "THIRD_PARTY_NOTICES.md",
        ".github/pull_request_template.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
    )

    missing = [path for path in required_files if not (ROOT / path).is_file()]

    assert missing == []

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == {"text": "Apache-2.0"}
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")


def test_public_configuration_does_not_expose_internal_hosts() -> None:
    public_files = (
        ".env.example",
        "README.md",
        "README.zh-CN.md",
        "deploy/production.env.example",
    )
    forbidden_fragments = ("100.88.158.91", "rainstone.top")

    leaks = [
        f"{path}: {fragment}"
        for path in public_files
        for fragment in forbidden_fragments
        if fragment in (ROOT / path).read_text(encoding="utf-8")
    ]

    assert leaks == []


def test_readme_languages_link_to_each_other() -> None:
    english = (ROOT / "README.md").read_text(encoding="utf-8")
    chinese = (ROOT / "README.zh-CN.md").read_text(encoding="utf-8")

    assert "[简体中文](README.zh-CN.md)" in english
    assert "[English](README.md)" in chinese


def test_web_fonts_are_served_locally() -> None:
    styles = (ROOT / "web/src/styles.css").read_text(encoding="utf-8")

    assert "fonts.googleapis.com" not in styles
    assert "fonts.gstatic.com" not in styles
    assert (ROOT / "web/public/fonts/SpaceGrotesk-VariableFont_wght.ttf").is_file()
    assert (ROOT / "web/public/fonts/JetBrainsMono-VariableFont_wght.ttf").is_file()


def test_ci_checks_secrets_and_dependency_licenses() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "gitleaks/gitleaks-action@" in workflow
    assert "pull-requests: read" in workflow
    assert "uvx --from licensecheck licensecheck" in workflow
    assert "node scripts/check_licenses.mjs" in workflow
