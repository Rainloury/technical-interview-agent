import { Navigate, Outlet, useLocation } from "react-router-dom";

import { FullPageState } from "@/shared/ui/FullPageState";
import { useAuth } from "@/features/auth/context";

export function ProtectedRoute() {
  const { isAuthenticated, isInitialLoading } = useAuth();
  const location = useLocation();

  if (isInitialLoading) {
    return <FullPageState kind="loading" title="正在恢复会话" />;
  }
  if (!isAuthenticated) {
    const returnTo = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?returnTo=${encodeURIComponent(returnTo)}`} replace />;
  }
  return <Outlet />;
}
