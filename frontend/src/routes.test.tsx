import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { createTestRouter, routerBasename } from "./routes";
import { ADMIN_ME, HEALTH_HANDLERS, installFetch, json } from "./test-utils";

beforeEach(() => {
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const DEEP_LINKS: Array<[string, string]> = [
  ["/", "screen-S1"],
  ["/access-denied", "screen-S1"],
  ["/datasets", "screen-S2"],
  ["/datasets/new", "screen-S3"],
  ["/datasets/42", "screen-S4"],
  ["/checks", "screen-S5"],
  ["/admin/permissions", "screen-S6"],
  ["/dashboards", "screen-S7"],
  ["/admin/dashboards", "screen-S8"],
  ["/admin/status", "screen-S9"],
];

describe("routerBasename", () => {
  it("루트 배포는 /, 하위 경로는 그대로", () => {
    expect(routerBasename("")).toBe("/");
    expect(routerBasename("/bi-wizard")).toBe("/bi-wizard");
  });
});

// 딥링크는 브라우저 주소 기준이다. APP_PROXY_STRIP_PREFIX(true/false)는 API 전달에만 영향을 주고
// 브라우저 주소(접두 포함)는 같으므로, 프런트 입장에서는 basePath가 있는/없는 두 설정을 시험한다.
describe.each([
  ["하위 경로(/bi-wizard)", "/bi-wizard"],
  ["루트 배포", ""],
])("딥링크: %s", (_name, basePath) => {
  beforeEach(() => {
    window.__APP_CONFIG__ = { basePath, supersetRoot: "" };
    installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), "GET /users": () => json(200, { items: [], total: 0, limit: 50, offset: 0 }), "GET /teams": () => json(200, { items: [], total: 0, limit: 200, offset: 0 }) }, basePath);
  });

  it.each(DEEP_LINKS)("%s 직접 진입", async (path, testId) => {
    render(<App router={createTestRouter(basePath, `${basePath}${path === "/" ? "/" : path}`)} />);
    expect(await screen.findByTestId(testId)).toBeTruthy();
  });

  it("상단 Navigation이 보이고 메뉴 링크가 basename을 포함한다", async () => {
    render(<App router={createTestRouter(basePath, `${basePath}/datasets/42`)} />);
    const nav = await screen.findByRole("navigation", { name: "주 메뉴" });
    expect(nav).toBeTruthy();
    const link = screen.getByRole("link", { name: "데이터셋" });
    expect(link.getAttribute("href")).toBe(`${basePath}/datasets`);
    expect(screen.getByRole("link", { name: "권한 관리" }).getAttribute("href")).toBe(
      `${basePath}/admin/permissions`,
    );
  });

  it("알 수 없는 경로는 셸 안에서 찾을 수 없음 화면", async () => {
    render(<App router={createTestRouter(basePath, `${basePath}/no/such/page`)} />);
    expect(await screen.findByTestId("screen-not-found")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "주 메뉴" })).toBeTruthy();
  });
});

it("하위 경로 밖 주소는 셸 화면으로 연결되지 않는다", () => {
  window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "" };
  installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME) }, "/bi-wizard");
  const router = createTestRouter("/bi-wizard", "/datasets");
  expect(router.state.errors).not.toBeNull();
  render(<App router={router} />);
  expect(screen.queryByTestId("screen-S2")).toBeNull();
});
