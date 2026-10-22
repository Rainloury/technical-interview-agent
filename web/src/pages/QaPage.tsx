import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  CornerDownLeft,
  MessageSquareText,
  ShieldCheck,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import type { QaAnswerPreference } from "../api/types";
import { ErrorNotice } from "../components/Feedback";
import { userError } from "../utils/errors";

const MAX_QUESTION_LENGTH = 2000;

const urlPattern =
  /(?:\b[a-z][a-z0-9+.-]*:\/\/\S+)|(?<![\w.-])(?:www\.)[a-z0-9.-]+\.[a-z]{2,63}|(?<![\w.-])localhost(?::\d{1,5})?|(?<![\w.-])(?:\d{1,3}\.){3}\d{1,3}/i;

export function validateQuestion(value: string): string | null {
  const question = value.trim();
  if (!question) {
    return "请输入一个技术问题。";
  }
  if (question.length > MAX_QUESTION_LENGTH) {
    return "问题不能超过 2000 个字符。";
  }
  if (urlPattern.test(question)) {
    return "问题中不能包含 URL，检索只使用已审核知识源。";
  }
  return null;
}

export function QaPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const prefilledQuestion =
    typeof location.state === "object" &&
    location.state !== null &&
    "question" in location.state &&
    typeof location.state.question === "string"
      ? location.state.question.slice(0, MAX_QUESTION_LENGTH)
      : "";
  const [question, setQuestion] = useState(prefilledQuestion);
  const [preference, setPreference] =
    useState<QaAnswerPreference>("concise");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const [requestedQuestion, setRequestedQuestion] = useState("");
  const [requestedPreference, setRequestedPreference] =
    useState<QaAnswerPreference | null>(null);

  const create = useMutation({
    mutationFn: ({
      value,
      answerPreference,
      key,
    }: {
      value: string;
      answerPreference: QaAnswerPreference;
      key: string;
    }) => api.createQa(value.trim(), answerPreference, key),
    onSuccess: (accepted) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("qa") });
      navigate(`/qa/${accepted.qa_request_id}`, {
        replace: true,
        state: { question: null },
      });
    },
  });

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateQuestion(question);
    setQuestionError(error);
    if (error) {
      return;
    }
    let key = requestKey;
    if (
      !key ||
      requestedQuestion !== question ||
      requestedPreference !== preference
    ) {
      key = newIdempotencyKey();
      setRequestKey(key);
      setRequestedQuestion(question);
      setRequestedPreference(preference);
    }
    create.mutate({
      value: question,
      answerPreference: preference,
      key,
    });
  };

  const conflict =
    create.error instanceof ApiError && create.error.code === "idempotency_conflict";

  return (
    <div className="page qa-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">KNOWLEDGE / QA</p>
          <h1>技术问答</h1>
          <p className="page-lede">
            提交一个具体的技术问题。系统会先检索当前账号已就绪资料与系统资料，再给出带公开证据的回答。
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      <div className="qa-layout">
        <section className="content-section qa-composer">
          <form className="qa-form" onSubmit={submit} noValidate>
            <div className="field">
              <label htmlFor="qa-question">技术问题</label>
              <textarea
                id="qa-question"
                className={`text-area ${questionError ? "text-area--error" : ""}`}
                value={question}
                onChange={(event) => {
                  const nextQuestion = event.target.value.slice(
                    0,
                    MAX_QUESTION_LENGTH,
                  );
                  setQuestion(nextQuestion);
                  setRequestKey(null);
                  if (questionError) {
                    setQuestionError(validateQuestion(nextQuestion));
                  }
                }}
                disabled={create.isPending}
                maxLength={MAX_QUESTION_LENGTH}
                rows={7}
                placeholder="例如：在高并发写入场景下，怎样设计有界重试并避免重复提交？"
              />
              <div className="qa-input-meta">
                <span>不要粘贴链接或外部文档地址。</span>
                <span className={question.length > 1900 ? "field-error" : undefined}>
                  {question.length} / {MAX_QUESTION_LENGTH}
                </span>
              </div>
              {questionError && (
                <p className="field-error" role="alert">
                  {questionError}
                </p>
              )}
            </div>

            <fieldset className="qa-preference field">
              <legend>回答详细程度</legend>
              <div className="qa-choice-row">
                <label
                  className={`qa-choice ${
                    preference === "concise" ? "qa-choice--active" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="answer-preference"
                    value="concise"
                    checked={preference === "concise"}
                    onChange={() => {
                      setPreference("concise");
                      setRequestKey(null);
                    }}
                  />
                  <span>
                    <strong>简明回答</strong>
                    <small>先给结论，再补充关键理由。</small>
                  </span>
                </label>
                <label
                  className={`qa-choice ${
                    preference === "detailed" ? "qa-choice--active" : ""
                  }`}
                >
                  <input
                    type="radio"
                    name="answer-preference"
                    value="detailed"
                    checked={preference === "detailed"}
                    onChange={() => {
                      setPreference("detailed");
                      setRequestKey(null);
                    }}
                  />
                  <span>
                    <strong>详细回答</strong>
                    <small>展开机制、权衡与适用边界。</small>
                  </span>
                </label>
              </div>
            </fieldset>

            {create.isError && (
              <ErrorNotice
                message={userError(create.error)}
                onRetry={
                  conflict
                    ? undefined
                    : () =>
                        create.mutate({
                          value: question,
                          answerPreference: preference,
                          key: requestKey ?? newIdempotencyKey(),
                        })
                }
              />
            )}

            <div className="qa-form-actions">
              <button
                type="submit"
                className="primary-button"
                disabled={create.isPending || !question.trim()}
              >
                <CornerDownLeft size={17} aria-hidden="true" />
                <span>{create.isPending ? "正在提交" : "开始检索"}</span>
              </button>
            </div>
          </form>
        </section>

        <aside className="qa-notes" aria-label="问答范围">
          <div className="qa-note">
            <span className="qa-note-icon" aria-hidden="true">
              <ShieldCheck size={19} />
            </span>
            <div>
              <h2>账号内资料优先</h2>
              <p>检索范围包含当前账号已就绪资料，以及最新发布且已加入白名单的系统知识。</p>
            </div>
          </div>
          <div className="qa-note">
            <span className="qa-note-icon" aria-hidden="true">
              <MessageSquareText size={19} />
            </span>
            <div>
              <h2>证据可以追溯</h2>
              <p>回答会标注公开引用编号；内部 UUID 和原始来源地址不会展示。</p>
            </div>
          </div>
          <Link className="text-button text-button--link" to="/history?type=qa">
            查看问答历史
            <ArrowRight size={15} aria-hidden="true" />
          </Link>
        </aside>
      </div>
    </div>
  );
}
