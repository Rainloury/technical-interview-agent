import {
  MutationCache,
  QueryCache,
  QueryClient,
  type QueryClientConfig,
} from "@tanstack/react-query";

import { ApiError } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/queryKeys";
import { clearSession } from "@/shared/lib/clearSession";

function handleUnauthorized(error: unknown, queryClient: QueryClient): void {
  if (!(error instanceof ApiError) || error.status !== 401) {
    return;
  }
  // 未登录时的 401（例如登录凭据错误）不代表会话失效，不清理业务缓存。
  if (queryClient.getQueryData(queryKeys.session) == null) {
    return;
  }
  clearSession(queryClient);
}

export function createQueryClient(
  defaultOptions: QueryClientConfig["defaultOptions"] = {},
): QueryClient {
  const onError = (error: unknown): void => {
    handleUnauthorized(error, client);
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: {
      queries: { retry: 1, refetchOnWindowFocus: false },
      mutations: { retry: false },
      ...defaultOptions,
    },
  });
  return client;
}
