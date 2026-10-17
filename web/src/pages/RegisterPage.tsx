import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { api } from "../api/client";
import { AuthLayout } from "../components/AuthLayout";
import { ErrorNotice, SuccessNotice } from "../components/Feedback";
import { FormField } from "../components/FormField";
import { userError } from "../utils/errors";
import { isValidEmail, passwordError } from "../utils/validation";

interface FormErrors {
  email?: string;
  password?: string;
  confirmPassword?: string;
}

export function RegisterPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const register = useMutation({
    mutationFn: () => api.register(email, password),
  });

  const validate = (): boolean => {
    const nextErrors: FormErrors = {};
    if (!isValidEmail(email)) {
      nextErrors.email = "请输入有效的邮箱地址。";
    }
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
      register.mutate();
    }
  };

  return (
    <AuthLayout
      title="创建账号"
      subtitle="注册后使用邮箱和密码登录。"
      footer={
        <p>
          已有账号？ <Link to="/login">返回登录</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {register.isSuccess && (
          <SuccessNotice message="注册请求已受理。请前往登录；该结果不会透露账号是否已存在。" />
        )}
        {register.isError && <ErrorNotice message={userError(register.error)} />}
        <FormField
          label="邮箱"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="name@example.com"
          value={email}
          error={errors.email}
          disabled={register.isSuccess}
          onChange={(event) => {
            setEmail(event.target.value);
            setErrors((current) => ({ ...current, email: undefined }));
            register.reset();
          }}
        />
        <FormField
          label="密码"
          type="password"
          name="password"
          autoComplete="new-password"
          placeholder="至少 12 个字符"
          value={password}
          error={errors.password}
          hint="使用至少 12 个字符，避免与其他网站重复。"
          password
          disabled={register.isSuccess}
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors((current) => ({ ...current, password: undefined }));
            register.reset();
          }}
        />
        <FormField
          label="确认密码"
          type="password"
          name="confirm-password"
          autoComplete="new-password"
          placeholder="再次输入密码"
          value={confirmPassword}
          error={errors.confirmPassword}
          password
          revealLabel="显示确认密码"
          hideLabel="隐藏确认密码"
          disabled={register.isSuccess}
          onChange={(event) => {
            setConfirmPassword(event.target.value);
            setErrors((current) => ({ ...current, confirmPassword: undefined }));
            register.reset();
          }}
        />
        {register.isSuccess ? (
          <Link className="primary-button primary-button--link" to="/login">
            <span>前往登录</span>
            <ArrowRight size={18} aria-hidden="true" />
          </Link>
        ) : (
          <button className="primary-button" type="submit" disabled={register.isPending}>
            <span>{register.isPending ? "正在提交" : "创建账号"}</span>
            <ArrowRight size={18} aria-hidden="true" />
          </button>
        )}
      </form>
    </AuthLayout>
  );
}
