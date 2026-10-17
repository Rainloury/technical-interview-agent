import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  FileX2,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type {
  ResumeFailureStage,
  ResumeQuestion,
  ResumeState,
  ResumeTask,
} from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/Feedback";
import { FullPageState } from "../components/FullPageState";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate, stateLabel } from "../utils/format";

const terminalStates = new Set<ResumeState>([
  "completed",
  "failed",
  "source_deleted",
]);

const stages: { state: ResumeState; label: string }[] = [
  { state: "uploaded", label: "接收文件" },
  { state: "extracting", label: "提取文本" },
  { state: "analyzing", label: "分析经历" },
  { state: "generating_questions", label: "生成题目" },
  { state: "completed", label: "完成" },
];

const stageLabels: Record<ResumeFailureStage, string> = {
  upload: "文件接收",
  extract: "文本提取",
  analyze: "经历分析",
  generate: "题目生成",
};

const difficultyLabels = {
  easy: "基础",
  medium: "进阶",
  hard: "挑战",
};

function stringItems(value: unknown): string[] {
  if (!value || typeof value !== "object" || !("items" in value)) {
    return [];
  }
  const items = (value as { items?: unknown }).items;
  if (!Array.isArray(items)) {
    return [];
  }
  return items
    .map((item) => (typeof item === "string" ? item : null))
    .filter((item): item is string => item !== null);
}

function currentStage(task: ResumeTask): number {
  if (task.state === "failed" && task.failure_stage) {
    const failedState = {
      upload: "uploaded",
      extract: "extracting",
      analyze: "analyzing",
      generate: "generating_questions",
    }[task.failure_stage];
    return stages.findIndex((stage) => stage.state === failedState);
  }
  return stages.findIndex((stage) => stage.state === task.state);
}

