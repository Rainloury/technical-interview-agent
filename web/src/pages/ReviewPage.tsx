import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  BookOpenText,
  ChevronDown,
  CircleAlert,
  ShieldAlert,
  Target,
} from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type { WeakPoint, WrongQuestionDetail } from "../api/types";
import { ErrorNotice } from "../components/Feedback";
import { FullPageState } from "../components/FullPageState";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate } from "../utils/format";

type ReviewTab = "wrong" | "weak";

export function ReviewPage() {
  const [params, setParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const tab: ReviewTab = params.get("tab") === "weak" ? "weak" : "wrong";
  const focusWeak = params.get("weak");
  const wrong = useQuery({
    queryKey: queryKeys.wrongQuestions,
    queryFn: () => api.wrongQuestions(),
    enabled: tab === "wrong",
  });
  const weak = useQuery({
    queryKey: queryKeys.weakPoints,
    queryFn: () => api.weakPoints(),
    enabled: tab === "weak" || Boolean(focusWeak),
  });
  const deletion = useQuery({
    queryKey: ["data-deletion"] as const,
    queryFn: api.latestDataDeletion,
    refetchInterval: (query) => {
      const value = query.state.data;
      return value && value.state !== "completed" && value.state !== "failed"
        ? 1000
        : false;
    },
  });
  const requestDeletion = useMutation({
    mutationFn: () => api.deleteMyData(newIdempotencyKey()),
    onSuccess: () => {
      setDeleteConfirm(false);
      void queryClient.invalidateQueries({ queryKey: ["data-deletion"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.wrongQuestions });
      void queryClient.invalidateQueries({ queryKey: queryKeys.weakPoints });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("interview") });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("qa") });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("resume") });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });
  useSessionGuard(wrong.error ?? weak.error);

  const setTab = (next: ReviewTab) => {
    const values = new URLSearchParams(params);
    if (next === "wrong") {
      values.delete("tab");
    } else {
      values.set("tab", "weak");
    }
    values.delete("weak");
    setParams(values);
  };

  return (
    <div className="page review-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">REVIEW / LIBRARY</p>
          <h1>复习中心</h1>
          <p className="page-lede">
            失败轮次的完整反馈只在面试结束后开放。错题记录来源，薄弱点聚合同一主题的重复缺口。
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      <div className="review-tabs" role="tablist" aria-label="复习类型">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "wrong"}
          className={tab === "wrong" ? "review-tab review-tab--active" : "review-tab"}
          onClick={() => setTab("wrong")}
        >
          <BookOpenText size={17} aria-hidden="true" />
          错题
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "weak"}
          className={tab === "weak" ? "review-tab review-tab--active" : "review-tab"}
          onClick={() => setTab("weak")}
        >
          <Target size={17} aria-hidden="true" />
          薄弱点
        </button>
      </div>

      {tab === "wrong" && (
        <ReviewQuery
          query={wrong}
          emptyTitle="还没有错题"
          emptyDescription="完成一次模拟面试后，未通过的轮次会出现在这里。"
        >
          {(items) =>
            items.map((item) => <WrongQuestionCard key={item.id} item={item} />)
          }
        </ReviewQuery>
      )}
      {tab === "weak" && (
        <ReviewQuery
          query={weak}
          emptyTitle="还没有薄弱点"
          emptyDescription="同一主题出现失败轮次后，系统会在这里聚合复习建议。"
        >
          {(items) =>
            items.map((item) => (
              <WeakPointCard
                key={item.id}
                item={item}
                emphasized={focusWeak === item.id}
              />
            ))
          }
        </ReviewQuery>
      )}

      <section className="privacy-controls" aria-labelledby="privacy-title">
        <div>
          <span className="section-kicker">PRIVACY</span>
          <h2 id="privacy-title">删除全部业务数据</h2>
          <p>
            删除请求会立即隐藏简历、问答、面试、错题和薄弱点，并在后台清除私有文件与已存业务数据。
            该操作不可撤销。
          </p>
        </div>
        {deletion.data?.state === "completed" ? (
          <div className="privacy-status privacy-status--completed">
            删除已完成
          </div>
        ) : deletion.data ? (
          <div className="privacy-status">
            {deletion.data.state === "failed" ? "删除未完成" : "删除处理中"}
          </div>
        ) : (
          <button
            type="button"
            className="danger-button"
            onClick={() => setDeleteConfirm(true)}
          >
            <ShieldAlert size={17} aria-hidden="true" />
            <span>删除全部数据</span>
          </button>
        )}
      </section>

      {deleteConfirm && (
        <div className="modal-scrim" role="presentation">
          <div
            className="interview-confirm"
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-all-title"
          >
            <ShieldAlert size={22} aria-hidden="true" />
            <h2 id="delete-all-title">确认删除全部业务数据？</h2>
            <p>
              账户会立即停用，业务内容将不可再访问；删除在后台继续执行，且无法恢复。
            </p>
            <div>
              <button
                type="button"
                className="secondary-button"
                onClick={() => setDeleteConfirm(false)}
                disabled={requestDeletion.isPending}
              >
                取消
              </button>
              <button
                type="button"
                className="danger-button"
                onClick={() => requestDeletion.mutate()}
                disabled={requestDeletion.isPending}
              >
                {requestDeletion.isPending ? "正在提交" : "确认删除"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewQuery<T>({
  query,
  emptyTitle,
  emptyDescription,
  children,
}: {
  query: {
    data?: { items: T[]; next_cursor: string | null };
    isPending: boolean;
    isError: boolean;
    error: unknown;
    refetch: () => unknown;
  };
  emptyTitle: string;
  emptyDescription: string;
  children: (items: T[]) => React.ReactNode;
}) {
  if (query.isPending) {
    return (
      <section className="content-section">
        <FullPageState title="正在读取复习记录" />
      </section>
    );
  }
  if (query.isError) {
    return (
      <ErrorNotice
        message={userError(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return (
      <section className="content-section review-empty">
        <CircleAlert size={24} aria-hidden="true" />
        <h2>{emptyTitle}</h2>
        <p>{emptyDescription}</p>
        <Link className="primary-button primary-button--link" to="/interviews">
          开始模拟面试
          <ArrowRight size={17} aria-hidden="true" />
        </Link>
      </section>
    );
  }
  return <div className="review-list">{children(items)}</div>;
}

function WrongQuestionCard({ item }: { item: WrongQuestionDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <article className={`review-item ${open ? "review-item--open" : ""}`}>
      <button
        type="button"
        className="review-item-summary"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="review-item-kicker">{item.topic_key.replaceAll("_", " ")}</span>
        <strong>{item.question_text}</strong>
        <span>
          <small>{formatDate(item.created_at)}</small>
          <span className="state-pill state-pill--failed">需复习</span>
        </span>
        <ChevronDown className={open ? "rotate" : ""} size={18} aria-hidden="true" />
      </button>
      {open && (
        <div className="review-item-detail">
          <div>
            <span className="section-kicker">YOUR ANSWER</span>
            <p>{item.answer_text}</p>
          </div>
          <div>
            <span className="section-kicker">REFERENCE</span>
            <p>{item.reference_answer}</p>
          </div>
          {item.loss_reasons.length > 0 && (
            <div>
              <span className="section-kicker">LOSS REASONS</span>
              <ul>
                {item.loss_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

function WeakPointCard({
  item,
  emphasized,
}: {
  item: WeakPoint;
  emphasized: boolean;
}) {
  const advice = item.review_advice;
  const concept =
    typeof advice.concept === "string" ? advice.concept : item.topic_key;
  const direction =
    typeof advice.direction === "string" ? advice.direction : "复盘失分原因";
  return (
    <article className={`review-item weak-item ${emphasized ? "weak-item--focus" : ""}`}>
      <header className="weak-item-header">
        <span className="review-item-kicker">{concept.replaceAll("_", " ")}</span>
        <span className="weak-count">{item.failure_count} 次失败</span>
      </header>
      <h2>{item.title.replaceAll("_", " ")}</h2>
      <p>{direction}</p>
      <footer>
        <span>最近失败：{formatDate(item.last_failure_at)}</span>
        <span>{item.evidence.length} 条来源证据</span>
      </footer>
    </article>
  );
}

