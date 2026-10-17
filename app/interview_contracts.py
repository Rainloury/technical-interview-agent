"""Deterministic interview configuration and structured LLM contracts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Direction = Literal["backend", "frontend", "fullstack"]
Difficulty = Literal["easy", "medium", "hard"]
DifficultyProfile = Literal["foundation", "balanced", "challenge"]
ScoreBand = Literal["below_70", "70_84", "85_plus"]

INTERVIEW_MAIN_QUESTION_COUNT = 5
INTERVIEW_DURATION_SECONDS = 40 * 60
INTERVIEW_TOTAL_TOKEN_BUDGET = 200_000
INTERVIEW_CHAIN_TOKEN_BUDGET = 30_000
INTERVIEW_BLUEPRINT_VERSION = "2026-10-18.1"
INTERVIEW_SCORING_VERSION = "1.0.0"
INTERVIEW_REPORT_VERSION = "1.0.0"
INTERVIEW_PROMPT_VERSION = "1.0.0"

SCORE_WEIGHTS: dict[str, int] = {
    "correctness": 35,
    "technical_depth": 25,
    "engineering_judgment": 20,
    "completeness": 10,
    "clarity": 10,
}


@dataclass(frozen=True, slots=True)
class Topic:
    key: str
    title: str
    capability: str
    anchors: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DirectionPlan:
    topics: tuple[Topic, ...]
    l3: frozenset[str]


@dataclass(frozen=True, slots=True)
class BlueprintQuestion:
    sequence: int
    topic_key: str
    topic_title: str
    capability: str
    difficulty: Difficulty
    anchors: tuple[str, ...]
    seed: int


DIRECTION_PLANS: dict[Direction, DirectionPlan] = {
    "backend": DirectionPlan(
        topics=(
            Topic(
                "api_idempotency",
                "HTTP/API 与幂等",
                "设计可重复调用且不产生重复副作用的接口",
                ("幂等键生命周期", "唯一约束", "并发重放", "响应回放"),
            ),
            Topic(
                "runtime_concurrency",
                "运行时与并发",
                "定位并发瓶颈并选择正确的隔离策略",
                ("事件循环阻塞", "连接池", "锁粒度", "背压"),
            ),
            Topic(
                "db_transactions",
                "数据库、事务与索引",
                "保证事务正确性并解释隔离级别影响",
                ("隔离级别", "死锁", "索引选择", "迁移兼容"),
            ),
            Topic(
                "cache_consistency",
                "缓存与一致性",
                "在命中率、一致性和故障恢复之间取舍",
                ("缓存失效", "双写", "穿透雪崩", "最终一致"),
            ),
            Topic(
                "async_retry",
                "消息与异步重试",
                "设计至少一次投递下的可靠消费链路",
                ("重复消费", "退避抖动", "死信队列", "可观测性"),
            ),
            Topic(
                "auth_security",
                "认证与安全",
                "识别会话、权限和输入信任边界",
                ("CSRF", "会话撤销", "最小权限", "不可信输入"),
            ),
            Topic(
                "observability",
                "可观测性与排障",
                "通过指标、日志和 trace 定位线上故障",
                ("SLI", "trace 关联", "日志脱敏", "告警阈值"),
            ),
            Topic(
                "service_reliability",
                "服务设计与可用性",
                "设计有界失败和可恢复的服务调用",
                ("超时预算", "熔断", "降级", "容量估算"),
            ),
        ),
        l3=frozenset({"api_idempotency", "db_transactions", "cache_consistency"}),
    ),
    "frontend": DirectionPlan(
        topics=(
            Topic(
                "responsive_a11y",
                "HTML/CSS、响应式与无障碍",
                "构建可访问且跨视口稳定的界面",
                ("语义化", "焦点管理", "响应式布局", "对比度"),
            ),
            Topic(
                "event_loop",
                "JS/TS 与事件循环",
                "解释异步执行顺序并避免主线程阻塞",
                ("微任务", "宏任务", "长任务", "取消"),
            ),
            Topic(
                "component_state",
                "组件状态与数据流",
                "设计可预测、可恢复的组件状态",
                ("状态提升", "派生状态", "竞态请求", "缓存失效"),
            ),
            Topic(
                "browser_network_security",
                "浏览器网络与安全",
                "处理同源、凭据、CSRF 和 XSS 边界",
                ("CORS", "Cookie", "CSRF", "内容注入"),
            ),
            Topic(
                "render_performance",
                "渲染性能",
                "定位渲染瓶颈并选择可测量的优化",
                ("重渲染", "虚拟列表", "布局抖动", "性能预算"),
            ),
            Topic(
                "form_errors",
                "表单与错误状态",
                "设计完整校验、提交和失败恢复体验",
                ("即时校验", "幂等提交", "错误聚焦", "乐观更新"),
            ),
            Topic(
                "testing_debugging",
                "测试与调试",
                "用分层测试覆盖真实用户路径",
                ("单元边界", "集成测试", "网络模拟", "可诊断日志"),
            ),
            Topic(
                "build_cache",
                "构建与缓存",
                "在首屏、缓存命中和发布一致性之间取舍",
                ("代码分割", "缓存键", "资源指纹", "回滚"),
            ),
        ),
        l3=frozenset({"event_loop", "render_performance", "browser_network_security"}),
    ),
    "fullstack": DirectionPlan(
        topics=(
            Topic(
                "api_contract",
                "API 契约与校验",
                "让前后端共享稳定、可演进的接口契约",
                ("DTO", "兼容演进", "错误结构", "边界校验"),
            ),
            Topic(
                "auth_session",
                "认证与会话",
                "贯通浏览器、网关和服务端的身份链路",
                ("Cookie 属性", "会话撤销", "CSRF", "权限边界"),
            ),
            Topic(
                "data_modeling",
                "数据建模与事务",
                "从用户流程推导数据约束和事务边界",
                ("唯一约束", "状态机", "一致性", "迁移"),
            ),
            Topic(
                "state_sync",
                "前后端状态同步",
                "处理缓存、刷新和并发更新的冲突",
                ("乐观更新", "版本号", "轮询恢复", "冲突合并"),
            ),
            Topic(
                "async_consistency",
                "异步任务与最终一致性",
                "设计跨请求、跨服务的可恢复任务",
                ("租约", "幂等消费", "重试", "状态查询"),
            ),
            Topic(
                "e2e_errors",
                "端到端错误与重试",
                "把失败恢复设计成完整用户路径",
                ("错误映射", "重连", "幂等重试", "降级提示"),
            ),
            Topic(
                "e2e_performance",
                "端到端性能与缓存",
                "从浏览器到数据库定位性能瓶颈",
                ("缓存层", "预算", "慢查询", "首屏"),
            ),
            Topic(
                "deployment_observability",
                "部署、安全与可观测性",
                "设计可发布、可回滚、可追踪的部署",
                ("不可信输入", "请求 ID", "指标", "回滚"),
            ),
        ),
        l3=frozenset({"auth_session", "state_sync", "e2e_errors"}),
    ),
}


def normalize_topic_keys(direction: Direction, values: list[str]) -> list[str]:
    """Validate, deduplicate, and preserve caller order for topic preferences."""

    known = {topic.key for topic in DIRECTION_PLANS[direction].topics}
    normalized: list[str] = []
    for value in values:
        key = value.strip()
        if not key:
            raise ValueError("topic keys must not be blank")
        if key not in known:
            raise ValueError(f"unsupported topic key for {direction}: {key}")
        if key not in normalized:
            normalized.append(key)
    return normalized


def difficulty_mix(profile: DifficultyProfile) -> tuple[Difficulty, ...]:
    """Return the frozen five-question difficulty distribution."""

    if profile == "foundation":
        return ("easy", "easy", "medium", "medium", "hard")
    if profile == "challenge":
        return ("medium", "medium", "medium", "hard", "hard")
    return ("easy", "medium", "medium", "medium", "hard")


def build_blueprint(
    *,
    direction: Direction,
    difficulty: DifficultyProfile,
    topic_keys: list[str],
    interview_id: str,
) -> list[BlueprintQuestion]:
    """Create a deterministic five-topic blueprint with at least four topics."""

    plan = DIRECTION_PLANS[direction]
    digest = hashlib.sha256(interview_id.encode("utf-8")).digest()
    ordered = list(plan.topics)
    offset = digest[0] % len(ordered)
    ordered = ordered[offset:] + ordered[:offset]
    selected: list[Topic] = []
    for key in topic_keys:
        selected.append(next(topic for topic in ordered if topic.key == key))
    for topic in ordered:
        if topic not in selected:
            selected.append(topic)
        if len(selected) == INTERVIEW_MAIN_QUESTION_COUNT:
            break
    mix = difficulty_mix(difficulty)
    return [
        BlueprintQuestion(
            sequence=index,
            topic_key=topic.key,
            topic_title=topic.title,
            capability=topic.capability,
            difficulty=mix[index - 1],
            anchors=topic.anchors,
            seed=digest[index] if index < len(digest) else index,
        )
        for index, topic in enumerate(selected[:INTERVIEW_MAIN_QUESTION_COUNT], start=1)
    ]


class InterviewQuestionDraft(BaseModel):
    """One generated question with protected scoring material."""

    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(min_length=1, max_length=1200)
    reference_answer: str = Field(min_length=1, max_length=5000)
    scoring_rubric: list[str] = Field(min_length=1, max_length=12)


class InterviewQuestionsOutput(BaseModel):
    """Exactly five ordered main-question drafts."""

    model_config = ConfigDict(extra="forbid")

    questions: list[InterviewQuestionDraft]

    @model_validator(mode="after")
    def validate_count(self) -> InterviewQuestionsOutput:
        if len(self.questions) != INTERVIEW_MAIN_QUESTION_COUNT:
            raise ValueError("exactly five main questions are required")
        return self


class InterviewScoreDimension(BaseModel):
    """A bounded dimension score with a concrete loss reason."""

    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0, le=100)
    deduction_reason: str = Field(default="", max_length=500)


class InterviewScoringOutput(BaseModel):
    """Model-provided scoring evidence; deterministic code computes pass/fail."""

    model_config = ConfigDict(extra="forbid")

    correctness: InterviewScoreDimension
    technical_depth: InterviewScoreDimension
    engineering_judgment: InterviewScoreDimension
    completeness: InterviewScoreDimension
    clarity: InterviewScoreDimension
    critical_error: bool = False
    critical_error_reason: str = Field(default="", max_length=500)
    loss_reasons: list[str] = Field(default_factory=list, max_length=12)
    feedback: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_critical_reason(self) -> InterviewScoringOutput:
        if self.critical_error and not self.critical_error_reason.strip():
            raise ValueError("critical errors require a reason")
        return self


class InterviewFollowUpOutput(BaseModel):
    """One relevant, non-duplicative follow-up question."""

    model_config = ConfigDict(extra="forbid")

    question_text: str = Field(min_length=1, max_length=1200)
    reference_answer: str = Field(min_length=1, max_length=5000)
    scoring_rubric: list[str] = Field(min_length=1, max_length=12)


def weighted_total(output: InterviewScoringOutput) -> float:
    """Compute the fixed weighted total in one deterministic place."""

    total: float = sum(
        float(getattr(output, dimension).score) * weight / 100
        for dimension, weight in SCORE_WEIGHTS.items()
    )
    return round(min(100.0, max(0.0, total)), 2)


def score_band(total: float) -> ScoreBand:
    if total < 70:
        return "below_70"
    if total < 85:
        return "70_84"
    return "85_plus"


def is_pass(total: float, critical_error: bool) -> bool:
    return not critical_error and total >= 70


def scoring_payload(output: InterviewScoringOutput) -> dict[str, object]:
    """Return the internal, versioned scoring snapshot."""

    total = weighted_total(output)
    return {
        "total": total,
        "band": score_band(total),
        "critical_error": output.critical_error,
        "dimensions": {
            key: {
                "score": getattr(output, key).score,
                "weight": weight,
                "deduction_reason": getattr(output, key).deduction_reason,
            }
            for key, weight in SCORE_WEIGHTS.items()
        },
        "loss_reasons": output.loss_reasons,
        "feedback": output.feedback,
        "critical_error_reason": output.critical_error_reason,
    }


__all__ = [
    "DIRECTION_PLANS",
    "INTERVIEW_BLUEPRINT_VERSION",
    "INTERVIEW_CHAIN_TOKEN_BUDGET",
    "INTERVIEW_DURATION_SECONDS",
    "INTERVIEW_MAIN_QUESTION_COUNT",
    "INTERVIEW_PROMPT_VERSION",
    "INTERVIEW_REPORT_VERSION",
    "INTERVIEW_SCORING_VERSION",
    "INTERVIEW_TOTAL_TOKEN_BUDGET",
    "SCORE_WEIGHTS",
    "BlueprintQuestion",
    "InterviewFollowUpOutput",
    "InterviewQuestionDraft",
    "InterviewQuestionsOutput",
    "InterviewScoreDimension",
    "InterviewScoringOutput",
    "build_blueprint",
    "difficulty_mix",
    "is_pass",
    "normalize_topic_keys",
    "score_band",
    "scoring_payload",
    "weighted_total",
]
