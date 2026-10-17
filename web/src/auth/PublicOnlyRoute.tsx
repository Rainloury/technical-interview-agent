import { Navigate, Outlet, useSearchParams } from "react-router-dom";

import { FullPageState } from "../components/FullPageState";
import { safeReturnTo } from "../utils/navigation";
import { useAuth } from "./context";

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
