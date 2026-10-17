"""Structured QA answer contract and deterministic lexical retrieval."""

from __future__ import annotations

import math
import re
import uuid
from collections import Counter
from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    KnowledgeSource,
    KnowledgeSourceSection,
    KnowledgeSourceVersion,
)

_TOKEN_PATTERN = re.compile(r"[a-zA-Z0-9_+#.-]+|[\u4e00-\u9fff]")
_URL_PATTERN = re.compile(
    r"(?ix)"
    r"(?:\b[a-z][a-z0-9+.-]*://\S+)"
    r"|(?<![\w.-])(?:www\.)[a-z0-9.-]+\.[a-z]{2,63}(?::\d{1,5})?(?:[/?#]\S*)?"
    r"|(?<![\w.-])localhost(?::\d{1,5})?(?:[/?#]\S*)?"
    r"|(?<![\w.-])"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
    r"(?:\.(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}"
    r"(?::\d{1,5})?(?:[/?#]\S*)?"
    r"|(?<![\w.-])"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"(?:[a-z]{2,63}|xn--[a-z0-9-]{2,59})"
    r"(?::\d{1,5})?(?:[/?#]\S*)?"
)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "why",
        "with",
        "如何",
        "什么",
        "怎么",
        "以及",
        "一个",
        "进行",
        "可以",
        "需要",
    }
)


class QaAnswerOutput(BaseModel):
    """Provider-neutral answer shape shared by Worker and API."""

    model_config = ConfigDict(extra="forbid")

    direct_answer: str = Field(min_length=1, max_length=2000)
    explanation: str = Field(min_length=1, max_length=6000)
    evidence_ids: list[str] = Field(default_factory=list)
    extended_questions: list[str] = Field(default_factory=list, max_length=5)
    evidence_status: Literal["supported", "model_knowledge", "insufficient"]

    @model_validator(mode="after")
    def validate_evidence_state(self) -> QaAnswerOutput:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        if self.evidence_status == "supported" and not self.evidence_ids:
            raise ValueError("supported answers must cite evidence")
        if self.evidence_status in {"model_knowledge", "insufficient"} and self.evidence_ids:
            raise ValueError(f"{self.evidence_status} answers must not cite evidence")
        return self


@dataclass(frozen=True, slots=True)
class RetrievedEvidence:
    """One ranked section snapshot before persistence."""

    knowledge_source_version_id: uuid.UUID
    source_title: str
    section_path: str
    snippet: str
    relevance_score: float
    position: dict[str, int | str]


def contains_url(value: str) -> bool:
    """Reject caller-supplied locations from becoming knowledge sources."""

    return _URL_PATTERN.search(value) is not None


def tokenize(value: str) -> list[str]:
    """Use a deterministic, dependency-free tokenizer for Chinese and English."""

    tokens = [token.casefold() for token in _TOKEN_PATTERN.findall(value)]
    return [token for token in tokens if token not in _STOPWORDS]


def _snippet(content: str, terms: set[str]) -> str:
    compact = re.sub(r"\s+", " ", content).strip()
    if len(compact) <= 200:
        return compact
    positions = [
        compact.casefold().find(term.casefold())
        for term in terms
        if compact.casefold().find(term.casefold()) >= 0
    ]
    center = min(positions) if positions else 0
    start = max(0, min(center - 60, len(compact) - 200))
    return compact[start : start + 200]


def _score(question_terms: list[str], content: str) -> float:
    if not question_terms:
        return 0.0
    counts = Counter(tokenize(content))
    unique = set(question_terms)
    matched = sum(1 for term in unique if counts[term])
    if matched == 0:
        return 0.0
    frequency = sum(min(counts[term], 3) for term in unique)
    coverage = matched / len(unique)
    return min(1.0, 0.7 * coverage + 0.3 * (math.log1p(frequency) / math.log1p(3 * len(unique))))


async def retrieve_evidence(
    session: AsyncSession,
    *,
    question: str,
    limit: int = 5,
) -> list[RetrievedEvidence]:
    """Rank the latest published allowlisted sections with stable lexical scoring."""

    terms = tokenize(question)
    if not terms:
        return []
    latest = (
        select(
            KnowledgeSourceVersion.id.label("version_id"),
            KnowledgeSourceVersion.source_id.label("source_id"),
        )
        .where(KnowledgeSourceVersion.status == "published")
        .distinct(KnowledgeSourceVersion.source_id)
        .order_by(
            KnowledgeSourceVersion.source_id,
            KnowledgeSourceVersion.published_at.desc(),
            KnowledgeSourceVersion.id.desc(),
        )
        .subquery()
    )
    rows = (
        await session.execute(
            select(
                KnowledgeSourceSection,
                KnowledgeSourceVersion.id,
                KnowledgeSource.title,
            )
            .join(latest, latest.c.version_id == KnowledgeSourceSection.version_id)
            .join(
                KnowledgeSourceVersion,
                KnowledgeSourceVersion.id == KnowledgeSourceSection.version_id,
            )
            .join(KnowledgeSource, KnowledgeSource.id == KnowledgeSourceVersion.source_id)
            .where(
                KnowledgeSource.allowlisted.is_(True),
                KnowledgeSourceVersion.status == "published",
            )
        )
    ).all()
    ranked: list[RetrievedEvidence] = []
    for section, version_id, title in rows:
        score = _score(terms, section.content)
        if score <= 0:
            continue
        ranked.append(
            RetrievedEvidence(
                knowledge_source_version_id=version_id,
                source_title=title,
                section_path=section.section_path,
                snippet=_snippet(section.content, set(terms)),
                relevance_score=round(score, 4),
                position={"section_index": section.section_index},
            )
        )
    ranked.sort(
        key=lambda item: (
            -item.relevance_score,
            item.source_title,
            item.section_path,
            str(item.knowledge_source_version_id),
        )
    )
    selected = ranked[:limit]
    return [
        RetrievedEvidence(
            knowledge_source_version_id=item.knowledge_source_version_id,
            source_title=item.source_title,
            section_path=item.section_path,
            snippet=item.snippet,
            relevance_score=item.relevance_score,
            position={
                "rank": rank,
                "citation_id": f"evidence-{rank}",
                "section_index": cast(int, item.position["section_index"]),
            },
        )
        for rank, item in enumerate(selected, start=1)
    ]
