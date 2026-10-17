import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { api } from "../api/client";
import { useAuth } from "../auth/context";
import { AuthLayout } from "../components/AuthLayout";
import { ErrorNotice } from "../components/Feedback";
import { FormField } from "../components/FormField";
import { userError } from "../utils/errors";
import { safeReturnTo } from "../utils/navigation";
import { isValidEmail } from "../utils/validation";

interface FormErrors {
  email?: string;
  password?: string;
}

export function LoginPage() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const returnTo = safeReturnTo(searchParams.get("returnTo"));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<FormErrors>({});
  const login = useMutation({
    mutationFn: () => api.login(email, password),
    onSuccess: async () => {
      await refresh();
      navigate(returnTo, { replace: true });
    },
  });

  const validate = (): boolean => {
    const nextErrors: FormErrors = {};
    if (!isValidEmail(email)) {
      nextErrors.email = "请输入有效的邮箱地址。";
    }
    if (!password) {
      nextErrors.password = "请输入密码。";
    }
    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (validate()) {
      login.mutate();
    }
  };

  return (
    <AuthLayout
      title="登录工作台"
      subtitle="使用你的账号继续准备技术面试。"
      footer={
        <p>
          还没有账号？ <Link to="/register">创建账号</Link>
        </p>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit} noValidate>
        {login.isError && <ErrorNotice message={userError(login.error)} />}
        <FormField
          label="邮箱"
          type="email"
          name="email"
          autoComplete="email"
          placeholder="name@example.com"
          value={email}
          error={errors.email}
          onChange={(event) => {
            setEmail(event.target.value);
            setErrors((current) => ({ ...current, email: undefined }));
            login.reset();
          }}
        />
        <FormField
          label="密码"
          type="password"
          name="password"
          autoComplete="current-password"
          placeholder="输入你的密码"
          value={password}
          error={errors.password}
          password
          onChange={(event) => {
            setPassword(event.target.value);
            setErrors((current) => ({ ...current, password: undefined }));
            login.reset();
          }}
        />
        <div className="form-actions form-actions--between">
          <Link className="quiet-link" to="/forgot-password">
            忘记密码？
          </Link>
        </div>
        <button className="primary-button" type="submit" disabled={login.isPending}>
          <span>{login.isPending ? "正在登录" : "登录"}</span>
          <ArrowRight size={18} aria-hidden="true" />
        </button>
      </form>
    </AuthLayout>
  );
}
