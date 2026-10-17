import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  BrainCircuit,
  Check,
  Clock3,
  Layers3,
  ShieldCheck,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type {
  InterviewDifficulty,
  InterviewDirection,
} from "../api/types";
import { ErrorNotice } from "../components/Feedback";
import { userError } from "../utils/errors";

const directionOptions: {
  value: InterviewDirection;
  label: string;
  description: string;
  topics: { key: string; label: string }[];
}[] = [
  {
    value: "backend",
    label: "后端",
    description: "API、数据、并发、缓存与可靠性",
    topics: [
      { key: "api_idempotency", label: "API 幂等" },
      { key: "db_transactions", label: "事务与索引" },
      { key: "cache_consistency", label: "缓存一致性" },
      { key: "async_retry", label: "异步重试" },
      { key: "auth_security", label: "认证安全" },
      { key: "observability", label: "可观测性" },
    ],
  },
  {
    value: "frontend",
    label: "前端",
    description: "状态流、浏览器、性能与可访问性",
    topics: [
      { key: "event_loop", label: "事件循环" },
      { key: "component_state", label: "组件状态" },
      { key: "render_performance", label: "渲染性能" },
      { key: "browser_network_security", label: "浏览器安全" },
      { key: "responsive_a11y", label: "响应式与无障碍" },
      { key: "testing_debugging", label: "测试与调试" },
    ],
  },
  {
    value: "fullstack",
    label: "全栈",
    description: "契约、会话、状态同步与端到端故障",
    topics: [
      { key: "api_contract", label: "API 契约" },
      { key: "auth_session", label: "认证会话" },
      { key: "state_sync", label: "状态同步" },
      { key: "async_consistency", label: "最终一致性" },
      { key: "e2e_errors", label: "端到端重试" },
      { key: "deployment_observability", label: "部署与观测" },
    ],
  },
];

const difficultyOptions: {
  value: InterviewDifficulty;
  label: string;
  description: string;
}[] = [
  {
    value: "foundation",
    label: "基础",
    description: "以概念与场景应用为主，保留一道进阶题。",
  },
  {
    value: "balanced",
    label: "均衡",
    description: "基础、场景和设计取舍各占一部分。",
  },
  {
    value: "challenge",
    label: "进阶",
    description: "更多设计取舍和故障恢复问题。",
  },
];

