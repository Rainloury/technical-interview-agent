"""Account, session, CSRF, dashboard, and history API tests."""

from __future__ import annotations

from http.cookies import SimpleCookie
from typing import Any

import pytest
from app.config import Settings
from app.db.models import AsyncJob, AuditEvent, PasswordResetToken, User
from app.prompts.loader import PromptLoader
from app.services.auth import set_user_role
from app.worker import ResumeWorker
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import AppHarness

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery staple"
WRITE_HEADERS = {"Origin": "https://testserver"}


def _login(client: TestClient, email: str, password: str = PASSWORD) -> Any:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers=WRITE_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response


def _csrf(client: TestClient) -> str:
    return client.cookies.get("interview_csrf") or ""


def _write_headers(client: TestClient) -> dict[str, str]:
    return {**WRITE_HEADERS, "X-CSRF-Token": _csrf(client)}


def _cookie_attributes(response: Any) -> dict[str, Any]:
    cookies: dict[str, Any] = {}
    for header in response.headers.get_list("set-cookie"):
        parsed = SimpleCookie()
        parsed.load(header)
        cookies.update(parsed)
    return cookies


async def test_register_is_neutral_and_never_sets_a_cookie(
    app_client: AppHarness, create_user: Any
) -> None:
    user = create_user("existing@example.com")
    async with app_client.session_factory() as session:
        session.add(user)
        await session.commit()

    client = app_client.client
    fresh = client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": PASSWORD},
        headers=WRITE_HEADERS,
    )
    assert fresh.status_code == 202
    assert fresh.json() == {"accepted": True, "next_action": "login"}
    assert "set-cookie" not in fresh.headers

    existing = client.post(
        "/api/v1/auth/register",
        json={"email": " EXISTING@example.com ", "password": PASSWORD},
        headers=WRITE_HEADERS,
    )
    assert existing.status_code == 202
    assert existing.json() == fresh.json()
    assert "set-cookie" not in existing.headers


async def test_login_cookie_session_and_logout(app_client: AppHarness, create_user: Any) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("owner@example.com"))
        await session.commit()

    client = app_client.client
    login = _login(client, "owner@example.com")
    body = login.json()
    assert body["user"]["display_name"] == "示例用户"
    assert body["user"]["role"] == "user"
    assert "token" not in login.text.lower()
    assert "session_token" not in login.text
    cookies = _cookie_attributes(login)
    assert cookies["interview_session"]["httponly"] is True
    assert cookies["interview_session"]["secure"] is True
    assert cookies["interview_session"]["samesite"] == "lax"
    raw_csrf = next(
        header
        for header in login.headers.get_list("set-cookie")
        if header.startswith("interview_csrf=")
    )
    assert "httponly" not in raw_csrf.lower()
    assert cookies["interview_csrf"]["secure"] is True

    session_response = client.get("/api/v1/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"] == body["user"]

    rejected = client.post("/api/v1/auth/logout", headers=WRITE_HEADERS)
    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "csrf_rejected"

    logout = client.post("/api/v1/auth/logout", headers=_write_headers(client))
    assert logout.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401


async def test_session_and_dashboard_include_current_role(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("admin-role@example.com", role="admin"))
        await session.commit()

    client = app_client.client
    login = _login(client, "admin-role@example.com")
    assert login.json()["user"]["role"] == "admin"

    session_response = client.get("/api/v1/auth/session")
    assert session_response.status_code == 200
    assert session_response.json()["user"]["role"] == "admin"

    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.json()["user"]["role"] == "admin"


async def test_set_role_updates_active_user_and_writes_audit(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("promote@example.com"))
        await session.commit()

    async with app_client.session_factory() as session:
        result = await set_user_role(
            session,
            email=" PROMOTE@example.com ",
            role="admin",
            request_id="role-test",
        )
        await session.commit()

    async with app_client.session_factory() as session:
        user = (
            await session.execute(
                select(User).where(User.email_normalized == "promote@example.com")
            )
        ).scalar_one()
        audit = (
            await session.execute(
                select(AuditEvent).where(AuditEvent.action == "user_role_changed")
            )
        ).scalar_one()
    assert result.previous_role == "user"
    assert result.current_role == "admin"
    assert user.role == "admin"
    assert audit.result == "success"
    assert audit.request_id == "role-test"


async def test_set_role_rejects_unknown_and_inactive_users(
    app_client: AppHarness,
    create_user: Any,
) -> None:
    inactive = create_user("inactive-role@example.com")
    inactive.status = "suspended"
    async with app_client.session_factory() as session:
        session.add(inactive)
        await session.commit()

    async with app_client.session_factory() as session:
        with pytest.raises(Exception, match="用户不存在"):
            await set_user_role(
                session,
                email="missing@example.com",
                role="admin",
                request_id="role-missing",
            )
        with pytest.raises(Exception, match="用户不存在"):
            await set_user_role(
                session,
                email="inactive-role@example.com",
                role="admin",
                request_id="role-inactive",
            )


