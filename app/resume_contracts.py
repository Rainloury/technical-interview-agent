"""Structured LLM contracts for resume analysis and question generation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    level: Literal["basic", "intermediate", "advanced"] = "intermediate"
    evidence_ids: list[str] = Field(min_length=1)


class ProjectEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    role: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(min_length=1)


class ResumeEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=1, max_length=200)
    capability_tags: list[str] = Field(default_factory=list)


class ResumeAnalysisOutput(BaseModel):
    """Provider-neutral resume analysis schema."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    analysis_version: str = Field(default="1.0.0", min_length=1, max_length=40)
    skills: list[SkillEvidence] = Field(default_factory=list)
    projects: list[ProjectEvidence] = Field(default_factory=list)
    evidence: list[ResumeEvidence] = Field(min_length=1)
    unverified_items: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_evidence_links(self) -> ResumeAnalysisOutput:
        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")
        known = set(evidence_ids)
        linked: set[str] = set()
        for skill in self.skills:
            linked.update(skill.evidence_ids)
        for project in self.projects:
            linked.update(project.evidence_ids)
        if not linked <= known:
            raise ValueError("every evidence link must reference a known evidence ID")
        return self


class GeneratedQuestionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1, le=10)
    question_text: str = Field(min_length=1, max_length=1000)
    category: str = Field(min_length=1, max_length=80)
    difficulty: Literal["easy", "medium", "hard"]
    topic_key: str = Field(min_length=1, max_length=120)
    assessment_points: list[str] = Field(min_length=1)
    reference_answer: str = Field(min_length=1, max_length=4000)
    scoring_rubric: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class ResumeQuestionsOutput(BaseModel):
    """Strict fixed-size question-set contract."""

    model_config = ConfigDict(extra="forbid")

    questions: list[GeneratedQuestionOutput]

    @model_validator(mode="after")
    def validate_question_set(self) -> ResumeQuestionsOutput:
        if len(self.questions) != 10:
            raise ValueError("exactly 10 questions are required")
        if [item.sequence for item in self.questions] != list(range(1, 11)):
            raise ValueError("question sequences must be 1 through 10")
        counts = {
            difficulty: sum(item.difficulty == difficulty for item in self.questions)
            for difficulty in ("easy", "medium", "hard")
        }
        if counts != {"easy": 3, "medium": 5, "hard": 2}:
            raise ValueError("difficulty mix must be 3 easy, 5 medium, and 2 hard")
        topic_keys = [item.topic_key for item in self.questions]
        if len(topic_keys) != len(set(topic_keys)):
            raise ValueError("topic keys must be unique")
        return self
