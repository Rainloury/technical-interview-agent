import { FileText, Trash2 } from "lucide-react";

import type { DocumentItem } from "@/shared/api/types";
import { formatDate } from "@/shared/lib/format";

const documentStates: Record<DocumentItem["state"], { label: string; tone: string }> = {
  uploaded: { label: "已上传", tone: "uploaded" },
  processing: { label: "处理中", tone: "processing" },
  ready: { label: "可检索", tone: "ready" },
  failed: { label: "索引失败", tone: "failed" },
  deleted: { label: "已删除", tone: "deleted" },
};

export function DocumentRow({
  document,
  onDelete,
  deleting,
  canDelete = document.can_delete,
  selected = false,
  onSelect,
  selectionDisabled = false,
}: {
  document: DocumentItem;
  onDelete: () => void;
  deleting: boolean;
  canDelete?: boolean;
  selected?: boolean;
  onSelect?: (checked: boolean) => void;
  selectionDisabled?: boolean;
}) {
  const status = documentStates[document.state];
  return (
    <article className="document-row">
      {onSelect && (
        <input
          className="document-checkbox"
          type="checkbox"
          aria-label={`选择 ${document.title}`}
          checked={selected}
          disabled={selectionDisabled}
          onChange={(event) => onSelect(event.target.checked)}
        />
      )}
      <span className="record-type" aria-hidden="true">
        <FileText size={18} />
      </span>
      <div className="record-copy">
        <strong title={document.title}>{document.title}</strong>
        <span>
          {document.original_filename} · {formatDate(document.updated_at)}
        </span>
        {document.state === "failed" && document.failure_code && (
          <span className="document-failure-code">{document.failure_code}</span>
        )}
      </div>
      <div className="document-meta">
        <span className={`document-scope document-scope--${document.visibility}`}>
          {document.visibility === "shared" ? "共享" : "个人"}
        </span>
        <span className={`state-pill state-pill--${status.tone}`}>{status.label}</span>
        <span>{document.chunk_count} 个分块</span>
      </div>
      {canDelete && (
        <button
          type="button"
          className="icon-button icon-button--danger"
          aria-label={`删除 ${document.title}`}
          onClick={onDelete}
          disabled={deleting}
        >
          <Trash2 size={17} aria-hidden="true" />
        </button>
      )}
    </article>
  );
}
