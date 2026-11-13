export interface UserSummary {
  id: string;
  display_name: string | null;
  role: "user" | "admin";
}

export interface SessionSummary {
  expires_at: string;
}

export interface Session {
  user: UserSummary;
  session: SessionSummary;
}

export interface LoginResponse {
  user: UserSummary;
  session: SessionSummary;
}

export interface RegisterResponse {
  accepted: true;
  next_action: "login";
}

export interface ApiErrorBody {
  error?: {
    code?: string;
    message?: string;
    retryable?: boolean;
    request_id?: string;
  };
}
