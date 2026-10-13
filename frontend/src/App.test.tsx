import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import App from "./App";
import { createTestRouter } from "./routes";
import { ADMIN_ME, HEALTH_HANDLERS, installFetch, json } from "./test-utils";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

it("하위 경로 아래 API로 Health를 호출하고 결과를 보여 준다", async () => {
  const { fetchMock } = installFetch({
    ...HEALTH_HANDLERS,
    "GET /me": () => json(200, ADMIN_ME),
    "GET /health/db": () => json(503, {}),
  });

  render(<App router={createTestRouter("/bi-wizard", "/bi-wizard/")} />);

  expect(await screen.findByText("정상 (HTTP 200)")).toBeTruthy();
  expect(await screen.findByText("오류 (HTTP 503)")).toBeTruthy();
  const urls = fetchMock.mock.calls.map((call) => call[0]);
  expect(urls).toContain("/bi-wizard/api/health");
  expect(urls).toContain("/bi-wizard/api/health/db");
  expect(urls).toContain("/bi-wizard/api/me");
});
