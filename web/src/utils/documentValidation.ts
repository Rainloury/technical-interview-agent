const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".txt", ".md"];

export function validateDocument(file: File | null): string | null {
  if (!file) {
    return "请选择资料文件。";
  }
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "仅支持 PDF、DOCX、TXT 或 Markdown 文件。";
  }
  if (file.size === 0) {
    return "文件不能为空。";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "文件不能超过 10 MB。";
  }
  return null;
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
