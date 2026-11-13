import { QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { initAnalytics } from "@/app/analytics";
import { App } from "@/app/App";
import { AuthProvider } from "@/features/auth/AuthProvider";
import { createQueryClient } from "@/app/queryClient";
import "@/app/styles.css";

initAnalytics();

const queryClient = createQueryClient();

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element is missing");
}

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
