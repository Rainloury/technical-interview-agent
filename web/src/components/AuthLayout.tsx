import { ArrowLeft, ExternalLink } from "lucide-react";
import type { PropsWithChildren, ReactNode } from "react";
import { Link } from "react-router-dom";

import { GitHubMark } from "./GitHubMark";

interface AuthLayoutProps extends PropsWithChildren {
  title: string;
  subtitle: string;
  footer?: ReactNode;
}

const githubUrl = "https://github.com/Rainloury/technical-interview-agent";

function GitHubLink({ compact = false }: { compact?: boolean }) {
  return (
    <a
      className={compact ? "auth-github auth-github--compact" : "auth-github"}
      href={githubUrl}
      target="_blank"
      rel="noreferrer"
    >
      <GitHubMark />
      <span>开源仓库</span>
      {!compact && <ExternalLink size={14} aria-hidden="true" />}
    </a>
  );
}

export function AuthLayout({ title, subtitle, footer, children }: AuthLayoutProps) {
  return (
    <main className="auth-page">
      <section className="auth-intro" aria-label="产品说明">
        <div className="auth-intro-nav">
          <Link className="auth-back" to="/login">
            <ArrowLeft size={17} aria-hidden="true" />
            <span>技术面试工作台</span>
          </Link>
          <GitHubLink />
        </div>
        <div className="auth-intro-copy">
          <p className="eyebrow">TECHNICAL INTERVIEW AGENT / v1</p>
          <h1>把每次练习，留成可复盘的记录。</h1>
          <p>
            简历分析、检索问答和模拟面试都进入同一条工作流。登录后从工作台继续。
          </p>
          <div className="auth-terminal" aria-hidden="true">
            <p>
              <span>$</span> interview-agent workspace --session=active
            </p>
            <p>
              <span>→</span> retrieve / answer / practice / review
            </p>
            <p>
              <span>✓</span> ready
            </p>
          </div>
        </div>
        <ol className="auth-steps" aria-label="使用流程">
          <li>
            <span>01</span>
            <div>
              <strong>建立会话</strong>
              <p>使用邮箱登录，会话凭据由安全 Cookie 管理。</p>
            </div>
          </li>
          <li>
            <span>02</span>
            <div>
              <strong>选择训练路径</strong>
              <p>从简历、问答或模拟面试进入具体任务。</p>
            </div>
          </li>
          <li>
            <span>03</span>
            <div>
              <strong>回到证据</strong>
              <p>在历史和复习中心检查结果与薄弱点。</p>
            </div>
          </li>
        </ol>
      </section>

      <section className="auth-panel">
        <div className="auth-form-wrap">
          <div className="auth-panel-meta">
            <span>SECURE SESSION</span>
            <div className="auth-panel-meta-end">
              <span>INTERVIEW_AGENT / AUTH</span>
              <GitHubLink compact />
            </div>
          </div>
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
