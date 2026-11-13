import type { QueryClient } from "@tanstack/react-query";

import { queryKeys } from "@/shared/api/queryKeys";

export function clearSession(queryClient: QueryClient): void {
  queryClient.setQueryData(queryKeys.session, null);
  queryClient.removeQueries({ queryKey: queryKeys.dashboard });
  queryClient.removeQueries({ queryKey: ["history"] });
}
