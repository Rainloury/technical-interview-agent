export const MIN_PASSWORD_LENGTH = 12;

export const MAX_QUESTION_LENGTH = 2000;

const MAX_FILE_BYTES = 10 * 1024 * 1024;

const urlPattern =
  /(?:\b[a-z][a-z0-9+.-]*:\/\/\S+)|(?<![\w.-])(?:www\.)[a-z0-9.-]+\.[a-z]{2,63}|(?<![\w.-])localhost(?::\d{1,5})?|(?<![\w.-])(?:\d{1,3}\.){3}\d{1,3}/i;

interface UploadRule {
  extensions: readonly string[];
  emptyMessage: string;
  extensionMessage: string;
}

const resumeRule: UploadRule = {
  extensions: [".pdf", ".docx"],
  emptyMessage: "请选择一份 PDF 或 DOCX 简历。",
  extensionMessage: "仅支持 PDF 或 DOCX 文件。",
};

const documentRule: UploadRule = {
  extensions: [".pdf", ".docx", ".txt", ".md"],
  emptyMessage: "请选择资料文件。",
  extensionMessage: "仅支持 PDF、DOCX、TXT 或 Markdown 文件。",
};

function validateUpload(file: File | null, rule: UploadRule): string | null {
  if (!file) {
    return rule.emptyMessage;
  }
  const name = file.name.toLowerCase();
  if (!rule.extensions.some((extension) => name.endsWith(extension))) {
    return rule.extensionMessage;
  }
  if (file.size === 0) {
    return "文件不能为空。";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "文件不能超过 10 MB。";
  }
  return null;
}

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

export function validateQuestion(value: string): string | null {
  const question = value.trim();
  if (!question) {
    return "请输入一个技术问题。";
  }
  if (question.length > MAX_QUESTION_LENGTH) {
    return "问题不能超过 2000 个字符。";
  }
  if (urlPattern.test(question)) {
    return "问题中不能包含 URL，检索只使用已审核知识源。";
  }
  return null;
}

export function validateFile(file: File | null): string | null {
  return validateUpload(file, resumeRule);
}

export function validateDocument(file: File | null): string | null {
  return validateUpload(file, documentRule);
}

export function validateDocuments(files: File[]): string | null {
  if (files.length === 0) {
    return "请选择资料文件。";
  }
  for (const file of files) {
    const error = validateDocument(file);
    if (error) {
      return `${file.name}：${error}`;
    }
  }
  return null;
}