function QuestionCard({ question }: { question: ResumeQuestion }) {
  return (
    <article className="question-card">
      <header>
        <span className="question-sequence">{String(question.sequence).padStart(2, "0")}</span>
        <span className={`difficulty difficulty--${question.difficulty}`}>
          {difficultyLabels[question.difficulty]}
        </span>
        <span className="question-category">{question.category}</span>
      </header>
      <h3>{question.question_text}</h3>
      {stringItems(question.assessment_points).length > 0 && (
        <div className="assessment-points">
          <span>考察点</span>
          <ul>
            {stringItems(question.assessment_points).map((point) => (
              <li key={point}>{point}</li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

export function ResumeDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [retryKey, setRetryKey] = useState<string | null>(null);
  const [deleteKey, setDeleteKey] = useState<string | null>(null);

  const resume = useQuery({
    queryKey: queryKeys.resume(id),
    queryFn: () => api.resume(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const state = query.state.data?.state;
      return state && terminalStates.has(state) ? false : 1500;
    },
  });
  useSessionGuard(resume.error);

  const refreshLists = () => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    void queryClient.invalidateQueries({ queryKey: queryKeys.history("resume") });
  };

  const retry = useMutation({
    mutationFn: () => {
      const key = retryKey ?? newIdempotencyKey();
      if (!retryKey) {
        setRetryKey(key);
      }
      return api.retryResume(id, key);
    },
    onSuccess: (accepted) => {
      refreshLists();
      navigate(`/resumes/${accepted.resume_task_id}`, { replace: true });
    },
  });

  const removeSource = useMutation({
    mutationFn: () => {
      const key = deleteKey ?? newIdempotencyKey();
      if (!deleteKey) {
        setDeleteKey(key);
      }
      return api.deleteResumeSource(id, key);
    },
    onSuccess: () => {
      setConfirmDelete(false);
      refreshLists();
      void queryClient.invalidateQueries({ queryKey: queryKeys.resume(id) });
    },
  });

  if (resume.isPending) {
    return <FullPageState title="正在读取简历任务" />;
  }

  if (resume.isError) {
    return (
      <div className="page">
        <ErrorNotice
          message={userError(resume.error)}
          onRetry={() => void resume.refetch()}
        />
        <Link className="secondary-button secondary-button--link resume-error-back" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </div>
    );
  }

  const task = resume.data;
  const stageIndex = currentStage(task);
  const activeStages = stages.filter((stage) => stage.state !== "completed");
  const sourceDeleted = task.state === "source_deleted";

  return (
    <div className="page resume-page">
      <header className="page-header resume-detail-header">
        <div>
          <p className="eyebrow">RESUME / TASK</p>
          <div className="resume-title-line">
            <h1>简历分析</h1>
            <span className={`state-pill state-pill--${task.state}`}>
              {stateLabel(task.state)}
            </span>
          </div>
          <p className="page-lede">
            创建于 {formatDate(task.created_at)}
            {task.completed_at ? ` · 完成于 ${formatDate(task.completed_at)}` : ""}
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      {!terminalStates.has(task.state) && (
        <section className="content-section process-panel" aria-live="polite">
          <div className="section-heading">
            <div>
              <p className="section-kicker">PROCESSING</p>
              <h2>正在处理简历</h2>
            </div>
            <RefreshCw className="spin" size={18} aria-label="处理中" />
          </div>
          <ol className="stage-list">
            {activeStages.map((stage, index) => {
              const done = index < stageIndex;
              const active = index === stageIndex;
              return (
                <li
                  key={stage.state}
                  className={`${done ? "stage--done" : ""} ${active ? "stage--active" : ""}`}
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

      {task.state === "failed" && (
        <section className="content-section failure-panel">
          <span className="failure-icon" aria-hidden="true">
            <AlertTriangle size={21} />
          </span>
          <div>
            <h2>简历处理未完成</h2>
            <p>
              {task.failure_stage
                ? `在“${stageLabels[task.failure_stage]}”阶段未能完成。`
                : "处理任务未能完成。"}
              你可以保留新任务记录并重新提交同一份私有来源。
            </p>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => retry.mutate()}
            disabled={retry.isPending}
          >
            <RotateCcw size={17} aria-hidden="true" />
            <span>{retry.isPending ? "正在重试" : "重新处理"}</span>
          </button>
          {retry.isError && <ErrorNotice message={userError(retry.error)} />}
        </section>
      )}

      {sourceDeleted && (
        <section className="content-section deleted-panel">
          <span className="failure-icon failure-icon--muted" aria-hidden="true">
            <FileX2 size={21} />
          </span>
          <div>
            <h2>原始简历已删除</h2>
            <p>私有文件与提取文本已清除；保留的分析摘要不再包含文件名、页码或可定位原文。</p>
          </div>
        </section>
      )}

      {task.analysis && (
        <>
          <section className="content-section analysis-section" aria-labelledby="analysis-title">
            <div className="section-heading">
              <div>
                <p className="section-kicker">ANALYSIS</p>
                <h2 id="analysis-title">结构化分析</h2>
              </div>
              <span className="analysis-version">schema {task.analysis.schema_version}</span>
            </div>
            <div className="analysis-grid">
              <div>
                <h3>技能</h3>
                <ul className="tag-list">
                  {(task.analysis.skills.items ?? []).map((skill, index) => {
                    const name =
                      skill && typeof skill === "object" && "name" in skill
                        ? String(skill.name)
                        : null;
                    return name ? <li key={`${name}-${index}`}>{name}</li> : null;
                  })}
                </ul>
                {(task.analysis.skills.items ?? []).length === 0 && (
                  <p className="muted-copy">未识别到明确技能。</p>
                )}
              </div>
              <div>
                <h3>项目</h3>
                {(task.analysis.projects.items ?? []).length > 0 ? (
                  <ul className="project-list">
                    {(task.analysis.projects.items ?? []).map((project, index) => {
                      if (!project || typeof project !== "object") {
                        return null;
                      }
                      const name =
                        "name" in project ? String(project.name) : `项目 ${index + 1}`;
                      const summary =
                        "summary" in project ? String(project.summary) : "";
                      return (
                        <li key={`${name}-${index}`}>
                          <strong>{name}</strong>
                          {summary && <span>{summary}</span>}
                        </li>
                      );
                    })}
                  </ul>
                ) : (
                  <p className="muted-copy">未识别到可验证的项目经历。</p>
                )}
              </div>
              <div>
                <h3>待验证</h3>
                {stringItems(task.analysis.unverified_items).length > 0 ? (
                  <ul className="plain-list">
                    {stringItems(task.analysis.unverified_items).map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted-copy">暂无需要单独核实的条目。</p>
                )}
              </div>
            </div>
          </section>

          {task.questions.length > 0 && (
            <section className="questions-section" aria-labelledby="questions-title">
              <div className="section-heading">
                <div>
                  <p className="section-kicker">QUESTIONS</p>
                  <h2 id="questions-title">面试题目</h2>
                </div>
                <span className="result-count">{task.questions.length} 道</span>
              </div>
              <div className="question-list">
                {task.questions.map((question) => (
                  <QuestionCard key={question.id} question={question} />
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {task.state === "completed" && task.questions.length === 0 && task.analysis && (
        <EmptyState
          title="尚未生成题目"
          description="分析已完成，但当前任务没有公开题目。"
        />
      )}

      {!sourceDeleted && (
        <section className="source-controls">
          <div>
            <span className="source-label">
              <ShieldCheck size={17} aria-hidden="true" />
              原始简历控制
            </span>
            <p>删除原始文件与提取文本，保留已脱敏的分析和题目。</p>
          </div>
          {!confirmDelete ? (
            <button
              className="secondary-button danger-button"
              type="button"
              onClick={() => setConfirmDelete(true)}
            >
              <Trash2 size={17} aria-hidden="true" />
              <span>删除原始简历</span>
            </button>
          ) : (
            <div className="confirm-actions">
              <span>此操作不可撤销。</span>
              <button
                className="secondary-button"
                type="button"
                onClick={() => setConfirmDelete(false)}
                disabled={removeSource.isPending}
              >
                取消
              </button>
              <button
                className="primary-button danger-primary"
                type="button"
                onClick={() => removeSource.mutate()}
                disabled={removeSource.isPending}
              >
                <Trash2 size={17} aria-hidden="true" />
                <span>{removeSource.isPending ? "正在删除" : "确认删除"}</span>
              </button>
            </div>
          )}
          {removeSource.isError && <ErrorNotice message={userError(removeSource.error)} />}
        </section>
      )}
    </div>
  );
}
