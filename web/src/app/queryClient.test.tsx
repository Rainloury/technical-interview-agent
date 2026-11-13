import {
  QueryClientProvider,
  useMutation,
  type QueryClient,
} from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { createElement, type PropsWithChildren } from "react";

import { ApiError } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/queryKeys";
import { createQueryClient } from "@/app/queryClient";
import { demoDashboard, demoSession } from "@/test/server";

function wrapperFor(queryClient: QueryClient) {
  return ({ children }: PropsWithChildren) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function useUnauthorizedMutation() {
  return useMutation({
    mutationFn: async () => {
      throw new ApiError("请先登录", {
        status: 401,
        code: "authentication_required",
      });
    },
  });
}

async function runFailingMutation(queryClient: QueryClient): Promise<void> {
  const { result } = renderHook(useUnauthorizedMutation, {
    wrapper: wrapperFor(queryClient),
  });
  await act(async () => {
    await result.current.mutateAsync().catch(() => undefined);
  });
}

describe("query client", () => {
  it("clears the cached session when a mutation fails with 401", async () => {
    const queryClient = createQueryClient({ mutations: { retry: false } });
    queryClient.setQueryData(queryKeys.session, demoSession);
    queryClient.setQueryData(queryKeys.dashboard, demoDashboard);

    await runFailingMutation(queryClient);

    expect(queryClient.getQueryData(queryKeys.session)).toBeNull();
    expect(queryClient.getQueryData(queryKeys.dashboard)).toBeUndefined();
  });

  it("keeps business caches for a 401 returned while signed out", async () => {
    const queryClient = createQueryClient({ mutations: { retry: false } });
    queryClient.setQueryData(queryKeys.session, null);
    queryClient.setQueryData(queryKeys.dashboard, demoDashboard);

    await runFailingMutation(queryClient);

    expect(queryClient.getQueryData(queryKeys.dashboard)).toEqual(demoDashboard);
  });
});
