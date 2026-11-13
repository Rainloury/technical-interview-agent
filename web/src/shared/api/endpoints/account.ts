import { request } from "@/shared/api/http";
import type { DataDeletionAccepted, DataDeletionStatus } from "@/shared/api/types";

export const accountEndpoints = {
  deleteMyData: (idempotencyKey: string) =>
    request<DataDeletionAccepted>("/api/v1/me/data", {
      method: "DELETE",
      headers: { "Idempotency-Key": idempotencyKey },
    }),
  latestDataDeletion: () =>
    request<DataDeletionStatus | null>("/api/v1/me/data-deletion"),
};
