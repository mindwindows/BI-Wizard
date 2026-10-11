import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

it("하위 경로 아래 API로 Health를 호출하고 결과를 보여 준다", async () => {
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve(new Response("{}", { status: url.endsWith("/health/db") ? 503 : 200 })),
  );
  vi.stubGlobal("fetch", fetchMock);

  render(<App />);

  expect(await screen.findByText("정상 (HTTP 200)")).toBeTruthy();
  expect(await screen.findByText("오류 (HTTP 503)")).toBeTruthy();
  const urls = fetchMock.mock.calls.map((call) => call[0]);
  expect(urls).toContain("/bi-wizard/api/health");
  expect(urls).toContain("/bi-wizard/api/health/db");
});
