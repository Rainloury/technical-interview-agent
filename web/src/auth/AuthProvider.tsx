import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, type PropsWithChildren } from "react";

import { api, ApiError } from "../api/client";
import { queryKeys } from "../api/queryKeys";
import type { Session } from "../api/types";
import { AuthContext, type AuthContextValue } from "./context";

export function AuthProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const sessionQuery = useQuery({
    queryKey: queryKeys.session,
    queryFn: async (): Promise<Session | null> => {
      try {
        return await api.session();
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) {
          return null;
        }
        throw error;
      }
    },
    retry: (failureCount, error) => {
      if (error instanceof ApiError && error.status === 401) {
        return false;
      }
      return failureCount < 1;
    },
    staleTime: 30_000,
  });

  const refresh = useCallback(async (): Promise<Session | null> => {
    const result = await queryClient.fetchQuery({
      queryKey: queryKeys.session,
      queryFn: async (): Promise<Session | null> => {
        try {
          return await api.session();
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            return null;
          }
          throw error;
        }
      },
      staleTime: 0,
    });
    return result;
  }, [queryClient]);

  const clear = useCallback(() => {
    queryClient.setQueryData(queryKeys.session, null);
    queryClient.removeQueries({ queryKey: queryKeys.dashboard });
    queryClient.removeQueries({ queryKey: ["history"] });
  }, [queryClient]);

  const value = useMemo<AuthContextValue>(
    () => ({
      session: sessionQuery.data ?? null,
      isAuthenticated:
        sessionQuery.data !== undefined && sessionQuery.data !== null,
      isInitialLoading: sessionQuery.isPending && sessionQuery.data === undefined,
      refresh,
      clear,
    }),
    [clear, refresh, sessionQuery.data, sessionQuery.isPending],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
