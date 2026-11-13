import { request } from "@/shared/api/http";
import type { LoginResponse, RegisterResponse, Session } from "@/shared/api/types";

export const authEndpoints = {
  session: () => request<Session>("/api/v1/auth/session"),
  login: (email: string, password: string) =>
    request<LoginResponse>("/api/v1/auth/login", {
      method: "POST",
      body: { email, password },
    }),
  register: (email: string, password: string) =>
    request<RegisterResponse>("/api/v1/auth/register", {
      method: "POST",
      body: { email, password },
    }),
  logout: () => request<void>("/api/v1/auth/logout", { method: "POST" }),
  requestPasswordReset: (email: string) =>
    request<{ accepted: true }>("/api/v1/auth/password-reset/request", {
      method: "POST",
      body: { email },
    }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    request<void>("/api/v1/auth/password-reset/confirm", {
      method: "POST",
      body: { token, new_password: newPassword },
    }),
};
