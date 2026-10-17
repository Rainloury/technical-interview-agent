import { useEffect } from "react";

import { ApiError } from "../api/client";
import { useAuth } from "../auth/context";

export function useSessionGuard(error: unknown): void {
  const { clear } = useAuth();

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) {
      clear();
    }
  }, [clear, error]);
}
