import { ArrowLeft } from "lucide-react";
import type { PropsWithChildren, ReactNode } from "react";
import { Link } from "react-router-dom";

interface AuthLayoutProps extends PropsWithChildren {
  title: string;
  subtitle: string;
  footer?: ReactNode;
}

export function AuthLayout({ title, subtitle, footer, children }: AuthLayoutProps) {
  return (
    <main className="auth-page">
      <section className="auth-intro" aria-label="产品说明">
        <Link className="auth-back" to="/login">
          <ArrowLeft size={17} aria-hidden="true" />
          <span>技术面试工作台</span>
        </Link>
        <div className="auth-intro-copy">
          <p className="eyebrow">TECHNICAL INTERVIEW AGENT</p>
          <h1>把每一次准备，变成可追踪的进展。</h1>
          <p>
            从工作台进入你的面试任务，查看历史记录，并持续沉淀技术面试准备过程。
          </p>
        </div>
        <ol className="auth-steps" aria-label="使用流程">
          <li>
            <span>01</span>
            <div>
              <strong>进入账号</strong>
              <p>注册或登录，只保留必要的会话信息。</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>查看工作台</strong>
              <p>集中查看最近任务与模拟面试记录。</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>持续回看</strong>
              <p>按类型分页浏览自己的历史记录。</p>
            </div>
          </li>
        </ol>
      </section>

      <section className="auth-panel">
        <div className="auth-form-wrap">
          <p className="eyebrow mobile-only">TECHNICAL INTERVIEW AGENT</p>
          <h2>{title}</h2>
          <p className="auth-subtitle">{subtitle}</p>
          {children}
          {footer && <div className="auth-footer">{footer}</div>}
        </div>
      </section>
    </main>
  );
}
