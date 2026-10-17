import {
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareText,
  Plus,
  X,
} from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../api/client";
import { useAuth } from "../auth/context";

const navigation = [
  { to: "/workspace", label: "工作台", icon: LayoutDashboard },
  { to: "/history", label: "历史记录", icon: History },
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
            T
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
        <div>
          <NavLink
            className="brand"
            to="/workspace"
            onClick={() => setMobileOpen(false)}
          >
            <span className="brand-mark" aria-hidden="true">
              T
            </span>
            <span>
              技术面试
              <small>AGENT WORKSPACE</small>
            </span>
          </NavLink>

          <nav className="primary-nav" aria-label="主导航">
            <p className="nav-label">工作区</p>
            {navigation.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `nav-item ${isActive ? "nav-item--active" : ""}`
                }
                onClick={() => setMobileOpen(false)}
              >
                <Icon size={18} strokeWidth={1.8} aria-hidden="true" />
                <span>{label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="next-work">
            <p className="nav-label">简历</p>
            <NavLink
              className={({ isActive }) =>
                `nav-item ${isActive ? "nav-item--active" : ""}`
              }
              to="/resumes/new"
              onClick={() => setMobileOpen(false)}
            >
              <Plus size={18} strokeWidth={1.8} aria-hidden="true" />
              <span>上传简历</span>
            </NavLink>
            <p className="nav-label next-work-label">即将开放</p>
            <div className="next-work-row">
              <MessageSquareText size={17} aria-hidden="true" />
              <span>模拟面试</span>
              <span className="soon">待开放</span>
            </div>
          </div>
        </div>

        <div className="account-block">
          <div className="account-summary">
            <span className="avatar" aria-hidden="true">
              {initial}
            </span>
            <div>
              <strong>{displayName}</strong>
              <span>已登录</span>
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
        <Outlet />
      </main>
    </div>
  );
}
