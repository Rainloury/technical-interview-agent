const CSRF_COOKIE = "interview_csrf";

export function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  for (const part of document.cookie.split(";")) {
    const value = part.trim();
    if (value.startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length));
    }
  }
  return null;
}

export function readCsrfToken(): string | null {
  return readCookie(CSRF_COOKIE);
}
