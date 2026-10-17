import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  BookOpenText,
  Check,
  CircleDashed,
  HelpCircle,
  RefreshCw,
  Scale,
  Sparkles,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type {
  QaAnswer,
  QaEvidence,
  QaEvidenceStatus,
  QaRequest,
  QaState,
  QaStreamEvent,
} from "../api/types";
import { ErrorNotice } from "../components/Feedback";
import { FullPageState } from "../components/FullPageState";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate, stateLabel } from "../utils/format";

const terminalStates = new Set<QaState>(["completed", "failed"]);

const evidenceLabels: Record<
  QaEvidenceStatus,
  { label: string; description: string; tone: string }
> = {
  supported: {
    label: "资料支持",
    description: "回答结论来自已审核资料中的检索证据。",
    tone: "supported",
  },
  model_knowledge: {
    label: "模型知识",
    description: "当前资料不足，回答依据通用模型知识，未引用内部证据。",
    tone: "model",
  },
  insufficient: {
    label: "信息不足",
    description: "现有资料无法支持可靠回答，请补充条件或换一种问法。",
    tone: "insufficient",
  },
};

const progressStages: { state: QaState; label: string }[] = [
  { state: "created", label: "接收问题" },
  { state: "retrieving", label: "检索资料" },
  { state: "answering", label: "生成回答" },
  { state: "completed", label: "完成" },
];

function mergeEvidence(
  current: QaEvidence[],
  incoming: QaEvidence[],
): QaEvidence[] {
  const byCitation = new Map(current.map((item) => [item.citation_id, item]));
  for (const item of incoming) {
    byCitation.set(item.citation_id, item);
  }
  return [...byCitation.values()];
}

function currentStage(state: QaState): number {
  return progressStages.findIndex((stage) => stage.state === state);
}

function AnswerBody({ answer }: { answer: QaAnswer }) {
  return (
    <div className="qa-answer-copy">
      <p className="qa-direct-answer">{answer.direct_answer}</p>
      <div className="qa-explanation">
        {answer.explanation.split(/\n{2,}/).map((paragraph) => (
          <p key={paragraph}>{paragraph}</p>
        ))}
      </div>
    </div>
  );
}

function EvidenceCard({ item }: { item: QaEvidence }) {
  return (
    <article className="qa-evidence-card">
      <header>
        <span className="citation-tag">{item.citation_id}</span>
        <span
          className={`source-state ${
            item.source_state === "available" ? "" : "source-state--deleted"
          }`}
        >
          {item.source_state === "available" ? "可访问" : "来源已删除"}
        </span>
      </header>
      <h3>{item.title}</h3>
      {item.section_path && <p className="evidence-path">{item.section_path}</p>}
      <blockquote>{item.snippet}</blockquote>
      <footer>
        <span>相关度</span>
        <span className="relevance-track" aria-hidden="true">
          <span style={{ width: `${Math.round(item.relevance_score * 100)}%` }} />
        </span>
        <span>{Math.round(item.relevance_score * 100)}%</span>
      </footer>
    </article>
  );
}

