import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  CalendarClock,
  FileText,
  History,
  MessageSquareText,
  Plus,
  RefreshCw,
  Search,
} from "lucide-react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import { EmptyState } from "../components/EmptyState";
import { ErrorNotice } from "../components/Feedback";
import { LoadingRows } from "../components/LoadingRows";
import { useSessionGuard } from "../hooks/useSessionGuard";
import { formatDate, stateLabel, taskTypeLabels } from "../utils/format";
import { userError } from "../utils/errors";

const directionLabels = {
  backend: "后端方向",
  frontend: "前端方向",
  fullstack: "全栈方向",
};

export function WorkspacePage() {
  const dashboard = useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: api.dashboard,
  });
  useSessionGuard(dashboard.error);

  const displayName =
    dashboard.data?.user.display_name?.trim() || "你好，面试者";
  const recentTasks = dashboard.data?.recent_tasks ?? [];
  const recentInterviews = dashboard.data?.recent_interviews ?? [];
  const hasActivity = recentTasks.length > 0 || recentInterviews.length > 0;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">WORKSPACE / OVERVIEW</p>
          <h1>{displayName}</h1>
          <p className="page-lede">
            这里汇总你的最近任务和模拟面试。先从下方记录继续，或查看完整历史。
          </p>
        </div>
        <div className="page-header-actions">
          <Link className="primary-button primary-button--link" to="/qa">
            <Search size={17} aria-hidden="true" />
            <span>技术问答</span>
          </Link>
          <Link className="primary-button primary-button--link" to="/resumes/new">
            <Plus size={17} aria-hidden="true" />
            <span>上传简历</span>
          </Link>
          <Link className="secondary-button secondary-button--link" to="/history">
            <History size={17} aria-hidden="true" />
            <span>全部历史</span>
          </Link>
        </div>
      </header>

      {dashboard.isPending && (
        <section className="content-section" aria-label="工作台加载中">
          <LoadingRows rows={5} />
        </section>
      )}

      {dashboard.isError && (
        <ErrorNotice
          message={userError(dashboard.error)}
          onRetry={() => void dashboard.refetch()}
        />
      )}

      {dashboard.isSuccess && (
        <>
          <section className="summary-strip" aria-label="工作台摘要">
            <div className="summary-item">
              <span className="summary-icon" aria-hidden="true">
                <FileText size={19} />
              </span>
              <div>
                <span>最近任务</span>
                <strong>{recentTasks.length}</strong>
              </div>
            </div>
            <div className="summary-item">
              <span className="summary-icon" aria-hidden="true">
                <MessageSquareText size={19} />
              </span>
              <div>
                <span>最近面试</span>
                <strong>{recentInterviews.length}</strong>
              </div>
            </div>
            <div className="summary-item summary-item--wide">
              <span className="summary-icon" aria-hidden="true">
                <CalendarClock size={19} />
              </span>
              <div>
                <span>服务端时间</span>
                <strong className="summary-time">
                  {formatDate(dashboard.data.server_time)}
                </strong>
              </div>
            </div>
          </section>

          {!hasActivity && (
            <section className="content-section">
              <EmptyState
                title="工作台还很安静"
                description="上传第一份简历，开始生成结构化分析和技术面试题目。"
                action={
                  <Link className="text-button text-button--link" to="/resumes/new">
                    上传简历
                    <ArrowRight size={15} aria-hidden="true" />
                  </Link>
                }
              />
            </section>
          )}

          {hasActivity && (
            <div className="dashboard-grid">
              <section className="content-section" aria-labelledby="recent-tasks-title">
                <div className="section-heading">
                  <div>
                    <p className="section-kicker">TASKS</p>
                    <h2 id="recent-tasks-title">最近任务</h2>
                  </div>
                  <Link className="quiet-link" to="/history?type=resume">
                    查看全部
                  </Link>
                </div>
                <div className="record-list">
                  {recentTasks.map((task) => (
                    <article className="record-row" key={`${task.type}-${task.id}`}>
                      <span className="record-type" aria-hidden="true">
                        {task.type === "resume" ? (
                          <FileText size={18} />
                        ) : (
                          <MessageSquareText size={18} />
                        )}
                      </span>
                      <div className="record-copy">
                        <strong title={task.title}>{task.title}</strong>
                        <span>
                          {taskTypeLabels[task.type]} · {formatDate(task.updated_at)}
                        </span>
                      </div>
                      <span className="state-pill">{stateLabel(task.state)}</span>
                      <Link
                        className="record-action"
                        to={
                          task.type === "resume"
                            ? `/resumes/${task.id}`
                            : `/qa/${task.id}`
                        }
                        aria-label={`查看 ${task.title}`}
                      >
                        <ArrowRight size={16} aria-hidden="true" />
                      </Link>
                    </article>
                  ))}
                </div>
              </section>

              <section className="content-section" aria-labelledby="recent-interviews-title">
                <div className="section-heading">
                  <div>
                    <p className="section-kicker">INTERVIEWS</p>
                    <h2 id="recent-interviews-title">最近面试</h2>
                  </div>
                  <Link className="quiet-link" to="/history?type=interview">
                    查看全部
                  </Link>
                </div>
                <div className="record-list">
                  {recentInterviews.map((interview) => (
                    <article className="record-row" key={interview.id}>
                      <span className="record-type" aria-hidden="true">
                        <MessageSquareText size={18} />
                      </span>
                      <div className="record-copy">
                        <strong>{directionLabels[interview.direction]}</strong>
                        <span>{formatDate(interview.updated_at)}</span>
                      </div>
                      <span className="state-pill">{stateLabel(interview.state)}</span>
                    </article>
                  ))}
                </div>
              </section>
            </div>
          )}
        </>
      )}

      {dashboard.isFetching && !dashboard.isPending && (
        <button
          type="button"
          className="floating-refresh"
          onClick={() => void dashboard.refetch()}
          disabled
          aria-label="正在刷新"
        >
          <RefreshCw className="spin" size={16} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}
