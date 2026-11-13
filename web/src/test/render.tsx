import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { App } from "@/app/App";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { createQueryClient } from "@/app/queryClient";
import { LocationProbe } from "@/test/LocationProbe";

export function createTestQueryClient(): QueryClient {
  return createQueryClient({
    queries: { retry: false, gcTime: Infinity },
    mutations: { retry: false },
  });
}

export function renderApp(initialPath = "/login") {
  const queryClient = createTestQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialPath]}>
          <AuthProvider>
            <App />
            <LocationProbe />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

export function renderWithProviders(element: ReactElement) {
  const queryClient = createTestQueryClient();
  return {
    queryClient,
    ...render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthProvider>
            {element}
            <LocationProbe />
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}
