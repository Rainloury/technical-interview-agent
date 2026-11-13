import { Navigate, Outlet, useSearchParams } from "react-router-dom";

import { FullPageState } from "@/shared/ui/FullPageState";
import { safeReturnTo } from "@/shared/lib/navigation";
import { useAuth } from "@/features/auth/context";

export function PublicOnlyRoute() {
  const { isAuthenticated, isInitialLoading } = useAuth();
  const [searchParams] = useSearchParams();

  if (isInitialLoading) {
    return <FullPageState kind="loading" title="正在检查会话" />;
  }
  if (isAuthenticated) {
    return <Navigate to={safeReturnTo(searchParams.get("returnTo"))} replace />;
  }
  return <Outlet />;
}
