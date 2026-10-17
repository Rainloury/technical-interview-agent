import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  CheckCircle2,
  ChevronDown,
  Clock3,
  LoaderCircle,
  MessageSquareText,
  ShieldCheck,
  SkipForward,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type {
  Interview,
  InterviewProgress,
  InterviewReport,
  InterviewReportTurn,
  InterviewTurn,
} from "../api/types";
import { ErrorNotice } from "../components/Feedback";
import { FullPageState } from "../components/FullPageState";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate } from "../utils/format";

const MAX_ANSWER_LENGTH = 20_000;
const terminalStates = new Set(["completed", "timed_out", "cancelled", "failed"]);

const directionLabels = {
  backend: "后端方向",
  frontend: "前端方向",
  fullstack: "全栈方向",
};

const difficultyLabels = {
  easy: "基础",
  medium: "场景",
  hard: "进阶",
};

function draftKey(interviewId: string, turnId: string): string {
  return `interview-draft:${interviewId}:${turnId}`;
}

function readDraft(interviewId: string, turnId: string): string {
  try {
    return window.localStorage.getItem(draftKey(interviewId, turnId)) ?? "";
  } catch {
    return "";
  }
}

function saveDraft(interviewId: string, turnId: string, value: string): void {
  try {
    if (value) {
      window.localStorage.setItem(draftKey(interviewId, turnId), value);
    } else {
      window.localStorage.removeItem(draftKey(interviewId, turnId));
    }
  } catch {
    // Storage can be unavailable in privacy modes; the server still holds submitted answers.
  }
}

function progressLabel(progress: InterviewProgress): string {
  return `${progress.main_questions_completed} / ${progress.main_questions_total}`;
}

