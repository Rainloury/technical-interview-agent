import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileText, Upload } from "lucide-react";
import { type ChangeEvent, type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { api, ApiError } from "../api/client";
import { newIdempotencyKey } from "../api/idempotency";
import { queryKeys } from "../api/queryKeys";
import { ErrorNotice } from "../components/Feedback";
import { userError } from "../utils/errors";

const MAX_FILE_BYTES = 10 * 1024 * 1024;
const ACCEPTED_EXTENSIONS = [".pdf", ".docx"];

export function validateFile(file: File | null): string | null {
  if (!file) {
    return "请选择一份 PDF 或 DOCX 简历。";
  }
  const lowerName = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((extension) => lowerName.endsWith(extension))) {
    return "仅支持 PDF 或 DOCX 文件。";
  }
  if (file.size === 0) {
    return "文件不能为空。";
  }
  if (file.size > MAX_FILE_BYTES) {
    return "文件不能超过 10 MB。";
  }
  return null;
}

export function ResumeUploadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [targetRole, setTargetRole] = useState("");
  const [fileError, setFileError] = useState<string | null>(null);
  const [requestKey, setRequestKey] = useState<string | null>(null);
  const [requestedFile, setRequestedFile] = useState<File | null>(null);
  const [requestedRole, setRequestedRole] = useState("");

  const upload = useMutation({
    mutationFn: ({
      selectedFile,
      role,
      key,
    }: {
      selectedFile: File;
      role: string;
      key: string;
    }) => api.uploadResume(selectedFile, role, key),
    onSuccess: (accepted) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      void queryClient.invalidateQueries({ queryKey: queryKeys.history("resume") });
      navigate(`/resumes/${accepted.resume_task_id}`, { replace: true });
    },
  });

  const handleFile = (event: ChangeEvent<HTMLInputElement>) => {
    const nextFile = event.target.files?.[0] ?? null;
    setFile(nextFile);
    setFileError(validateFile(nextFile));
    setRequestKey(null);
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const error = validateFile(file);
    setFileError(error);
    if (error || !file) {
      return;
    }
    let key = requestKey;
    if (!key || requestedFile !== file || requestedRole !== targetRole) {
      key = newIdempotencyKey();
      setRequestKey(key);
      setRequestedFile(file);
      setRequestedRole(targetRole);
    }
    upload.mutate({ selectedFile: file, role: targetRole, key });
  };

  const conflict =
    upload.error instanceof ApiError && upload.error.code === "idempotency_conflict";

  return (
    <div className="page resume-page">
      <header className="page-header">
        <div>
          <p className="eyebrow">RESUME / UPLOAD</p>
          <h1>上传简历</h1>
          <p className="page-lede">
            选择一份技术简历，服务端会提取经历并生成结构化分析。原始文件仅用于本次任务，可随时单独删除。
          </p>
        </div>
        <Link className="secondary-button secondary-button--link" to="/workspace">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>返回工作台</span>
        </Link>
      </header>

      <section className="content-section resume-form-section">
        <form className="resume-form" onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="resume-file">简历文件</label>
            <label className={`file-picker ${fileError ? "file-picker--error" : ""}`}>
              <FileText size={22} aria-hidden="true" />
              <span>
                <strong>{file?.name ?? "选择 PDF 或 DOCX"}</strong>
                <small>
                  {file
                    ? `${(file.size / 1024 / 1024).toFixed(2)} MB`
                    : "不超过 10 MB，最多 10 页"}
                </small>
              </span>
              <input
                id="resume-file"
                className="visually-hidden"
                type="file"
                accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleFile}
                disabled={upload.isPending}
              />
            </label>
            {fileError && (
              <p className="field-error" role="alert">
                {fileError}
              </p>
            )}
          </div>

          <div className="field">
            <label htmlFor="target-role">目标岗位（可选）</label>
            <input
              id="target-role"
              className="text-input"
              value={targetRole}
              onChange={(event) => {
                setTargetRole(event.target.value);
                setRequestKey(null);
              }}
              disabled={upload.isPending}
              placeholder="例如：高级后端工程师"
            />
            <p className="field-hint">当前版本以简历内容出题，岗位信息将在后续切片启用。</p>
          </div>

          {upload.isError && (
            <ErrorNotice
              message={userError(upload.error)}
              onRetry={conflict ? undefined : () => upload.mutate({
                selectedFile: file!,
                role: targetRole,
                key: requestKey ?? newIdempotencyKey(),
              })}
            />
          )}

          <div className="resume-form-actions">
            <Link className="secondary-button secondary-button--link" to="/workspace">
              取消
            </Link>
            <button
              className="primary-button"
              type="submit"
              disabled={upload.isPending || !file}
            >
              <Upload size={17} aria-hidden="true" />
              <span>{upload.isPending ? "正在上传" : "开始分析"}</span>
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