export function QaDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [liveState, setLiveState] = useState<QaRequest | null>(null);
  const [streamError, setStreamError] = useState<unknown>(null);
  const [reconnecting, setReconnecting] = useState(false);
  const [retryToken, setRetryToken] = useState(0);
  const seenEventIds = useRef(new Set<number>());
  const lastEventId = useRef(0);
  const terminalSeen = useRef(false);
  const streamRequestId = useRef<string | null>(null);
  const liveStateRef = useRef<QaRequest | null>(null);

  const qa = useQuery({
    queryKey: queryKeys.qa(id),
    queryFn: () => api.qa(id),
    enabled: Boolean(id),
  });
  useSessionGuard(qa.error);

  const localSnapshot =
    liveState && liveState.id === qa.data?.id ? liveState : null;
  const request = localSnapshot ?? qa.data ?? null;
  const evidence = localSnapshot?.evidence ?? qa.data?.evidence ?? [];
  const answer = localSnapshot?.answer ?? qa.data?.answer ?? null;

  useEffect(() => {
    const snapshot = qa.data;
    if (!snapshot || !id || snapshot.id !== id) {
      return;
    }
    if (streamRequestId.current !== snapshot.id) {
      streamRequestId.current = snapshot.id;
      seenEventIds.current = new Set();
      lastEventId.current = snapshot.last_event_seq;
      terminalSeen.current = terminalStates.has(snapshot.state);
      liveStateRef.current = terminalSeen.current ? snapshot : null;
    }
    if (terminalSeen.current) {
      return;
    }
    const controller = new AbortController();
    let active = true;
    const eventCursor = lastEventId.current || snapshot.last_event_seq;

    const finish = () => {
      if (!active) {
        return;
      }
      active = false;
      terminalSeen.current = true;
      void queryClient.fetchQuery({
        queryKey: queryKeys.qa(id),
        queryFn: () => api.qa(id),
        staleTime: 0,
      }).then((fresh) => {
        const current = liveStateRef.current;
        if (
          terminalStates.has(fresh.state) &&
          !(current?.id === id && terminalStates.has(current.state))
        ) {
          liveStateRef.current = fresh;
          setLiveState(fresh);
        }
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("qa") });
    };

    const handleEvent = (event: QaStreamEvent) => {
      if (!active || seenEventIds.current.has(event.id)) {
        return;
      }
      seenEventIds.current.add(event.id);
      lastEventId.current = Math.max(lastEventId.current, event.id);
      setReconnecting(false);

      if (event.type === "evidence") {
        const items = Array.isArray(event.data.items)
          ? (event.data.items as QaEvidence[])
          : [];
        const current =
          liveStateRef.current?.id === snapshot.id
            ? liveStateRef.current
            : snapshot;
        const next = {
          ...current,
          evidence: mergeEvidence(current.evidence, items),
          state: "answering" as const,
        };
        liveStateRef.current = next;
        setLiveState(next);
        return;
      }
      if (event.type === "completed" && event.data.answer) {
        const completedEvidence = Array.isArray(event.data.evidence)
          ? (event.data.evidence as QaEvidence[])
          : [];
        const completedAnswer = event.data.answer as QaAnswer;
        const current =
          liveStateRef.current?.id === snapshot.id
            ? liveStateRef.current
            : snapshot;
        const next = {
          ...current,
          state: "completed" as const,
          answer: completedAnswer,
          evidence: completedEvidence,
          evidence_status: completedAnswer.evidence_status,
          completed_at: current.completed_at ?? new Date().toISOString(),
        };
        liveStateRef.current = next;
        setLiveState(next);
        finish();
        return;
      }
      if (event.type === "error") {
        setStreamError(
          new Error(
            typeof event.data.message === "string"
              ? event.data.message
              : "问答暂未完成，请稍后重试。",
          ),
        );
        const current =
          liveStateRef.current?.id === snapshot.id
            ? liveStateRef.current
            : snapshot;
        const next = {
          ...current,
          state: "failed" as const,
          error: {
            code:
              typeof event.data.code === "string"
                ? event.data.code
                : "qa_failed",
            message:
              typeof event.data.message === "string"
                ? event.data.message
                : "问答暂未完成，请稍后重试。",
            retryable: Boolean(event.data.retryable),
          },
        };
        liveStateRef.current = next;
        setLiveState(next);
        finish();
      }
    };

    void api
      .streamQa(id, {
        afterSeq: eventCursor,
        onEvent: handleEvent,
        onReconnect: () => setReconnecting(true),
        signal: controller.signal,
      })
      .catch((error: unknown) => {
        if (active && !controller.signal.aborted) {
          setStreamError(error);
        }
      })
      .finally(() => setReconnecting(false));

    return () => {
      active = false;
      controller.abort();
      setReconnecting(false);
    };
  }, [id, qa.data, queryClient, retryToken]);

  if (qa.isPending) {
    return <FullPageState title="正在读取问答" />;
  }

  if (qa.isError || !request) {
    return (
      <div className="page">
        <ErrorNotice
          message={userError(qa.error)}
          onRetry={() => void qa.refetch()}
        />
        <Link className="secondary-button secondary-button--link qa-back" to="/qa">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回技术问答</span>
        </Link>
      </div>
    );
  }

  const evidenceStatus = answer?.evidence_status ?? request.evidence_status;
  const status = evidenceLabels[evidenceStatus];
  const stageIndex = currentStage(request.state);
  const failed = request.state === "failed";
  const completed = request.state === "completed";
  const evidenceIds = new Set(answer?.evidence_ids ?? []);
  const citedEvidence = evidence.filter(
    (item) => evidenceIds.size === 0 || evidenceIds.has(item.citation_id),
  );

  return (
    <div className="page qa-page qa-detail-page">
      <header className="page-header qa-detail-header">
        <div>
          <p className="eyebrow">KNOWLEDGE / ANSWER</p>
          <div className="resume-title-line">
            <h1>检索问答</h1>
            <span className={`state-pill state-pill--${request.state}`}>
              {stateLabel(request.state)}
            </span>
          </div>
          <p className="page-lede">
            创建于 {formatDate(request.created_at)}
            {request.completed_at
              ? ` · 完成于 ${formatDate(request.completed_at)}`
              : ""}
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/qa">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>继续提问</span>
        </Link>
      </header>

      <section className="qa-question-panel" aria-labelledby="qa-question-title">
        <div className="section-heading">
          <div>
            <p className="section-kicker">QUESTION</p>
            <h2 id="qa-question-title">你的问题</h2>
          </div>
          <span className="qa-preference-label">
            {request.answer_preference === "detailed" ? "详细回答" : "简明回答"}
          </span>
        </div>
        <p>{request.question}</p>
      </section>

      {!completed && !failed && (
        <section className="content-section process-panel qa-process" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="section-kicker">RETRIEVING</p>
              <h2>{reconnecting ? "正在恢复回答连接" : "正在检索并回答"}</h2>
            </div>
            <RefreshCw className="spin" size={18} aria-label="处理中" />
          </div>
          <ol className="stage-list qa-stage-list">
            {progressStages
              .filter((stage) => stage.state !== "completed")
              .map((stage, index) => {
                const done = index < stageIndex;
                const active = index === stageIndex;
                return (
                  <li
                    key={stage.state}
                    className={`${done ? "stage--done" : ""} ${
                      active ? "stage--active" : ""
                    }`}
                  >
                    <span className="stage-marker">
                      {done ? <Check size={14} /> : index + 1}
                    </span>
                    <span>{stage.label}</span>
                  </li>
                );
              })}
          </ol>
        </section>
      )}

      {failed && (
        <section className="content-section failure-panel qa-failure">
          <span className="failure-icon" aria-hidden="true">
            <AlertTriangle size={21} />
          </span>
          <div>
            <h2>问答暂未完成</h2>
            <p>
              {request.error?.message ??
                userError(streamError)}
            </p>
          </div>
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              setStreamError(null);
              void qa.refetch();
            }}
          >
            <RefreshCw size={17} aria-hidden="true" />
            <span>重新读取</span>
          </button>
        </section>
      )}

      {!failed && Boolean(streamError) && !completed && (
        <section className="content-section qa-stream-error">
          <ErrorNotice
            message={
              streamError instanceof Error
                ? streamError.message
                : "回答连接中断，请稍后重试。"
            }
            onRetry={() => setRetryToken((value) => value + 1)}
          />
        </section>
      )}

      {answer && (
        <>
          <section className="content-section qa-answer-panel" aria-labelledby="qa-answer-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">ANSWER</p>
                <h2 id="qa-answer-title">回答</h2>
              </div>
              <span className={`evidence-status evidence-status--${status.tone}`}>
                {status.tone === "supported" ? (
                  <BookOpenText size={15} aria-hidden="true" />
                ) : status.tone === "model" ? (
                  <Sparkles size={15} aria-hidden="true" />
                ) : (
                  <HelpCircle size={15} aria-hidden="true" />
                )}
                {status.label}
              </span>
            </div>
            <AnswerBody answer={answer} />
            <p className="evidence-status-note">{status.description}</p>
          </section>

          <section className="qa-evidence-section" aria-labelledby="qa-evidence-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">EVIDENCE</p>
                <h2 id="qa-evidence-title">引用证据</h2>
              </div>
              <span className="result-count">{citedEvidence.length} 条</span>
            </div>
            {citedEvidence.length > 0 ? (
              <div className="qa-evidence-list">
                {citedEvidence.map((item) => (
                  <EvidenceCard key={item.citation_id} item={item} />
                ))}
              </div>
            ) : (
              <div className="qa-empty-evidence">
                <Scale size={19} aria-hidden="true" />
                <div>
                  <strong>本次回答没有引用内部资料</strong>
                  <p>{status.description}</p>
                </div>
              </div>
            )}
          </section>
        </>
      )}

      {!answer && evidence.length > 0 && (
        <section className="qa-evidence-section" aria-labelledby="qa-pending-evidence-title">
          <div className="section-heading">
            <div>
              <p className="section-kicker">RETRIEVED</p>
              <h2 id="qa-pending-evidence-title">已检索资料</h2>
            </div>
            <CircleDashed className="spin" size={17} aria-label="正在生成回答" />
          </div>
          <div className="qa-evidence-list">
            {evidence.map((item) => (
              <EvidenceCard key={item.citation_id} item={item} />
            ))}
          </div>
        </section>
      )}

      {answer && answer.extended_questions.length > 0 && (
        <section className="content-section qa-followups" aria-labelledby="qa-followups-title">
          <div className="section-heading">
            <div>
              <p className="section-kicker">NEXT</p>
              <h2 id="qa-followups-title">可以继续追问</h2>
            </div>
          </div>
          <ul>
            {answer.extended_questions.map((question, index) => (
              <li key={`${index}-${question}`}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <Link to="/qa" state={{ question }}>
                  {question}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
