import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";

import { api } from "../api/client";
import type {
  QaAnswer,
  QaEvidence,
  QaRequest,
  QaStreamEvent,
} from "../api/types";
import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

const evidence: QaEvidence = {
  citation_id: "evidence-1",
  title: "有界重试指南",
  section_path: "可靠性 / 重试",
  snippet: "使用有界退避、抖动与幂等键，避免重复提交。",
  relevance_score: 0.91,
  source_state: "available",
  source_kind: "system",
};

const answer: QaAnswer = {
  direct_answer: "使用有界退避和幂等键隔离重复提交。",
  explanation: "限制重试次数，并用指数退避与随机抖动分散压力。\n\n每个请求都应携带稳定的幂等键。",
  evidence_ids: ["evidence-1"],
  extended_questions: ["如何选择退避上限？"],
  evidence_status: "supported",
};

function qaRequest(overrides: Partial<QaRequest> = {}): QaRequest {
  return {
    id: "qa-1",
    question: "如何设计有界重试？",
    answer_preference: "concise",
    state: "answering",
    answer: null,
    evidence: [],
    evidence_status: "insufficient",
    error: null,
    created_at: "2026-10-17T08:00:00Z",
    completed_at: null,
    last_event_seq: 2,
    ...overrides,
  };
}

describe("QaDetailPage", () => {
  it("resumes from last_event_seq, renders the answer once, and ignores duplicate events", async () => {
    let afterSeq: number | undefined;
    let snapshotReads = 0;
    const streamedEvents: QaStreamEvent[] = [
      {
        id: 3,
        type: "evidence",
        data: { items: [evidence] },
      },
      {
        id: 4,
        type: "completed",
        data: { answer, evidence: [evidence] },
      },
    ];
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () => {
        snapshotReads += 1;
        if (snapshotReads > 1) {
          return HttpResponse.json(
            qaRequest({
              state: "completed",
              answer,
              evidence: [evidence],
              evidence_status: "supported",
              completed_at: "2026-10-17T08:00:05Z",
              last_event_seq: 4,
            }),
          );
        }
        return HttpResponse.json(qaRequest());
      }),
    );
    const stream = vi.spyOn(api, "streamQa").mockImplementation(async (_id, options) => {
      afterSeq = options.afterSeq;
      await Promise.resolve();
      const [evidenceEvent, completedEvent] = streamedEvents;
      if (!evidenceEvent || !completedEvent) {
        throw new Error("missing streamed QA events");
      }
      options.onEvent(evidenceEvent);
      options.onEvent(evidenceEvent);
      options.onEvent(completedEvent);
    });
    const { container } = renderApp("/qa/qa-1");

    expect(await screen.findByText(answer.direct_answer)).toBeInTheDocument();
    expect(screen.getByText("有界重试指南")).toBeInTheDocument();
    expect(screen.getByText("系统资料")).toBeInTheDocument();
    expect(container.querySelectorAll(".qa-evidence-card")).toHaveLength(1);
    expect(afterSeq).toBe(2);
    expect(stream).toHaveBeenCalledWith("qa-1", expect.any(Object));
    await waitFor(() => expect(snapshotReads).toBeGreaterThan(1));
    expect(container.textContent).not.toContain("qa-evidence-uuid");
    expect(container.textContent).not.toContain("https://source.example");
  });

  it("labels private document evidence", async () => {
    const privateEvidence: QaEvidence = {
      ...evidence,
      source_kind: "user_document",
      title: "个人 Redis 笔记",
    };
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () =>
        HttpResponse.json(
          qaRequest({
            state: "completed",
            answer: { ...answer, evidence_ids: ["evidence-1"] },
            evidence: [privateEvidence],
            evidence_status: "supported",
            completed_at: "2026-10-17T08:00:05Z",
            last_event_seq: 3,
          }),
        ),
      ),
    );
    renderApp("/qa/qa-1");

    expect(await screen.findByText("个人 Redis 笔记")).toBeInTheDocument();
    expect(screen.getByText("个人资料")).toBeInTheDocument();
  });

  it("does not let an answering snapshot overwrite a completed stream event", async () => {
    let resolveSnapshot: ((response: Response) => void) | undefined;
    const staleSnapshot = new Promise<Response>((resolve) => {
      resolveSnapshot = resolve;
    });
    let snapshotReads = 0;
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", async () => {
        snapshotReads += 1;
        if (snapshotReads === 1) {
          return HttpResponse.json(qaRequest());
        }
        return staleSnapshot;
      }),
    );
    vi.spyOn(api, "streamQa").mockImplementation(async (_id, options) => {
      await Promise.resolve();
      options.onEvent({
        id: 3,
        type: "completed",
        data: { answer, evidence: [evidence] },
      });
    });
    const { container } = renderApp("/qa/qa-1");

    expect(await screen.findByText(answer.direct_answer)).toBeInTheDocument();
    expect(await screen.findByText("有界重试指南")).toBeInTheDocument();
    resolveSnapshot?.(HttpResponse.json(qaRequest()) as unknown as Response);

    await waitFor(() => expect(snapshotReads).toBeGreaterThan(1));
    expect(screen.getByText(answer.direct_answer)).toBeInTheDocument();
    expect(screen.getByText("有界重试指南")).toBeInTheDocument();
    expect(container.querySelectorAll(".qa-evidence-card")).toHaveLength(1);
  });

  it("shows a model-knowledge answer without evidence cards", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () => HttpResponse.json(qaRequest())),
    );
    vi.spyOn(api, "streamQa").mockImplementation(async (_id, options) => {
      options.onEvent({
        id: 3,
        type: "completed",
        data: {
          answer: {
            direct_answer: "当前资料不足，以下是通用建议。",
            explanation: "可以为检索失败保留明确的知识状态。",
            evidence_ids: [],
            extended_questions: [],
            evidence_status: "model_knowledge",
          },
          evidence: [],
        },
      });
    });
    const { container } = renderApp("/qa/qa-1");

    expect(
      await screen.findByText("当前资料不足，以下是通用建议。"),
    ).toBeInTheDocument();
    expect(screen.getByText("模型知识")).toBeInTheDocument();
    expect(container.querySelectorAll(".qa-evidence-card")).toHaveLength(0);
    expect(
      screen.getByText("本次回答没有引用内部资料"),
    ).toBeInTheDocument();
  });

  it("renders insufficiency and failure states without fabricating evidence", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () =>
        HttpResponse.json(
          qaRequest({
            state: "completed",
            last_event_seq: 3,
            completed_at: "2026-10-17T08:00:05Z",
            answer: {
              direct_answer: "现有信息不足。",
              explanation: "请补充并发量、失败模式和重试预算。",
              evidence_ids: [],
              extended_questions: [],
              evidence_status: "insufficient",
            },
            evidence_status: "insufficient",
          }),
        ),
      ),
    );
    const { unmount } = renderApp("/qa/qa-1");

    expect(await screen.findByText("现有信息不足。")).toBeInTheDocument();
    expect(screen.getByText("信息不足")).toBeInTheDocument();
    unmount();

    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () =>
        HttpResponse.json(
          qaRequest({
            state: "failed",
            last_event_seq: 3,
            error: {
              code: "provider_unavailable",
              message: "模型服务暂不可用，请稍后重试。",
              retryable: true,
            },
          }),
        ),
      ),
    );
    renderApp("/qa/qa-1");

    expect(
      await screen.findByRole("heading", { name: "问答暂未完成" }),
    ).toBeInTheDocument();
    expect(screen.getByText("模型服务暂不可用，请稍后重试。")).toBeInTheDocument();
  });

  it("does not open a stream for an already terminal request", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/qa/qa-1", () =>
        HttpResponse.json(
          qaRequest({
            state: "completed",
            answer,
            evidence: [evidence],
            evidence_status: "supported",
            completed_at: "2026-10-17T08:00:05Z",
          }),
        ),
      ),
    );
    const stream = vi.spyOn(api, "streamQa");
    renderApp("/qa/qa-1");

    expect(await screen.findByText(answer.direct_answer)).toBeInTheDocument();
    await waitFor(() => expect(stream).not.toHaveBeenCalled());
  });
});
