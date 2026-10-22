"""Favicon source and browser integration contracts."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


def test_favicon_assets_cover_browser_mobile_and_windows() -> None:
    public = WEB / "public"

    assert (public / "favicon.svg").read_text(encoding="utf-8").startswith("<svg")
    assert (public / "favicon-32.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (public / "favicon-192.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert (public / "apple-touch-icon.png").read_bytes().startswith(
        b"\x89PNG\r\n\x1a\n"
    )
    assert (public / "favicon.ico").read_bytes().startswith(b"\x00\x00\x01\x00")
    assert '"short_name": "Interview"' in (public / "site.webmanifest").read_text(
        encoding="utf-8"
    )


def test_index_declares_favicon_and_application_manifest() -> None:
    index = (WEB / "index.html").read_text(encoding="utf-8")

    for fragment in (
        'rel="icon" type="image/svg+xml" href="/favicon.svg"',
        'rel="icon" type="image/x-icon" href="/favicon.ico"',
        'rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png"',
        'rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"',
        'rel="manifest" href="/site.webmanifest"',
    ):
        assert fragment in index


def test_auth_and_app_shell_reuse_the_favicon_brand_mark() -> None:
    app_shell = (WEB / "src/components/AppShell.tsx").read_text(encoding="utf-8")
    styles = (WEB / "src/styles.css").read_text(encoding="utf-8")

    assert app_shell.count('src="/favicon.svg"') == 2
    assert ".brand-mark img {" in styles
