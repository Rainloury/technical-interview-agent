const DEFAULT_RETURN_PATH = "/workspace";

export function safeReturnTo(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) {
    return DEFAULT_RETURN_PATH;
  }
  return value;
}
