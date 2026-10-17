import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { AuthLayout } from "../components/AuthLayout";
import { ErrorNotice, SuccessNotice } from "../components/Feedback";
import { FormField } from "../components/FormField";
import { userError } from "../utils/errors";
import { isValidEmail } from "../utils/validation";

export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [emailError, setEmailError] = useState<string>();
  const requestReset = useMutation({
    mutationFn: () => api.requestPasswordReset(email),
  });

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isValidEmail(email)) {
      setEmailError("请输入有效的邮箱地址。");
      return;
    }
    setEmailError(undefined);
    requestReset.mutate();
  };

  return (
    <AuthLayout
      title="找回密码"
      subtitle="输入账号邮箱，我们会发送一次性重置链接。"
      footer={
        <p>
          想起密码了？ <Link to="/login">返回登录</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {requestReset.isSuccess && (
          <SuccessNotice message="请求已受理。如果该邮箱对应账号，重置邮件将很快送达。请检查收件箱和垃圾邮件。" />
        )}
        {requestReset.isError && <ErrorNotice message={userError(requestReset.error)} />}
        <FormField
          label="邮箱"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="name@example.com"
          value={email}
          error={emailError}
          disabled={requestReset.isSuccess}
          onChange={(event) => {
            setEmail(event.target.value);
            setEmailError(undefined);
            requestReset.reset();
          }}
        />
        <button
          className="primary-button"
          type="submit"
          disabled={requestReset.isPending || requestReset.isSuccess}
        >
          <span>{requestReset.isPending ? "正在提交" : "发送重置链接"}</span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
        {requestReset.isSuccess && (
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              requestReset.reset();
              setEmail("");
            }}
          >
            使用其他邮箱
          </button>
        )}
      </form>
    </AuthLayout>
  );
}
