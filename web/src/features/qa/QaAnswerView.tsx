import type { QaAnswer, QaEvidence } from "@/shared/api/types";

export function AnswerBody({ answer }: { answer: QaAnswer }) {
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

export function EvidenceCard({ item }: { item: QaEvidence }) {
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
        <span className="source-kind">
          {item.source_kind === "user_document" ? "个人资料" : "系统资料"}
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
