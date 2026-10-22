import {
  Command,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Library,
  Plus,
  Target,
  Search,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { useAuth } from "../auth/context";

const navigation = [
  { to: "/workspace", label: "工作台", code: "01", icon: LayoutDashboard },
  { to: "/qa", label: "技术问答", code: "02", icon: Search },
  { to: "/documents", label: "内部资料", code: "03", icon: Library },
  { to: "/interviews", label: "模拟面试", code: "04", icon: MessageSquareText },
  { to: "/reviews", label: "复习中心", code: "05", icon: Target },
  { to: "/history", label: "历史记录", code: "06", icon: History },
];

export function AppShell() {
  const { session, clear } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [mobileOpen, setMobileOpen] = useState(false);
  const logout = useMutation({
    mutationFn: api.logout,
    onSettled: () => {
      clear();
      queryClient.clear();
      navigate("/login", { replace: true });
    },
  });

  const displayName = session?.user.display_name?.trim() || "面试者";
  const initial = displayName.slice(0, 1).toUpperCase();

  const handleLogout = () => {
    setMobileOpen(false);
    logout.mutate();
  };

  return (
    <div className="app-shell">
      <header className="mobile-header">
        <NavLink className="brand brand--mobile" to="/workspace">
          <span className="brand-mark" aria-hidden="true">
            T/
          </span>
          <span>技术面试工作台</span>
        </NavLink>
        <button
          type="button"
          className="icon-button mobile-menu-button"
          aria-label={mobileOpen ? "关闭导航" : "打开导航"}
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((open) => !open)}
        >
          {mobileOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </header>

      <aside className={`sidebar ${mobileOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar-body">
          <div className="sidebar-topline">
            <NavLink
              className="brand"
              to="/workspace"
              onClick={() => setMobileOpen(false)}
            >
              <span className="brand-mark" aria-hidden="true">
                T/
              </span>
              <span className="brand-copy">
                技术面试工作台
                <small>INTERVIEW AGENT · TERMINAL</small>
              </span>
            </NavLink>
            <button
              type="button"
              className="icon-button sidebar-close"
              aria-label="关闭导航"
              onClick={() => setMobileOpen(false)}
            >
              <X size={20} />
            </button>
          </div>

          <div className="sidebar-status" aria-label="工作区状态">
            <span className="status-light" aria-hidden="true" />
            <span>WORKSPACE ONLINE</span>
            <Command size={14} aria-hidden="true" />
          </div>

          <nav className="primary-nav" aria-label="主导航">
            <p className="nav-label">工作区 / 索引</p>
            {navigation.map(({ to, label, code, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "nav-item--active" : ""}`
                }
                onClick={() => setMobileOpen(false)}
              >
                <span className="nav-code" data-index={code} aria-hidden="true" />
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="next-work">
            <p className="nav-label">快捷入口</p>
            <NavLink
              className={({ isActive }) =>
                `nav-item ${isActive ? "nav-item--active" : ""}`
              }
              to="/resumes/new"
              onClick={() => setMobileOpen(false)}
            >
              <span className="nav-code" data-index="++" aria-hidden="true" />
              <Plus size={18} strokeWidth={1.8} aria-hidden="true" />
              <span>上传简历</span>
            </NavLink>
          </div>
        </div>

        <div className="account-block">
          <div className="account-summary">
            <span className="avatar" aria-hidden="true">
              {initial}
            </span>
            <div>
              <strong>{displayName}</strong>
              <span>已登录 · session</span>
            </div>
          </div>
          <button
            type="button"
            className="logout-button"
            onClick={handleLogout}
            disabled={logout.isPending}
          >
            <LogOut size={17} aria-hidden="true" />
            <span>{logout.isPending ? "正在退出" : "退出登录"}</span>
          </button>
        </div>
      </aside>

      {mobileOpen && (
        <button
          type="button"
          className="nav-scrim"
          aria-label="关闭导航"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <main className="main-content">
        <div className="workspace-rail" aria-hidden="true">
          <span>TECHNICAL INTERVIEW AGENT</span>
          <span>BUILD · PRACTICE · REVIEW</span>
        </div>
        <Outlet />
      </main>
    </div>
  );
}
