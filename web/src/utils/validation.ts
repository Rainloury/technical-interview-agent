export const MIN_PASSWORD_LENGTH = 12;

export function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

export function passwordError(value: string): string | undefined {
  if (!value) {
    return "请输入密码。";
  }
  if (value.length < MIN_PASSWORD_LENGTH) {
    return `密码至少需要 ${MIN_PASSWORD_LENGTH} 个字符。`;
  }
  if (value.length > 128) {
    return "密码不能超过 128 个字符。";
  }
  return undefined;
}
