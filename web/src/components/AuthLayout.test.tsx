import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AuthLayout } from "./AuthLayout";

describe("AuthLayout", () => {
  it("links both responsive layouts to the public GitHub repository", () => {
    render(
      <MemoryRouter>
        <AuthLayout title="登录工作台" subtitle="继续准备技术面试。">
          <form />
        </AuthLayout>
      </MemoryRouter>,
    );

    const links = screen.getAllByRole("link", { name: "开源仓库" });

    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link.querySelector('[data-github-mark="true"]')).not.toBeNull();
      expect(link).toHaveAttribute(
        "href",
        "https://github.com/Rainloury/technical-interview-agent",
      );
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noreferrer");
    }
  });
});
