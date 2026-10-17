import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import { App } from "../App";
import { AuthProvider } from "../auth/AuthProvider";
import { LocationProbe } from "./LocationProbe";

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
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
