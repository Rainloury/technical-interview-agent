export type DocumentState = "uploaded" | "processing" | "ready" | "failed" | "deleted";

export interface DocumentAccepted {
  document_id: string;
  state: DocumentState;
  created_at: string;
}

export interface DocumentBatchAccepted {
  documents: DocumentAccepted[];
  original_filenames: string[];
}

export interface DocumentItem {
  id: string;
  title: string;
  original_filename: string;
  state: DocumentState;
  chunk_count: number;
  failure_code: string | null;
  error_message: string | null;
  index_version: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  retention_expires_at: string;
  visibility: "private" | "shared";
  can_delete: boolean;
}

export interface DocumentPage {
  items: DocumentItem[];
  next_cursor: string | null;
}

