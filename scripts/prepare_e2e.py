"""Seed deterministic interview history for a registered E2E account."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC, datetime, timedelta

from app.config import Settings
from app.db.models import Interview, User
from app.db.session import create_engine, create_session_factory
from app.security import normalize_email
from sqlalchemy import select

DIRECTIONS = ("backend", "frontend", "fullstack")
HISTORY_COUNT = 12
_NAMESPACE = uuid.UUID("6c9f9255-632e-4a20-a8f7-25c65914f9be")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create deterministic history rows for one existing E2E user."
    )
    parser.add_argument("email", help="Email of the account created through the E2E UI.")
    return parser


async def _prepare(email: str, settings: Settings) -> int:
    engine = create_engine(settings)
    factory = create_session_factory(engine)
    normalized = normalize_email(email)
    try:
        async with factory() as session:
            user = (
                await session.execute(select(User).where(User.email_normalized == normalized))
            ).scalar_one_or_none()
            if user is None:
                raise LookupError("registered E2E user was not found")

            created = 0
            for index in range(HISTORY_COUNT):
                interview_id = uuid.uuid5(_NAMESPACE, f"{normalized}:{index}")
                existing = await session.get(Interview, interview_id)
                if existing is not None:
                    continue
                ended_at = datetime(2026, 10, 1, 8, tzinfo=UTC) + timedelta(minutes=index)
                session.add(
                    Interview(
                        id=interview_id,
                        owner_user_id=user.id,
                        direction=DIRECTIONS[index % len(DIRECTIONS)],
                        difficulty_profile={
                            "easy": 1,
                            "medium": 2,
                            "hard": 2,
                        },
                        topic_keys={
                            "primary": f"e2e-topic-{index % 4}",
                            "supporting": ["systems", "problem-solving"],
                        },
                        state="completed",
                        main_question_count=5,
                        total_token_budget=20_000,
                        total_tokens_used=3200 + index * 10,
                        started_at=ended_at - timedelta(minutes=35),
                        ended_at=ended_at,
                        end_reason="completed",
                        blueprint_version="e2e-blueprint@1.0.0",
                        scoring_version="e2e-scoring@1.0.0",
                        created_at=ended_at - timedelta(minutes=40),
                        expires_at=ended_at + timedelta(days=90),
                    )
                )
                created += 1
            await session.commit()
            return created
    finally:
        await engine.dispose()


def main() -> int:
    args = _parser().parse_args()
    try:
        created = asyncio.run(_prepare(args.email, Settings()))
    except LookupError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"prepared {HISTORY_COUNT} deterministic interview history rows ({created} new)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