async def test_cross_origin_write_is_rejected(app_client: AppHarness) -> None:
    response = app_client.client.post(
        "/api/v1/auth/register",
        json={"email": "origin@example.com", "password": PASSWORD},
        headers={"Origin": "https://attacker.example"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_rejected"


async def test_dashboard_and_history_are_owner_scoped_and_paginated(
    app_client: AppHarness, create_user: Any, create_activity: Any
) -> None:
    owner = create_user("owner@example.com")
    stranger = create_user("stranger@example.com")

    async with app_client.session_factory() as session:
        session.add_all([owner, stranger])
        await session.flush()
        owner_older = create_activity(owner, suffix="owner-older", day=1)
        owner_newer = create_activity(owner, suffix="owner-newer", day=2)
        stranger_activity = create_activity(stranger, suffix="stranger", day=3)
        for activity in (owner_older, owner_newer, stranger_activity):
            session.add_all(activity)
        await session.commit()

    client = app_client.client
    _login(client, "owner@example.com")
    dashboard = client.get("/api/v1/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.json()
    assert payload["user"]["display_name"] == "示例用户"
    assert len(payload["recent_tasks"]) == 4
    assert len(payload["recent_interviews"]) == 2
    assert all("stranger" not in item["title"] for item in payload["recent_tasks"])

    first = client.get(
        "/api/v1/history",
        params={"type": "interview", "limit": 1},
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert len(first_payload["items"]) == 1
    assert first_payload["items"][0]["id"] == str(owner_newer[2].id)
    assert first_payload["next_cursor"]

    second = client.get(
        "/api/v1/history",
        params={
            "type": "interview",
            "limit": 1,
            "cursor": first_payload["next_cursor"],
        },
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert [item["id"] for item in second_payload["items"]] == [str(owner_older[2].id)]
    assert second_payload["next_cursor"] is None
    assert str(stranger_activity[2].id) not in {
        item["id"] for item in first_payload["items"] + second_payload["items"]
    }

    invalid = client.get("/api/v1/history", params={"type": "interview", "cursor": "bad"})
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "invalid_request"


async def test_password_reset_is_neutral_and_revokes_sessions(
    app_client: AppHarness,
    create_user: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = create_user("reset@example.com")
    async with app_client.session_factory() as session:
        session.add(user)
        await session.commit()

    client = app_client.client
    _login(client, "reset@example.com")
    accepted = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "missing@example.com"},
        headers=WRITE_HEADERS,
    )
    assert accepted.status_code == 202
    assert accepted.json() == {"accepted": True}

    async with app_client.session_factory() as session:
        assert (await session.execute(select(PasswordResetToken))).scalar_one_or_none() is None

    reset_request = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "reset@example.com"},
        headers=WRITE_HEADERS,
    )
    assert reset_request.status_code == 202
    assert reset_request.json() == {"accepted": True}

    async with app_client.session_factory() as session:
        reset = (await session.execute(select(PasswordResetToken))).scalar_one()
        queued = (
            await session.execute(
                select(AsyncJob).where(AsyncJob.job_type == "password_reset_delivery")
            )
        ).scalar_one()
        ciphertext = reset.delivery_ciphertext
        reset_id = reset.id
    assert queued.resource_id == reset_id
    assert queued.state == "queued"
    assert ciphertext is not None
    delivered: list[str] = []

    async def capture_delivery(settings: Settings, *, email: str, token: str) -> None:
        del settings, email
        delivered.append(token)

    monkeypatch.setattr("app.worker.deliver_password_reset", capture_delivery)

    async def run_delivery() -> None:
        worker = ResumeWorker(
            settings=app_client.app.state.settings,
            session_factory=app_client.session_factory,
            storage=app_client.app.state.resume_storage,
            llm=Any,  # type: ignore[arg-type]
            prompt_loader=PromptLoader(app_client.app.state.settings.prompt_dir),
            worker_id="reset-delivery-worker",
        )
        result = await worker.run_once()
        assert result.outcome == "succeeded"

    await run_delivery()
    assert len(delivered) == 1

    async with app_client.session_factory() as session:
        stored_reset = await session.get(PasswordResetToken, reset_id)
        assert stored_reset is not None
        assert stored_reset.delivery_ciphertext is None

    confirmed = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": delivered[0], "new_password": NEW_PASSWORD},
        headers=WRITE_HEADERS,
    )
    assert confirmed.status_code == 204
    assert client.get("/api/v1/auth/session").status_code == 401

    replay = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={"token": delivered[0], "new_password": NEW_PASSWORD},
        headers=WRITE_HEADERS,
    )
    assert replay.status_code == 410
    assert replay.json()["error"]["code"] == "reset_token_invalid"

    new_login = client.post(
        "/api/v1/auth/login",
        json={"email": "reset@example.com", "password": NEW_PASSWORD},
        headers=WRITE_HEADERS,
    )
    assert new_login.status_code == 200


async def test_empty_workspace_returns_empty_collections(
    app_client: AppHarness, create_user: Any
) -> None:
    async with app_client.session_factory() as session:
        session.add(create_user("empty@example.com"))
        await session.commit()

    client = app_client.client
    _login(client, "empty@example.com")
    payload = client.get("/api/v1/dashboard").json()
    assert payload["recent_tasks"] == []
    assert payload["recent_interviews"] == []
