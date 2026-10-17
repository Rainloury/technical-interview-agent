import { ArrowLeft } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFoundPage() {
  return (
    <main className="not-found">
      <p className="eyebrow">404 / NOT FOUND</p>
      <h1>没有找到这个页面</h1>
      <p>地址可能已变更，返回工作台继续。</p>
      <Link className="primary-button primary-button--link" to="/workspace">
        <ArrowLeft size={18} aria-hidden="true" />
        <span>返回工作台</span>
      </Link>
    </main>
  );
}
