import { act, cleanup, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFetch, json } from "../../test-utils";
import { DashboardEmbed } from "./DashboardEmbed";
import type { Dashboard } from "./types";

/**
 * 실물 @superset-ui/embedded-sdk 0.4.0과 가짜 타이머로 확인하는 시험(모의 SDK가 아님).
 * 프로브(docs/research/fu1e-probes.md 5-3)의 동작을 컴포넌트가 지키는지 본다:
 * 갱신은 만료 5초 전(약 295초)에 fetchGuestToken을 다시 부르고, 정리하지 않으면 타이머가 남는다.
 * iframe의 load는 jsdom이 보내지 않으므로 테스트가 직접 일으킨다.
 */
const BASE = "/bi-wizard";
const DASH: Dashboard = { id: 5, name: "매출 현황", embedded_uuid: "11111111-1111-4111-8111-111111111111", is_active: true };

const b64url = (value: object) => btoa(JSON.stringify(value)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
/** 시험용 가짜 입장권: exp가 현재(가짜 시계)로부터 300초인 JWT 모양 문자열. 서명은 의미 없다. */
const fakeToken = () => `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url({ exp: Math.floor(Date.now() / 1000) + 300 })}.sig`;

beforeEach(() => {
  // jsdom에는 iframe.sandbox(DOMTokenList)가 없어 SDK가 쓰는 add()만 제공한다. 브라우저 동작에는 영향이 없는 시험용 보충이다.
  if (!("sandbox" in HTMLIFrameElement.prototype)) {
    Object.defineProperty(HTMLIFrameElement.prototype, "sandbox", { configurable: true, get: () => ({ add: () => undefined }) });
  }
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date"] });
});

afterEach(() => {
  cleanup();
  Reflect.deleteProperty(HTMLIFrameElement.prototype, "sandbox");
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  delete window.__APP_CONFIG__;
});

const settle = (ms = 0) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

/** 가장 최근 iframe의 load를 일으켜 SDK의 핸드셰이크와 첫 입장권 전달을 끝낸다. */
async function loadIframe() {
  const iframe = document.querySelector("iframe");
  if (!iframe) throw new Error("iframe 없음");
  // jsdom의 postMessage는 전송 목록(MessagePort)을 지원하지 않을 수 있어 시험에서만 대신한다.
  const win = iframe.contentWindow!;
  vi.spyOn(win, "postMessage").mockImplementation(() => undefined);
  await act(async () => {
    iframe.dispatchEvent(new Event("load"));
  });
  await settle(0);
}

describe("실물 SDK", () => {
  it("5분을 넘겨 열어 두면 약 295초마다 입장권을 다시 받는다(갱신 유지)", async () => {
    const { calls } = installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: fakeToken(), expires_in: 300 }) }, BASE);
    render(<DashboardEmbed dashboard={DASH} />);
    await settle(0);
    expect(calls).toHaveLength(1);
    await loadIframe();
    expect(screen.queryByText(/불러오는 중/)).toBeNull();

    await settle(290_000);
    expect(calls).toHaveLength(1);
    await settle(10_000); // 약 300초: 첫 갱신(만료 5초 전 = 295초)
    expect(calls).toHaveLength(2);
    await settle(295_000); // 약 595초: 두 번째 갱신
    expect(calls).toHaveLength(3);
    await settle(295_000); // 약 890초 = 5분을 훌쩍 넘겨도 계속
    expect(calls).toHaveLength(4);
    expect(screen.queryByTestId("embed-refresh-problem")).toBeNull();
  });

  it("언마운트하면 갱신 타이머가 남지 않고 더 이상 입장권을 요청하지 않는다", async () => {
    const { calls } = installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: fakeToken(), expires_in: 300 }) }, BASE);
    const view = render(<DashboardEmbed dashboard={DASH} />);
    await settle(0);
    await loadIframe();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
    await settle(600_000);
    expect(calls).toHaveLength(1);
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("iframe 로딩 전에(Promise가 풀리기 전에) 언마운트해도, 풀린 뒤 정리되어 타이머가 영구히 남지 않는다", async () => {
    const { calls } = installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: fakeToken(), expires_in: 300 }) }, BASE);
    const view = render(<DashboardEmbed dashboard={DASH} />);
    await settle(0);
    const iframe = document.querySelector("iframe");
    expect(iframe).not.toBeNull();
    view.unmount();
    // 정리된 컴포넌트의 iframe load가 늦게 도착한다(SDK는 이제야 풀린다). 이때 늦은 unmount()가 타이머를 정리해야 한다.
    const win = iframe!.contentWindow!;
    vi.spyOn(win, "postMessage").mockImplementation(() => undefined);
    await act(async () => {
      iframe!.dispatchEvent(new Event("load"));
    });
    await settle(0);
    expect(vi.getTimerCount()).toBe(0);
    await settle(120_000);
    expect(calls).toHaveLength(1);
  });

  it("엄격 모드에서도 입장권은 한 번만 요청하고, 정리하면 타이머가 남지 않는다", async () => {
    const { calls } = installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: fakeToken(), expires_in: 300 }) }, BASE);
    const view = render(
      <StrictMode>
        <DashboardEmbed dashboard={DASH} />
      </StrictMode>,
    );
    await settle(0);
    expect(calls).toHaveLength(1);
    expect(document.querySelectorAll("iframe")).toHaveLength(1);
    await loadIframe();
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("첫 입장권 요청이 실패하면 SDK가 iframe을 지우고 거부하며, 화면은 다시 시도 버튼을 보인다(재시도 없음)", async () => {
    const { calls } = installFetch(
      { "POST /dashboards/5/guest-token": () => json(503, { error: { code: "SUPERSET_UNAVAILABLE", message: "x", details: null, request_id: "r1" } }) },
      BASE,
    );
    render(<DashboardEmbed dashboard={DASH} />);
    await settle(0);
    expect(screen.getByTestId("embed-failed")).toBeTruthy();
    expect(document.querySelector("iframe")).toBeNull();
    await settle(60_000);
    expect(calls).toHaveLength(1);
  });

  it("갱신 요청이 계속 실패하면 SDK가 10초마다 다시 부르고, 화면은 배너로 알린다", async () => {
    let fail = false;
    const { calls } = installFetch(
      {
        "POST /dashboards/5/guest-token": () =>
          fail ? json(503, { error: { code: "SUPERSET_UNAVAILABLE", message: "x", details: null, request_id: "r1" } }) : json(200, { token: fakeToken(), expires_in: 300 }),
      },
      BASE,
    );
    render(<DashboardEmbed dashboard={DASH} />);
    await settle(0);
    await loadIframe();
    fail = true;
    await settle(300_000);
    expect(calls).toHaveLength(2);
    expect(screen.getByTestId("embed-refresh-problem").textContent).toContain("대시보드 서비스에 연결할 수 없습니다");
    await settle(10_000);
    expect(calls).toHaveLength(3);
    fail = false;
    await settle(10_000);
    expect(calls).toHaveLength(4);
    expect(screen.queryByTestId("embed-refresh-problem")).toBeNull();
  });
});