function remainingLabel(totalSeconds: number): string {
  const seconds = Math.max(0, totalSeconds);
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`
    : `${minutes}:${String(rest).padStart(2, "0")}`;
}

function turnTypeLabel(turn: InterviewTurn): string {
  return turn.type === "main" ? "主问题" : `追问 ${turn.depth} / 2`;
}

function resultLabel(result: InterviewReportTurn["result"]): string {
  return {
    passed: "通过",
    failed: "未通过",
    skipped: "已跳过",
    unanswered: "未作答",
    scoring_failed: "评分未完成",
    branch_completed: "已结束",
    cancelled: "已取消",
    pending: "待回答",
    awaiting_answer: "待回答",
    scoring: "评分中",
  }[result];
}

export function InterviewDetailPage() {
  const { id = "" } = useParams();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [actionError, setActionError] = useState<unknown>(null);
  const [nowTick, setNowTick] = useState(() => Date.now());
  const [serverSnapshotTick, setServerSnapshotTick] = useState(nowTick);
  const [confirmAction, setConfirmAction] = useState<
    "skip" | "end_branch" | null
  >(null);
  const [draftTurnId, setDraftTurnId] = useState<string | null>(null);
  const answerKey = useRef<string | null>(null);
  const skipKey = useRef<string | null>(null);
  const endKey = useRef<string | null>(null);

  const interview = useQuery({
    queryKey: queryKeys.interview(id),
    queryFn: () => api.interview(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const value = query.state.data;
      if (!value || terminalStates.has(value.state)) {
        return false;
      }
      return value.current_turn?.state === "scoring" ? 900 : 2500;
    },
  });
  useSessionGuard(interview.error);

  const current = interview.data;
  const serverSnapshot = current
    ? `${current.interview_id}:${current.server_time}`
    : "";
  const terminal = current ? terminalStates.has(current.state) : false;
  const reportEnabled = Boolean(
    current && (terminal || current.state === "created"),
  );
  const report = useQuery({
    queryKey: queryKeys.interviewReport(id),
    queryFn: () => api.interviewReport(id),
    enabled: reportEnabled && terminal,
    retry: false,
  });

  useEffect(() => {
    const timer = window.setInterval(() => setNowTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setServerSnapshotTick(Date.now());
    }, 0);
    return () => window.clearTimeout(timer);
  }, [serverSnapshot]);

  const turn = current?.current_turn ?? null;
  useEffect(() => {
    if (!current || !turn || turn.state !== "awaiting_answer") {
      return;
    }
    if (draftTurnId === turn.id) {
      return;
    }
    const timer = window.setTimeout(() => {
      setDraftTurnId(turn.id);
      setDraft(readDraft(current.interview_id, turn.id));
      answerKey.current = null;
    }, 0);
    return () => window.clearTimeout(timer);
  }, [current, draftTurnId, turn]);

  const start = useMutation({
    mutationFn: () => api.startInterview(id, newIdempotencyKey()),
    onSuccess: (value) => {
      queryClient.setQueryData(queryKeys.interview(id), value);
      void queryClient.invalidateQueries({ queryKey: queryKeys.interview(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  const answer = useMutation({
    mutationFn: ({
      turnId,
      value,
      key,
    }: {
      turnId: string;
      value: string;
      key: string;
    }) => api.answerInterview(id, turnId, value, key),
    onSuccess: (_accepted, variables) => {
      saveDraft(id, variables.turnId, "");
      setDraft("");
      void queryClient.invalidateQueries({ queryKey: queryKeys.interview(id) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("interview") });
    },
    onError: (error) => setActionError(error),
  });

  const branchAction = useMutation({
    mutationFn: ({
      turnId,
      operation,
      key,
    }: {
      turnId: string;
      operation: "skip" | "end_branch";
      key: string;
    }) =>
      operation === "skip"
        ? api.skipInterviewTurn(id, turnId, key)
        : api.endInterviewBranch(id, turnId, key),
    onSuccess: () => {
      setConfirmAction(null);
      void queryClient.invalidateQueries({ queryKey: queryKeys.interview(id) });
    },
    onError: (error) => setActionError(error),
  });

  const remainingSeconds = useMemo(() => {
    if (!current) {
      return 0;
    }
    const elapsed = Math.max(0, Math.floor((nowTick - serverSnapshotTick) / 1000));
    return Math.max(0, current.progress.remaining_seconds - elapsed);
  }, [current, nowTick, serverSnapshotTick]);

  if (interview.isPending) {
    return <FullPageState title="正在读取面试" />;
  }
  if (interview.isError || !current) {
    return (
      <div className="page">
        <ErrorNotice
          message={userError(interview.error)}
          onRetry={() => void interview.refetch()}
        />
        <Link className="secondary-button secondary-button--link qa-back" to="/interviews">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回模拟面试</span>
        </Link>
      </div>
    );
  }

  const submitAnswer = () => {
    if (!turn || !draft.trim()) {
      return;
    }
    setActionError(null);
    answerKey.current = answerKey.current ?? newIdempotencyKey();
    answer.mutate({
      turnId: turn.id,
      value: draft.trim(),
      key: answerKey.current,
    });
  };

  const runBranchAction = (operation: "skip" | "end_branch") => {
    if (!turn) {
      return;
    }
    setActionError(null);
    const ref = operation === "skip" ? skipKey : endKey;
    ref.current = ref.current ?? newIdempotencyKey();
    branchAction.mutate({
      turnId: turn.id,
      operation,
      key: ref.current,
    });
  };

  if (current.state === "created") {
    return (
      <div className="page interview-page">
        <header className="page-header">
          <div>
            <p className="eyebrow">INTERVIEW / READY</p>
            <h1>{directionLabels[current.direction]}</h1>
            <p className="page-lede">
              配置已经冻结。点击开始后，服务端会启动 40 分钟倒计时并准备第一道题。
            </p>
          </div>
          <Link className="secondary-button secondary-button--link" to="/interviews">
            <ArrowLeft size={17} aria-hidden="true" />
            <span>返回配置</span>
          </Link>
        </header>
        <section className="interview-ready-panel">
          <span className="interview-ready-icon" aria-hidden="true">
            <Clock3 size={27} />
          </span>
          <div>
            <p className="section-kicker">BEFORE START</p>
            <h2>开始后不会暂停</h2>
            <p>
              5 个主问题，每题一次提交机会；每条追问链最多两层追问。关闭页面后计时继续，
              返回时从精确轮次恢复。
            </p>
          </div>
          <button
            type="button"
            className="primary-button"
            onClick={() => start.mutate()}
            disabled={start.isPending}
          >
            <ArrowRight size={18} aria-hidden="true" />
            <span>{start.isPending ? "正在准备" : "开始面试"}</span>
          </button>
        </section>
        {start.isError && (
          <ErrorNotice
            message={userError(start.error)}
            onRetry={() => start.mutate()}
          />
        )}
      </div>
    );
  }

  if (terminal) {
    return (
      <InterviewResult
        interview={current}
        report={report.data ?? null}
        reportError={report.error}
        reportLoading={report.isPending}
        onReload={() => void report.refetch()}
      />
    );
  }

  return (
    <div className="page interview-page interview-live-page">
      <header className="interview-live-header">
        <div>
          <p className="eyebrow">INTERVIEW / IN PROGRESS</p>
          <div className="resume-title-line">
            <h1>{directionLabels[current.direction]}</h1>
            <span className="state-pill state-pill--in_progress">进行中</span>
          </div>
        </div>
        <div
          className={`interview-clock ${
            remainingSeconds <= 300 ? "interview-clock--urgent" : ""
          }`}
          aria-label="剩余时间"
        >
          <Clock3 size={18} aria-hidden="true" />
          <span>{remainingLabel(remainingSeconds)}</span>
        </div>
      </header>

      <section className="interview-progress-strip" aria-label="面试进度">
        <div>
          <span>主问题进度</span>
          <strong>{progressLabel(current.progress)}</strong>
        </div>
        <div className="interview-progress-track" aria-hidden="true">
          <span
            style={{
              width: `${
                (current.progress.main_questions_completed /
                  Math.max(1, current.progress.main_questions_total)) *
                100
              }%`,
            }}
          />
        </div>
        <span>
          剩余 {current.progress.main_questions_remaining} 个主问题
        </span>
      </section>

      {turn ? (
        <div className="interview-live-grid">
          <section className="interview-question-stage" aria-live="polite">
            <div className="interview-question-meta">
              <span>{turnTypeLabel(turn)}</span>
              <span>{difficultyLabels[turn.difficulty]}</span>
              <span>{turn.topic_key.replaceAll("_", " ")}</span>
            </div>
            {turn.state === "awaiting_answer" ? (
              <>
                <h2>{turn.question_text}</h2>
                <label className="sr-only" htmlFor="interview-answer">
                  你的回答
                </label>
                <textarea
                  id="interview-answer"
                  className="text-area interview-answer"
                  rows={9}
                  maxLength={MAX_ANSWER_LENGTH}
                  value={draft}
                  onChange={(event) => {
                    const value = event.target.value.slice(0, MAX_ANSWER_LENGTH);
                    setDraft(value);
                    answerKey.current = null;
                    saveDraft(id, turn.id, value);
                  }}
                  placeholder="先给结论，再说明关键机制、工程取舍和失败恢复。"
                  disabled={answer.isPending || branchAction.isPending}
                />
                <div className="interview-answer-footer">
                  <span>每题只能提交一次，提交后不能修改。</span>
                  <span>{draft.length} / {MAX_ANSWER_LENGTH}</span>
                </div>
                <div className="interview-answer-actions">
                  {turn.type === "follow_up" && (
                    <>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => setConfirmAction("skip")}
                        disabled={answer.isPending || branchAction.isPending}
                      >
                        <SkipForward size={16} aria-hidden="true" />
                        跳过此题
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => setConfirmAction("end_branch")}
                        disabled={answer.isPending || branchAction.isPending}
                      >
                        <XCircle size={16} aria-hidden="true" />
                        结束当前追问
                      </button>
                    </>
                  )}
                  <button
                    type="button"
                    className="primary-button interview-submit"
                    disabled={
                      answer.isPending ||
                      branchAction.isPending ||
                      !draft.trim()
                    }
                    onClick={submitAnswer}
                  >
                    {answer.isPending ? (
                      <LoaderCircle className="spin" size={18} aria-hidden="true" />
                    ) : (
                      <ArrowRight size={18} aria-hidden="true" />
                    )}
                    <span>{answer.isPending ? "正在提交" : "提交回答"}</span>
                  </button>
                </div>
              </>
            ) : (
              <div className="interview-waiting">
                <LoaderCircle className="spin" size={24} aria-hidden="true" />
                <h2>回答已记录，正在准备下一题</h2>
                <p>评分和分支推进在后台进行。当前页面会自动恢复最新状态。</p>
              </div>
            )}
          </section>

          <aside className="interview-live-aside">
            <div className="interview-process-note">
              <ShieldCheck size={18} aria-hidden="true" />
              <div>
                <strong>反馈在结束后解锁</strong>
                <p>进行中不展示分数、参考答案或追问触发依据。</p>
              </div>
            </div>
            <div className="interview-submitted">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">RECORDED</p>
                  <h2>已提交轮次</h2>
                </div>
                <strong>{current.submitted_turns.length}</strong>
              </div>
              {current.submitted_turns.length === 0 ? (
                <p className="muted-copy">还没有提交的回答。</p>
              ) : (
                <ol className="interview-turn-list">
                  {current.submitted_turns.map((item, index) => (
                    <li key={item.id}>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <div>
                        <strong>{turnTypeLabel(item)}</strong>
                        <small>{item.topic_key.replaceAll("_", " ")}</small>
                      </div>
                      <span className="state-pill">{resultLabel(item.state)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </aside>
        </div>
      ) : (
        <section className="interview-preparing">
          <LoaderCircle className="spin" size={26} aria-hidden="true" />
          <h2>正在准备下一题</h2>
          <p>题目生成与评分完成后，这里会自动显示当前问题。</p>
        </section>
      )}

      {actionError !== null && actionError !== undefined && (
        <ErrorNotice
          message={userError(actionError)}
          onRetry={() => setActionError(null)}
        />
      )}

      {confirmAction && turn && (
        <div className="modal-scrim" role="presentation">
          <div
            className="interview-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="branch-confirm-title"
          >
            <AlertTriangle size={22} aria-hidden="true" />
            <h2 id="branch-confirm-title">
              {confirmAction === "skip" ? "跳过当前追问？" : "结束当前追问？"}
            </h2>
            <p>
              已提交的轮次和评分结果会保留。该操作只会结束当前追问分支，然后继续下一道主问题。
            </p>
            <div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setConfirmAction(null)}
                disabled={branchAction.isPending}
              >
                继续作答
              </button>
              <button
                type="button"
                className="primary-button"
                onClick={() => runBranchAction(confirmAction)}
                disabled={branchAction.isPending}
              >
                {branchAction.isPending ? "正在处理" : "确认结束"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InterviewResult({
  interview,
  report,
  reportError,
  reportLoading,
  onReload,
}: {
  interview: Interview;
  report: InterviewReport | null;
  reportError: unknown;
  reportLoading: boolean;
  onReload: () => void;
}) {
  return (
    <div className="page interview-page interview-report-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">INTERVIEW / REPORT</p>
          <div className="resume-title-line">
            <h1>面试报告</h1>
            <span className={`state-pill state-pill--${interview.state}`}>
              {interview.state === "completed" ? "已完成" : "已结束"}
            </span>
          </div>
          <p className="page-lede">
            {directionLabels[interview.direction]} · {formatDate(interview.ended_at ?? interview.server_time)}
          </p>
        </div>
        <div className="page-header-actions">
          <Link className="secondary-button secondary-button--link" to="/history?type=interview">
            <BookOpenText size={17} aria-hidden="true" />
            <span>面试历史</span>
          </Link>
          <Link className="primary-button primary-button--link" to="/interviews">
            <MessageSquareText size={17} aria-hidden="true" />
            <span>再面试一次</span>
          </Link>
        </div>
      </header>

      {reportLoading && (
        <section className="content-section">
          <FullPageState title="正在整理面试报告" />
        </section>
      )}
      {reportError !== null && reportError !== undefined && (
        <ErrorNotice
          message={userError(reportError)}
          onRetry={onReload}
        />
      )}
      {report && (
        <>
          {report.scoring_status === "incomplete_scoring" && (
            <div className="interview-incomplete-banner" role="status">
              <AlertTriangle size={18} aria-hidden="true" />
              <span>
                部分轮次评分未完成。报告只展示已成功评分的内容，可在评分恢复后重新生成。
              </span>
            </div>
          )}
          <section className="interview-report-summary" aria-label="报告摘要">
            <div>
              <span>主问题</span>
              <strong>{report.summary.main_question_count}</strong>
            </div>
            <div>
              <span>追问</span>
              <strong>{report.summary.follow_up_count}</strong>
            </div>
            <div>
              <span>通过</span>
              <strong>{report.summary.passed_count}</strong>
            </div>
            <div>
              <span>未通过</span>
              <strong>{report.summary.failed_count}</strong>
            </div>
          </section>

          <div className="interview-report-grid">
            <section className="content-section">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">TURN TREE</p>
                  <h2>逐轮结果</h2>
                </div>
              </div>
              <ol className="interview-report-tree">
                {report.turns.map((turn) => (
                  <ReportTurn key={turn.id} turn={turn} />
                ))}
              </ol>
            </section>
            <aside className="interview-report-review">
              <section className="content-section">
                <div className="section-heading">
                  <div>
                    <p className="section-kicker">REVIEW</p>
                    <h2>薄弱点</h2>
                  </div>
                </div>
                {report.weak_points.length === 0 ? (
                  <p className="muted-copy">本次没有新增薄弱点。</p>
                ) : (
                  <div className="weak-point-list">
                    {report.weak_points.map((weak) => (
                      <Link key={weak.id} to={`/reviews?weak=${weak.id}`}>
                        <span>{weak.topic_key.replaceAll("_", " ")}</span>
                        <strong>{weak.failure_count} 次失败</strong>
                        <ArrowRight size={15} aria-hidden="true" />
                      </Link>
                    ))}
                  </div>
                )}
              </section>
              <Link className="secondary-button secondary-button--link interview-review-all" to="/reviews">
                <BookOpenText size={17} aria-hidden="true" />
                <span>打开复习中心</span>
              </Link>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}

function ReportTurn({ turn }: { turn: InterviewReportTurn }) {
  const [expanded, setExpanded] = useState(turn.type === "main");
  const passed = turn.result === "passed";
  const failed = turn.result === "failed" || turn.result === "scoring_failed";
  return (
    <li className={`report-turn report-turn--${turn.type}`} style={{ marginLeft: `${turn.depth * 1.35}rem` }}>
      <button
        type="button"
        className="report-turn-summary"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span className={`report-result-icon ${passed ? "passed" : failed ? "failed" : ""}`} aria-hidden="true">
          {passed ? <CheckCircle2 size={18} /> : failed ? <XCircle size={18} /> : <Clock3 size={18} />}
        </span>
        <span>
          <strong>{turn.type === "main" ? "主问题" : `追问 ${turn.depth}`}</strong>
          <small>{turn.topic_key.replaceAll("_", " ")}</small>
        </span>
        <span className="report-turn-score">
          {turn.score_total !== null ? Math.round(turn.score_total) : "—"}
        </span>
        <span className={`state-pill ${passed ? "state-pill--passed" : failed ? "state-pill--failed" : ""}`}>
          {resultLabel(turn.result)}
        </span>
        <ChevronDown className={expanded ? "rotate" : ""} size={17} aria-hidden="true" />
      </button>
      {expanded && (
        <div className="report-turn-detail">
          <p>{turn.question_text}</p>
          {turn.loss_reasons.length > 0 && (
            <div>
              <strong>失分原因</strong>
              <ul>
                {turn.loss_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
          {turn.reference_answer && (
            <div>
              <strong>参考答案</strong>
              <p>{turn.reference_answer}</p>
            </div>
          )}
        </div>
      )}
    </li>
  );
}

