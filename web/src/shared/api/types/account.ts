export type DataDeletionState =
  | "requested"
  | "deleting"
  | "completed"
  | "failed";

export interface DataDeletionAccepted {
  request_id: string;
  state: "requested";
  accepted_at: string;
}

export interface DataDeletionStatus {
  request_id: string;
  state: DataDeletionState;
  scope: string[];
  result: Record<string, unknown> | null;
  error_code: string | null;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

