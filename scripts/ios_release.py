#!/usr/bin/env python3
"""Preflight and archive the iOS wrapper without embedding signing secrets."""

from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios"
PROJECT = IOS / "TechnicalInterviewAgent.xcodeproj"
SCHEME = "TechnicalInterviewAgent"
BUNDLE_ID = "top.rainstone.technicalinterviewagent"
SITE_HOST = "it.rainstone.top"
TEAM_ID_PATTERN = re.compile(r"^[A-Z0-9]{10}$")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class ToolNotFoundError(RuntimeError):
    pass


def executable(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise ToolNotFoundError(f"Required command is unavailable: {name}")
    return path


@dataclass
class Check:
    name: str
    status: str
    detail: str


@dataclass
class Report:
    generated_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds")
    )
    mode: str = "preflight"
    project: str = str(PROJECT)
    site: str = f"https://{SITE_HOST}"
    bundle_id: str = BUNDLE_ID
    team_id: str | None = None
    checks: list[Check] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str) -> None:
        self.checks.append(Check(name=name, status=status, detail=detail))
        if status == "blocked":
            self.blockers.append(f"{name}: {detail}")

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ok"] = not self.blockers
        return data


def run(
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> CommandResult:
    if not command:
        raise ValueError("A command is required")
    args = [executable(command[0]), *command[1:]]
    try:
        completed = subprocess.run(  # noqa: S603
            args,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolNotFoundError(f"Required command is unavailable: {command[0]}") from exc
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_with_stdin(command: list[str], stdin: str) -> CommandResult:
    if not command:
        raise ValueError("A command is required")
    args = [executable(command[0]), *command[1:]]
    try:
        completed = subprocess.run(  # noqa: S603
            args,
            input=stdin,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise ToolNotFoundError(f"Required command is unavailable: {command[0]}") from exc
    return CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def command_output(command: list[str]) -> tuple[int, str]:
    result = run(command)
    output = (result.stdout + result.stderr).strip()
    return result.returncode, output


def xcode_available(report: Report) -> bool:
    if platform.system() != "Darwin":
        report.add("xcode", "blocked", "iOS builds require macOS with Xcode installed.")
        return False

    code, output = command_output(["xcode-select", "-p"])
    developer_dir = output.splitlines()[-1] if output else ""
    if code != 0 or not developer_dir.endswith("Xcode.app/Contents/Developer"):
        report.add(
            "xcode",
            "blocked",
            "Full Xcode is not selected; xcodebuild and the iOS SDK are unavailable.",
        )
        return False

    code, output = command_output(["xcodebuild", "-version"])
    if code != 0:
        report.add("xcode", "blocked", "xcodebuild is present but failed to report a version.")
        return False

    report.add("xcode", "pass", output.replace("\n", " · "))
    return True


def signing_identity_available(report: Report) -> bool:
    code, output = command_output(["security", "find-identity", "-v", "-p", "codesigning"])
    if code != 0:
        report.add(
            "codesigning_identity",
            "blocked",
            "The local code-signing Keychain is unavailable.",
        )
        return False

    identities = [
        line
        for line in output.splitlines()
        if "Apple Development:" in line or "Apple Distribution:" in line
    ]
    if not identities:
        report.add(
            "codesigning_identity",
            "blocked",
            "No valid Apple Development or Apple Distribution identity was found.",
        )
        return False

    report.add(
        "codesigning_identity",
        "pass",
        f"{len(identities)} valid Apple code-signing identity(s) found.",
    )
    return True


def profile_metadata(path: Path) -> dict[str, Any] | None:
    result = run(["security", "cms", "-D", "-i", str(path)])
    if result.returncode != 0:
        return None
    try:
        decoded = run_with_stdin(
            ["plutil", "-convert", "xml1", "-o", "-", "-"],
            result.stdout,
        )
        if decoded.returncode != 0:
            return None
        data = plistlib.loads(decoded.stdout.encode("utf-8"))
    except (plistlib.InvalidFileException, ValueError):
        return None
    return data if isinstance(data, dict) else None


def matching_profile(team_id: str) -> tuple[Path, dict[str, Any]] | None:
    directory = Path.home() / "Library/MobileDevice/Provisioning Profiles"
    if not directory.is_dir():
        return None

    for path in directory.glob("*.mobileprovision"):
        data = profile_metadata(path)
        if data is None:
            continue
        identifier = str(data.get("Entitlements", {}).get("application-identifier", ""))
        if not identifier.startswith(f"{team_id}."):
            continue
        if not identifier.endswith(f".{BUNDLE_ID}"):
            continue
        expiration = data.get("ExpirationDate")
        if isinstance(expiration, datetime) and expiration > datetime.now(UTC):
            return path, data
    return None


def validate_signing(report: Report, team_id: str | None) -> bool:
    if team_id is None:
        report.add(
            "development_team",
            "blocked",
            "Set APPLE_DEVELOPMENT_TEAM or APP_DEVELOPMENT_TEAM before signing.",
        )
        return False
    if not TEAM_ID_PATTERN.fullmatch(team_id):
        report.add(
            "development_team",
            "blocked",
            "The Apple Team ID must be exactly 10 uppercase letters or digits.",
        )
        return False
    report.team_id = team_id
    report.add("development_team", "pass", "A 10-character Apple Team ID is configured.")

    if not signing_identity_available(report):
        return False

    profile = matching_profile(team_id)
    if profile is None:
        report.add(
            "provisioning_profile",
            "blocked",
            f"No unexpired profile matching {team_id}.{BUNDLE_ID} is installed.",
        )
        return False
    path, _data = profile
    report.add(
        "provisioning_profile",
        "pass",
        f"Installed profile '{path.name}' matches the Team ID and Bundle ID.",
    )
    return True


def validate_project(report: Report) -> bool:
    required = (
        IOS / "Config/App.xcconfig",
        IOS / "TechnicalInterviewAgent/Info.plist",
        IOS / "TechnicalInterviewAgent/Resources/PrivacyInfo.xcprivacy",
        IOS / "TechnicalInterviewAgent/Assets.xcassets/AppIcon.appiconset/AppIcon-1024.png",
        PROJECT / "project.pbxproj",
        PROJECT / "xcshareddata/xcschemes" / f"{SCHEME}.xcscheme",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        report.add("project_files", "blocked", f"Missing: {', '.join(missing)}")
        return False
    report.add("project_files", "pass", "Project, shared scheme, plist, privacy and icon exist.")

    result = run(["plutil", "-lint", str(required[1]), str(required[2])])
    if result.returncode != 0:
        report.add("property_lists", "blocked", (result.stdout + result.stderr).strip())
        return False
    report.add("property_lists", "pass", "Info.plist and PrivacyInfo.xcprivacy parse successfully.")
    return True


def validate_web(report: Report) -> bool:
    result = run(["npm", "run", "build"], cwd=ROOT / "web")
    if result.returncode != 0:
        report.add(
            "web_build",
            "blocked",
            "Web build failed; see the command output in the terminal.",
        )
        return False
    report.add("web_build", "pass", "React/Vite production bundle built successfully.")

    if shutil.which("curl") is None:
        report.add(
            "site_reachability",
            "warn",
            "curl is unavailable; reachability was not checked.",
        )
        return True

    result = run(
        [
            "curl",
            "--silent",
            "--show-error",
            "--fail",
            "--head",
            "--max-time",
            "20",
            f"https://{SITE_HOST}/",
        ]
    )
    if result.returncode != 0:
        report.add(
            "site_reachability",
            "blocked",
            f"HTTPS site did not answer successfully: {result.stderr.strip()}",
        )
        return False
    report.add("site_reachability", "pass", f"HTTPS site https://{SITE_HOST}/ is reachable.")
    return True


def archive(
    report: Report,
    team_id: str,
    *,
    build_number: int | None,
) -> Path | None:
    archive_path = IOS / "build/TechnicalInterviewAgent.xcarchive"
    derived_data = IOS / "build/DerivedData"
    build_dir = IOS / "build"
    build_dir.mkdir(parents=True, exist_ok=True)

    command = [
        "xcodebuild",
        "-project",
        str(PROJECT),
        "-scheme",
        SCHEME,
        "-configuration",
        "Release",
        "-destination",
        "generic/platform=iOS",
        "-archivePath",
        str(archive_path),
        "-derivedDataPath",
        str(derived_data),
        "DEVELOPMENT_TEAM=" + team_id,
        "CODE_SIGN_STYLE=Automatic",
    ]
    if build_number is not None:
        command.append(f"APP_BUILD_NUMBER={build_number}")
    command.append("archive")

    result = run(command)
    if result.returncode != 0:
        report.add(
            "archive",
            "blocked",
            f"xcodebuild archive failed: {(result.stdout + result.stderr).strip()[-2000:]}",
        )
        return None

    report.add("archive", "pass", f"Archive written to {archive_path.relative_to(ROOT)}.")
    report.artifacts.append(str(archive_path.relative_to(ROOT)))
    return archive_path


def export_archive(
    report: Report,
    archive_path: Path,
) -> None:
    export_options = IOS / "ExportOptions.plist"
    example = IOS / "ExportOptions.plist.example"
    if not export_options.is_file():
        shutil.copyfile(example, export_options)
    shutil.copymode(example, export_options)

    export_path = IOS / "build/export"
    export_path.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            "xcodebuild",
            "-exportArchive",
            "-archivePath",
            str(archive_path),
            "-exportPath",
            str(export_path),
            "-exportOptionsPlist",
            str(export_options),
            "-allowProvisioningUpdates",
        ]
    )
    if result.returncode != 0:
        report.add(
            "export",
            "blocked",
            f"App Store export failed: {(result.stdout + result.stderr).strip()[-2000:]}",
        )
        return
    report.add("export", "pass", f"App Store IPA exported to {export_path.relative_to(ROOT)}.")
    report.artifacts.append(str(export_path.relative_to(ROOT)))

    report.add(
        "app_store_upload",
        "blocked",
        "IPA export is ready. Upload it locally with Xcode Organizer or an "
        "authenticated App Store Connect tool after checking the current Apple CLI syntax.",
    )


def resolve_team(cli_team: str | None) -> str | None:
    if cli_team:
        return cli_team.strip()
    for variable in ("APPLE_DEVELOPMENT_TEAM", "APP_DEVELOPMENT_TEAM"):
        value = os.environ.get(variable, "").strip()
        if value:
            return value
    xcconfig = IOS / "Config/Signing.xcconfig"
    if not xcconfig.is_file():
        return None
    for line in xcconfig.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\s*APP_DEVELOPMENT_TEAM\s*=\s*(\S+)\s*", line)
        if match and not match.group(1).startswith("REPLACE_"):
            return match.group(1)
    return None


def print_report(report: Report, output: Path | None) -> None:
    data = report.as_dict()
    rendered = json.dumps(data, ensure_ascii=False, indent=2)
    print(rendered)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("preflight", "archive", "release"),
        default="preflight",
    )
    parser.add_argument("--team-id", help="Apple Developer Team ID, 10 uppercase characters.")
    parser.add_argument(
        "--build-number",
        type=int,
        help="Optional monotonically increasing build number.",
    )
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = Report(mode=args.mode)
    team_id = resolve_team(args.team_id)
    validate_project(report)
    validate_web(report)

    xcode_ready = xcode_available(report)
    if xcode_ready:
        result = run(["xcodebuild", "-list", "-project", str(PROJECT)])
        if result.returncode == 0 and SCHEME in result.stdout:
            report.add("xcode_project", "pass", "Xcode recognizes the shared app scheme.")
        else:
            report.add("xcode_project", "blocked", "Xcode did not recognize the app scheme.")

    signing_ready = xcode_ready and validate_signing(report, team_id)
    if not team_id:
        report.add(
            "app_store_connect",
            "blocked",
            "App Store Connect app record and store metadata were not supplied.",
        )

    if args.mode in {"archive", "release"} and signing_ready:
        archive_path = archive(report, team_id or "", build_number=args.build_number)
        if (
            args.mode == "release"
            and archive_path is not None
            and archive_path.is_dir()
            and not any(
                check.status == "blocked" and check.name != "app_store_upload"
                for check in report.checks
            )
        ):
            export_archive(report, archive_path)
    elif args.mode in {"archive", "release"}:
        report.add(
            "signed_build",
            "blocked",
            "Signing prerequisites are incomplete; no signed archive was attempted.",
        )

    print_report(report, args.report)
    if args.mode == "preflight":
        return 0
    return 0 if not report.blockers else 1


if __name__ == "__main__":
    sys.exit(main())
