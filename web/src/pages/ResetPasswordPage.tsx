import { useMutation } from "@tanstack/react-query";
import { ArrowRight, KeyRound } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/context";
import { AuthLayout } from "../components/AuthLayout";
import { ErrorNotice, SuccessNotice } from "../components/Feedback";
import { FormField } from "../components/FormField";
import { userError } from "../utils/errors";
import { passwordError } from "../utils/validation";

interface FormErrors {
  password?: string;
  confirmPassword?: string;
}

export function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { clear } = useAuth();
  const token = searchParams.get("token")?.trim() ?? "";
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const resetPassword = useMutation({
    mutationFn: () => api.confirmPasswordReset(token, password),
    onSuccess: () => {
      clear();
    },
  });

  const validate = (): boolean => {
    const nextErrors: FormErrors = {};
    const nextPasswordError = passwordError(password);
    if (nextPasswordError) {
      nextErrors.password = nextPasswordError;
    }
    if (confirmPassword !== password) {
      nextErrors.confirmPassword = "两次输入的密码不一致。";
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (validate()) {
      resetPassword.mutate();
    }
  };

  if (!token) {
    return (
      <AuthLayout
        title="重置密码"
        subtitle="重置链接缺少必要信息。"
        footer={
          <p>
            需要新的链接？ <Link to="/forgot-password">重新申请</Link>
          </p>
        }
      >
        <div className="auth-empty">
          <KeyRound size={24} aria-hidden="true" />
          <p>该链接不完整或已失效，请重新发起密码重置。</p>
          <Link className="primary-button primary-button--link" to="/forgot-password">
            <span>重新申请</span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        </div>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title="设置新密码"
      subtitle="新密码保存后，所有旧会话将立即失效。"
      footer={
        <p>
          返回 <Link to="/login">登录</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {resetPassword.isSuccess && (
          <SuccessNotice message="密码已更新，旧会话已失效。请使用新密码登录。" />
        )}
        {resetPassword.isError && <ErrorNotice message={userError(resetPassword.error)} />}
        <FormField
          label="新密码"
          type="password"
          name="new-password"
          autoComplete="new-password"
          placeholder="至少 12 个字符"
          value={password}
          error={errors.password}
          hint="使用至少 12 个字符，避免与其他网站重复。"
          password
          disabled={resetPassword.isSuccess}
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors((current) => ({ ...current, password: undefined }));
            resetPassword.reset();
          }}
        />
        <FormField
          label="确认新密码"
          type="password"
          name="confirm-new-password"
          autoComplete="new-password"
          placeholder="再次输入新密码"
          value={confirmPassword}
          error={errors.confirmPassword}
          password
          revealLabel="显示确认新密码"
          hideLabel="隐藏确认新密码"
          disabled={resetPassword.isSuccess}
          onChange={(event) => {
            setConfirmPassword(event.target.value);
            setErrors((current) => ({ ...current, confirmPassword: undefined }));
            resetPassword.reset();
          }}
        />
        {resetPassword.isSuccess ? (
          <button
            type="button"
            className="primary-button"
            onClick={() => navigate("/login", { replace: true })}
          >
            <span>前往登录</span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        ) : (
          <button className="primary-button" type="submit" disabled={resetPassword.isPending}>
            <span>{resetPassword.isPending ? "正在更新" : "更新密码"}</span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        )}
      </form>
    </AuthLayout>
  );
}
