import { describe, expect, it } from "vitest";

import {
  isValidEmail,
  MAX_QUESTION_LENGTH,
  MIN_PASSWORD_LENGTH,
  passwordError,
  validateDocument,
  validateDocuments,
  validateFile,
  validateQuestion,
} from "./validation";

function oversizedFile(name: string): File {
  const file = new File(["x"], name);
  Object.defineProperty(file, "size", { value: 10 * 1024 * 1024 + 1 });
  return file;
}

describe("account validation", () => {
  it("accepts a trimmed email and rejects malformed ones", () => {
    expect(isValidEmail("  user@example.com ")).toBe(true);
    expect(isValidEmail("user@example")).toBe(false);
    expect(isValidEmail("user example.com")).toBe(false);
  });

  it("enforces the password length window", () => {
    expect(passwordError("")).toBe("请输入密码。");
    expect(passwordError("a".repeat(MIN_PASSWORD_LENGTH - 1))).toContain("12");
    expect(passwordError("a".repeat(MIN_PASSWORD_LENGTH))).toBeUndefined();
    expect(passwordError("a".repeat(129))).toBe("密码不能超过 128 个字符。");
  });
});

describe("question validation", () => {
  it("rejects empty, oversized and URL-bearing questions", () => {
    expect(validateQuestion("   ")).toBe("请输入一个技术问题。");
    expect(validateQuestion("x".repeat(MAX_QUESTION_LENGTH + 1))).toBe(
      "问题不能超过 2000 个字符。",
    );
    expect(validateQuestion("参考 https://example.com/a 的实现")).toBe(
      "问题中不能包含 URL，检索只使用已审核知识源。",
    );
    expect(validateQuestion("什么是 RRF 融合检索？")).toBeNull();
  });
});

describe("upload validation", () => {
  it("keeps the resume allowlist narrower than the document allowlist", () => {
    const markdown = new File(["x"], "notes.md");
    expect(validateFile(markdown)).toBe("仅支持 PDF 或 DOCX 文件。");
    expect(validateDocument(markdown)).toBeNull();

    const pdf = new File(["x"], "resume.pdf");
    expect(validateFile(pdf)).toBeNull();
    expect(validateDocument(pdf)).toBeNull();
  });

  it("shares the empty-file and size-limit rules", () => {
    expect(validateFile(null)).toBe("请选择一份 PDF 或 DOCX 简历。");
    expect(validateDocument(null)).toBe("请选择资料文件。");
    expect(validateFile(new File([], "resume.pdf"))).toBe("文件不能为空。");
    expect(validateDocument(oversizedFile("notes.txt"))).toBe("文件不能超过 10 MB。");
    expect(validateFile(oversizedFile("resume.docx"))).toBe("文件不能超过 10 MB。");
  });

  it("reports the offending filename for a batch", () => {
    expect(validateDocuments([])).toBe("请选择资料文件。");
    expect(validateDocuments([new File(["x"], "bad.exe")])).toBe(
      "bad.exe：仅支持 PDF、DOCX、TXT 或 Markdown 文件。",
    );
    expect(
      validateDocuments([new File(["x"], "a.pdf"), new File(["x"], "b.txt")]),
    ).toBeNull();
  });
});
