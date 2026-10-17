import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

beforeAll(() => server.listen());
afterEach(() => {
  cleanup();
  server.resetHandlers();
  document.cookie = "interview_csrf=; Max-Age=0; path=/";
});
afterAll(() => server.close());
