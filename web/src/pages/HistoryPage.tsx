import { useInfiniteQuery } from "@tanstack/react-query";
import { ArrowDown, ArrowRight, FileText, MessageSquareText } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { HistoryType } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/Feedback";
import { LoadingRows } from "../components/LoadingRows";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { userError } from "../utils/errors";
import { formatDate, stateLabel, taskTypeLabels } from "../utils/format";

const tabs: { type: HistoryType; label: string }[] = [
  { type: "interview", label: "模拟面试" },
  { type: "resume", label: "简历任务" },
  { type: "qa", label: "技术问答" },
  { type: "wrong_question", label: "错题" },
];

function parseType(value: string | null): HistoryType {
  return tabs.some((tab) => tab.type === value) ? (value as HistoryType) : "interview";
}

export function HistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const historyType = parseType(searchParams.get("type"));
  const history = useInfiniteQuery({
    queryKey: queryKeys.history(historyType),
    queryFn: ({ pageParam }) => api.history(historyType, pageParam, 10),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
  });
  useSessionGuard(history.error);

  const items = history.data?.pages.flatMap((page) => page.items) ?? [];

  const selectType = (type: HistoryType) => {
    setSearchParams({ type });
  };

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">WORKSPACE / HISTORY</p>
          <h1>历史记录</h1>
          <p className="page-lede">按类型查看属于你的任务、问答和模拟面试记录。</p>
        </div>
      </header>

      <div className="history-toolbar">
        <div className="segmented" role="tablist" aria-label="历史记录类型">
          {tabs.map((tab) => (
            <button
              key={tab.type}
              type="button"
              role="tab"
              aria-selected={historyType === tab.type}
              className={historyType === tab.type ? "segment--active" : ""}
              onClick={() => selectType(tab.type)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <span className="result-count">
          {history.isSuccess ? `${items.length} 条已加载` : "读取记录"}
        </span>
      </div>

      <section className="content-section content-section--history" aria-live="polite">
        {history.isPending && <LoadingRows rows={6} />}
        {history.isError && items.length === 0 && (
          <ErrorNotice
            message={userError(history.error)}
            onRetry={() => void history.refetch()}
          />
        )}
        {history.isSuccess && items.length === 0 && (
          <EmptyState
            title="暂无这类记录"
            description="当对应切片交付并产生记录后，这里会按更新时间倒序展示。"
          />
        )}
        {items.length > 0 && (
          <div className="history-list">
            {items.map((item) => (
              <article className="history-row" key={`${item.type}-${item.id}`}>
                <span className="record-type" aria-hidden="true">
                  {item.type === "qa" || item.type === "interview" ? (
                    <MessageSquareText size={18} />
                  ) : item.type === "resume" ? (
                    <FileText size={18} />
                  ) : (
                    <ArrowDown size={18} />
                  )}
                </span>
                <div className="record-copy">
                  <strong title={item.title}>{item.title}</strong>
                  <span>
                    {taskTypeLabels[item.type]} · {formatDate(item.updated_at)}
                  </span>
                </div>
                <span className="state-pill">{stateLabel(item.state)}</span>
                {(item.type === "resume" ||
                  item.type === "qa" ||
                  item.type === "interview") && (
                  <Link
                    className="record-action"
                    to={
                      item.type === "resume"
                        ? `/resumes/${item.id}`
                        : item.type === "interview"
                          ? `/interviews/${item.id}`
                          : `/qa/${item.id}`
                    }
                    aria-label={`查看 ${item.title}`}
                  >
                    <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                )}
              </article>
            ))}
          </div>
        )}
        {history.isError && items.length > 0 && (
          <ErrorNotice
            message={userError(history.error)}
            onRetry={() => void history.fetchNextPage()}
            compact
          />
        )}
        {history.hasNextPage && (
          <div className="load-more-wrap">
            <button
              type="button"
              className="secondary-button"
              onClick={() => void history.fetchNextPage()}
              disabled={history.isFetchingNextPage}
            >
              <span>{history.isFetchingNextPage ? "正在加载" : "加载更多"}</span>
              <ArrowDown size={16} aria-hidden="true" />
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
