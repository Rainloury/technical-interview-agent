import { createContext, useContext } from "react";

import type { Session } from "../api/types";

export interface AuthContextValue {
  session: Session | null;
  isAuthenticated: boolean;
  isInitialLoading: boolean;
  refresh: () => Promise<Session | null>;
  clear: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return context;
}