export function InterviewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [direction, setDirection] = useState<InterviewDirection>("backend");
  const [difficulty, setDifficulty] =
    useState<InterviewDifficulty>("balanced");
  const [topics, setTopics] = useState<string[]>([]);
  const [key, setKey] = useState<string | null>(null);
  const [requested, setRequested] = useState("");

  const activeDirection = directionOptions.find(
    (item) => item.value === direction,
  )!;

  const create = useMutation({
    mutationFn: ({
      idempotencyKey,
    }: {
      idempotencyKey: string;
    }) => api.createInterview(direction, difficulty, topics, idempotencyKey),
    onSuccess: (created) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.history("interview"),
      });
      navigate(`/interviews/${created.interview_id}`, { replace: true });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const snapshot = JSON.stringify({ direction, difficulty, topics });
    let nextKey = key;
    if (!nextKey || requested !== snapshot) {
      nextKey = newIdempotencyKey();
      setKey(nextKey);
      setRequested(snapshot);
    }
    create.mutate({ idempotencyKey: nextKey });
  };

  const conflict =
    create.error instanceof ApiError && create.error.code === "idempotency_conflict";

  return (
    <div className="page interview-create-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">INTERVIEW / SETUP</p>
          <h1>模拟面试</h1>
          <p className="page-lede">
            一次专注的连续技术面试。开始后会按服务端时间计时，结束前不展示分数和详细反馈。
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      <form className="interview-setup-grid" onSubmit={submit}>
        <div className="interview-setup-main">
          <section className="content-section">
            <div className="section-heading">
              <div>
                <p className="section-kicker">DIRECTION</p>
                <h2>选择面试方向</h2>
              </div>
              <span className="setup-step">01</span>
            </div>
            <div className="interview-choice-grid">
              {directionOptions.map((option) => (
                <label
                  key={option.value}
                  className={`interview-choice ${
                    direction === option.value ? "interview-choice--active" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="direction"
                    aria-label={`${option.label}方向`}
                    value={option.value}
                    checked={direction === option.value}
                    onChange={() => {
                      setDirection(option.value);
                      setTopics([]);
                      setKey(null);
                    }}
                  />
                  <span className="interview-choice-icon" aria-hidden="true">
                    {option.value === "backend" ? (
                      <BrainCircuit size={20} />
                    ) : option.value === "frontend" ? (
                      <Layers3 size={20} />
                    ) : (
                      <ArrowRight size={20} />
                    )}
                  </span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                  <span className="choice-check" aria-hidden="true">
                    <Check size={14} />
                  </span>
                </label>
              ))}
            </div>
          </section>

          <section className="content-section">
            <div className="section-heading">
              <div>
                <p className="section-kicker">DIFFICULTY</p>
                <h2>难度分布</h2>
              </div>
              <span className="setup-step">02</span>
            </div>
            <fieldset className="interview-difficulty">
              <legend className="sr-only">难度</legend>
              {difficultyOptions.map((option) => (
                <label
                  key={option.value}
                  className={`difficulty-choice ${
                    difficulty === option.value
                      ? "difficulty-choice--active"
                      : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="difficulty"
                    aria-label={option.label}
                    value={option.value}
                    checked={difficulty === option.value}
                    onChange={() => {
                      setDifficulty(option.value);
                      setKey(null);
                    }}
                  />
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </label>
              ))}
            </fieldset>
          </section>

          <section className="content-section">
            <div className="section-heading">
              <div>
                <p className="section-kicker">TOPICS</p>
                <h2>重点主题</h2>
              </div>
              <span className="setup-step">03</span>
            </div>
            <p className="setup-help">
              可选。不选择时由系统覆盖核心主题；选择后会优先进入前几道主问题。
            </p>
            <div className="topic-chip-grid">
              {activeDirection.topics.map((topic) => {
                const selected = topics.includes(topic.key);
                return (
                  <button
                    key={topic.key}
                    type="button"
                    className={`topic-chip ${selected ? "topic-chip--active" : ""}`}
                    aria-pressed={selected}
                    onClick={() => {
                      setTopics((current) =>
                        selected
                          ? current.filter((item) => item !== topic.key)
                          : [...current, topic.key],
                      );
                      setKey(null);
                    }}
                  >
                    {topic.label}
                  </button>
                );
              })}
            </div>
          </section>

          {create.isError && (
            <ErrorNotice
              message={userError(create.error)}
              onRetry={
                conflict
                  ? undefined
                  : () =>
                      create.mutate({
                        idempotencyKey: key ?? newIdempotencyKey(),
                      })
              }
            />
          )}
        </div>

        <aside className="interview-summary-panel" aria-label="面试规则">
          <p className="section-kicker">SESSION</p>
          <h2>{activeDirection.label}方向</h2>
          <div className="interview-rule-list">
            <div>
              <Clock3 size={18} aria-hidden="true" />
              <span>
                <strong>40 分钟</strong>
                <small>开始后持续计时，关闭页面也不暂停</small>
              </span>
            </div>
            <div>
              <Layers3 size={18} aria-hidden="true" />
              <span>
                <strong>5 个主问题</strong>
                <small>每题一次提交机会，最多两层追问</small>
              </span>
            </div>
            <div>
              <ShieldCheck size={18} aria-hidden="true" />
              <span>
                <strong>结束后解锁反馈</strong>
                <small>进行中只展示题目与中性进度</small>
              </span>
            </div>
          </div>
          <div className="interview-summary-topic">
            <span>难度</span>
            <strong>
              {difficultyOptions.find((item) => item.value === difficulty)?.label}
            </strong>
          </div>
          <div className="interview-summary-topic">
            <span>重点主题</span>
            <strong>{topics.length ? `${topics.length} 个` : "自动覆盖"}</strong>
          </div>
          <button
            type="submit"
            className="primary-button interview-start-button"
            disabled={create.isPending}
          >
            <ArrowRight size={18} aria-hidden="true" />
            <span>{create.isPending ? "正在创建" : "创建并开始"}</span>
          </button>
          <Link className="quiet-link interview-review-link" to="/reviews">
            查看错题与薄弱点
          </Link>
        </aside>
      </form>
    </div>
  );
}

