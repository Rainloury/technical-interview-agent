import { authEndpoints } from "@/shared/api/endpoints/auth";
import { workspaceEndpoints } from "@/shared/api/endpoints/workspace";
import { resumesEndpoints } from "@/shared/api/endpoints/resumes";
import { qaEndpoints } from "@/shared/api/endpoints/qa";
import { interviewsEndpoints } from "@/shared/api/endpoints/interviews";
import { reviewsEndpoints } from "@/shared/api/endpoints/reviews";
import { accountEndpoints } from "@/shared/api/endpoints/account";
import { documentsEndpoints } from "@/shared/api/endpoints/documents";

export { ApiError, REQUEST_TIMEOUT_MS } from "@/shared/api/http";
export { parseSseStream } from "@/shared/api/sse";
export type { ParsedSseEvent, QaStreamOptions } from "@/shared/api/sse";

export const api = {
  ...authEndpoints,
  ...workspaceEndpoints,
  ...resumesEndpoints,
  ...qaEndpoints,
  ...interviewsEndpoints,
  ...reviewsEndpoints,
  ...accountEndpoints,
  ...documentsEndpoints,
};
