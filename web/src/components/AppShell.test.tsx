import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { authenticatedSessionHandler, server } from "../test/server";
import { renderApp } from "../test/render";

describe("AppShell", () => {
  it("uses the interview favicon as the in-product brand mark", async () => {
    server.use(
      authenticatedSessionHandler(),
      http.get("*/api/v1/dashboard", () =>
        HttpResponse.json({
          greeting_name: "林然",
          summary: {
            resume_tasks: 1,
            qa_requests: 2,
            interviews: 1,
            reviews_due: 0,
          },
          recent: [],
        }),
      ),
    );

    renderApp("/workspace");

    const brandMarks = await screen.findAllByRole("presentation", {
      hidden: true,
    });
    expect(
      brandMarks.some(
        (mark) =>
          mark.tagName === "IMG" &&
          mark.getAttribute("src") === "/favicon.svg",
      ),
    ).toBe(true);
  });
});
