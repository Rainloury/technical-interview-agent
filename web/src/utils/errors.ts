import { ApiError } from "../api/client";

export function userError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return "出现了未预期的问题，请重试。";
}
