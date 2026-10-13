import type { EmbeddedDashboard } from "@superset-ui/embedded-sdk";
import { embedDashboard } from "@superset-ui/embedded-sdk";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiError, installFetch, json, type Handler } from "../../test-utils";
import { DashboardEmbed, EMPTY_CHECK_MS, RECHECK_MS, looksEmpty } from "./DashboardEmbed";
import type { Dashboard } from "./types";

vi.mock("@superset-ui/embedded-sdk", () => ({ embedDashboard: vi.fn() }));

/**
 * 임베딩 컴포넌트 생애주기 시험. SDK는 모의다(실물 SDK의 정리·갱신 동작은 embed.sdk.test.tsx).
 * 모의 SDK는 실물과 같이 embedDashboard 호출 즉시 fetchGuestToken을 부르고, 첫 호출이 실패하면 거부한다.
 */
const BASE = "/bi-wizard";
const TOKEN = "hdr.PAYLOAD-TOKEN-VALUE.sig";
const UUID_A = "11111111-1111-4111-8111-111111111111";
const UUID_B = "22222222-2222-4222-8222-222222222222";

const DASH_A: Dashboard = { id: 5, name: "매출 현황", embedded_uuid: UUID_A, is_active: true };
const DASH_B: Dashboard = { id: 6, name: "비용 현황", embedded_uuid: UUID_B, is_active: true };

interface Instance {
  params: Parameters<typeof embedDashboard>[0];
  unmount: ReturnType<typeof vi.fn>;
  iframe: HTMLIFrameElement;
  /** held 모드에서 embedDashboard를 푼다. */
  finish: () => void;
  token?: string;
}

const instances: Instance[] = [];
const embedMock = vi.mocked(embedDashboard);

/** hold=true: 첫 입장권은 받지만 iframe 로드(Promise 풀림)는 테스트가 finish()를 부를 때까지 보류한다. */
function installSdk(hold = false) {
  instances.length = 0;
  embedMock.mockImplementation((params) => {
    const iframe = document.createElement("iframe");
    params.mountPoint.replaceChildren(iframe);
    const unmount = vi.fn(() => params.mountPoint.replaceChildren());
    const instance: Instance = { params, unmount, iframe, finish: () => undefined };
    instances.push(instance);
    return new Promise<EmbeddedDashboard>((resolve, reject) => {
      const handle = { unmount } as unknown as EmbeddedDashboard;
      let release: () => void = () => undefined;
      const gate = new Promise<void>((open) => {
        release = open;
        if (!hold) open();
      });
      instance.finish = release;
      params.fetchGuestToken().then(
        async (token) => {
          instance.token = token;
          await gate;
          resolve(handle);
        },
        (error: unknown) => {
          params.mountPoint.replaceChildren();
          reject(error);
        },
      );
    });
  });
}

const tokenOk: Handler = () => json(200, { token: TOKEN, expires_in: 300 }, { "Cache-Control": "no-store" });

function setup(handlers: Record<string, Handler> = {}, hold = false) {
  installSdk(hold);
  return installFetch({ "POST /dashboards/5/guest-token": tokenOk, "POST /dashboards/6/guest-token": tokenOk, ...handlers }, BASE);
}

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
  embedMock.mockReset();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const flush = () => act(async () => undefined);

describe("마운트", () => {
  it("embedDashboard를 uuid, 하위 경로 포함 supersetDomain, 마운트 칸, 입장권 콜백으로 호출한다", async () => {
    const { calls } = setup();
    render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(embedMock).toHaveBeenCalledTimes(1));
    const params = instances[0].params;
    expect(params.id).toBe(UUID_A);
    expect(params.supersetDomain).toBe(`${window.location.origin}${BASE}/superset`);
    expect(params.mountPoint).toBeInstanceOf(HTMLElement);
    expect(screen.getByTestId("dashboard-embed").contains(params.mountPoint)).toBe(true);
    expect(typeof params.fetchGuestToken).toBe("function");
    expect(params.debug ?? false).toBe(false);
    // 입장권은 포털 대시보드 번호(5)로만 요청한다. uuid·본문을 보내지 않는다.
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0]).toMatchObject({ method: "POST", path: "/dashboards/5/guest-token", body: undefined });
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    expect(screen.queryByTestId("embed-failed")).toBeNull();
  });

  it("supersetRoot에 따라 supersetDomain이 달라진다(루트 포털 + 하위 경로 Superset)", async () => {
    window.__APP_CONFIG__ = { basePath: "", supersetRoot: "/superset" };
    setup();
    installFetch({ "POST /dashboards/5/guest-token": tokenOk }, "");
    render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(embedMock).toHaveBeenCalledTimes(1));
    expect(instances[0].params.supersetDomain).toBe(`${window.location.origin}/superset`);
  });

  it("fetchGuestToken이 돌려준 값은 입장권 문자열이고, 부를 때마다 새로 요청한다(갱신)", async () => {
    let n = 0;
    const { calls } = setup({ "POST /dashboards/5/guest-token": () => json(200, { token: `${TOKEN}-${++n}`, expires_in: 300 }) });
    render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(instances[0]?.token).toBe(`${TOKEN}-1`));
    await expect(instances[0].params.fetchGuestToken()).resolves.toBe(`${TOKEN}-2`);
    await expect(instances[0].params.fetchGuestToken()).resolves.toBe(`${TOKEN}-3`);
    expect(calls).toHaveLength(3);
  });
});

describe("정리", () => {
  it("언마운트하면 풀린 핸들의 unmount()를 부르고 마운트 칸을 제거한다", async () => {
    setup();
    const view = render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    const mountPoint = instances[0].params.mountPoint;
    view.unmount();
    expect(instances[0].unmount).toHaveBeenCalledTimes(1);
    expect(mountPoint.isConnected).toBe(false);
  });

  it("Promise가 풀리기 전에 언마운트하면 풀린 뒤 늦게라도 unmount()를 부른다", async () => {
    const { calls } = setup({}, true);
    const view = render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(instances[0]?.token).toBe(TOKEN));
    view.unmount();
    expect(instances[0].unmount).not.toHaveBeenCalled();
    // 정리된 뒤에는 SDK가 다시 불러도(10초마다 재시도하는 SDK 동작) 발급 요청을 보내지 않는다.
    const before = calls.length;
    await expect(instances[0].params.fetchGuestToken()).rejects.toBeDefined();
    expect(calls).toHaveLength(before);
    await act(async () => {
      instances[0].finish();
    });
    await waitFor(() => expect(instances[0].unmount).toHaveBeenCalledTimes(1));
  });

  it("첫 입장권 요청 중 언마운트되어 첫 호출이 실패해도 화면 상태를 건드리지 않는다", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    setup({ "POST /dashboards/5/guest-token": async () => (await gate, apiError(503, "SUPERSET_UNAVAILABLE")) });
    const errors = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const view = render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(embedMock).toHaveBeenCalledTimes(1));
    view.unmount();
    release();
    await flush();
    await flush();
    expect(errors).not.toHaveBeenCalled();
  });

  it("엄격 모드 이중 마운트: embedDashboard는 한 번만 호출되고 최종 한 인스턴스만 남아 정리된다", async () => {
    const { calls } = setup();
    const view = render(
      <StrictMode>
        <DashboardEmbed dashboard={DASH_A} />
      </StrictMode>,
    );
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    expect(embedMock).toHaveBeenCalledTimes(1);
    expect(calls).toHaveLength(1);
    expect(screen.getByTestId("dashboard-embed").querySelectorAll(".embed-mount")).toHaveLength(1);
    view.unmount();
    expect(instances[0].unmount).toHaveBeenCalledTimes(1);
  });

  it("엄격 모드에서 보류 중이던 이전 인스턴스가 있어도 마운트 칸을 공유하지 않아 새 iframe을 지우지 않는다", async () => {
    setup({}, true);
    render(
      <StrictMode>
        <DashboardEmbed dashboard={DASH_A} />
      </StrictMode>,
    );
    await waitFor(() => expect(instances[0]?.token).toBe(TOKEN));
    await act(async () => {
      instances[0].finish();
    });
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    expect(instances[0].params.mountPoint.querySelector("iframe")).toBe(instances[0].iframe);
    expect(instances[0].unmount).not.toHaveBeenCalled();
  });

  it("대시보드를 바꾸면 이전 인스턴스를 정리하고 새 uuid로 별도 마운트한다", async () => {
    setup();
    const view = render(<DashboardEmbed key={DASH_A.id} dashboard={DASH_A} />);
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    view.rerender(<DashboardEmbed key={DASH_B.id} dashboard={DASH_B} />);
    await waitFor(() => expect(embedMock).toHaveBeenCalledTimes(2));
    expect(instances[0].unmount).toHaveBeenCalledTimes(1);
    expect(instances[1].params.id).toBe(UUID_B);
    expect(instances[1].params.mountPoint).not.toBe(instances[0].params.mountPoint);
    expect(screen.getByTestId("dashboard-embed").querySelectorAll(".embed-mount")).toHaveLength(1);
  });

  it("보류 중에 대시보드를 바꿔도 이전 것은 풀린 뒤 늦게 unmount()된다", async () => {
    setup({}, true);
    const view = render(<DashboardEmbed key={DASH_A.id} dashboard={DASH_A} />);
    await waitFor(() => expect(instances[0]?.token).toBe(TOKEN));
    view.rerender(<DashboardEmbed key={DASH_B.id} dashboard={DASH_B} />);
    await waitFor(() => expect(instances[1]?.token).toBe(TOKEN));
    await act(async () => {
      instances[0].finish();
      instances[1].finish();
    });
    await waitFor(() => expect(instances[0].unmount).toHaveBeenCalledTimes(1));
    expect(instances[1].unmount).not.toHaveBeenCalled();
  });
});

describe("실패와 안내", () => {
  it("첫 입장권 요청이 실패하면 오류 안내와 '다시 시도' 버튼을 보이고, 누르면 다시 마운트한다", async () => {
    let attempts = 0;
    setup({ "POST /dashboards/5/guest-token": () => (++attempts === 1 ? apiError(503, "SUPERSET_UNAVAILABLE", "내부 문구") : tokenOk({} as never)) });
    render(<DashboardEmbed dashboard={DASH_A} />);
    const failed = await screen.findByTestId("embed-failed");
    expect(failed.textContent).toContain("대시보드 서비스에 연결할 수 없습니다");
    expect(failed.textContent).toContain("문의 번호: req-test");
    expect(failed.textContent).not.toContain("내부 문구");
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(embedMock).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByTestId("embed-failed")).toBeNull());
    expect(instances[1].token).toBe(TOKEN);
  });

  it("429는 기다릴 시간을 안내한다(Retry-After)", async () => {
    setup({
      "POST /dashboards/5/guest-token": () =>
        json(429, { error: { code: "GUEST_TOKEN_RATE_LIMITED", message: "x", details: { retry_after: 7 }, request_id: "r9" } }, { "Retry-After": "7" }),
    });
    render(<DashboardEmbed dashboard={DASH_A} />);
    const failed = await screen.findByTestId("embed-failed");
    expect(failed.textContent).toContain("요청이 너무 많습니다");
    expect(failed.textContent).toContain("7초");
  });

  it("Superset 거부(502)와 일반 오류도 쉬운 문구로 보인다", async () => {
    setup({ "POST /dashboards/5/guest-token": () => apiError(502, "SUPERSET_REJECTED") });
    render(<DashboardEmbed dashboard={DASH_A} />);
    expect((await screen.findByTestId("embed-failed")).textContent).toContain("관리자에게 문의");
  });

  it("열려 있는 동안 갱신 요청이 실패하면 배너로 알리고, 다시 성공하면 사라진다", async () => {
    let mode: "ok" | "expired" = "ok";
    setup({ "POST /dashboards/5/guest-token": () => (mode === "ok" ? tokenOk({} as never) : apiError(401, "UNAUTHENTICATED")) });
    render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(screen.queryByText(/불러오는 중/)).toBeNull());
    mode = "expired";
    await act(async () => {
      await instances[0].params.fetchGuestToken().catch(() => undefined);
    });
    const banner = screen.getByTestId("embed-refresh-problem");
    expect(banner.textContent).toContain("로그인 정보가 만료");
    expect(banner.textContent).toContain("자동으로 다시 시도");
    mode = "ok";
    await act(async () => {
      await instances[0].params.fetchGuestToken();
    });
    expect(screen.queryByTestId("embed-refresh-problem")).toBeNull();
  });
});

describe("허용 도메인 불일치 휴리스틱", () => {
  const readyWithFakeTimers = async () => {
    setup();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    render(<DashboardEmbed dashboard={DASH_A} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(screen.queryByText(/불러오는 중/)).toBeNull();
  };

  it("iframe이 로딩된 뒤 일정 시간이 지나도 안이 비어 있으면 관리자 안내를 보인다", async () => {
    await readyWithFakeTimers();
    expect(screen.queryByTestId("embed-blank-hint")).toBeNull();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    const hint = screen.getByTestId("embed-blank-hint");
    expect(hint.textContent).toContain("임베드 허용 도메인 설정을 확인하세요");
    expect(hint.textContent).toContain(window.location.origin);
  });

  it("빈 화면이면 iframe을 숨기고(원문 403 본문이 안 보이게) 포털 대시보드 번호와 다시 시도만 보인다", async () => {
    await readyWithFakeTimers();
    const frame = () => screen.getByTestId("dashboard-embed").querySelector(".embed-frame") as HTMLElement;
    expect(frame().hidden).toBe(false);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(frame().hidden).toBe(true);
    const hint = screen.getByTestId("embed-blank-hint");
    expect(hint.textContent).toContain(`문의 시 대시보드 번호 ${DASH_A.id}를 알려 주세요.`);
    expect(hint.textContent).not.toContain(DASH_A.embedded_uuid);
    expect(hint.querySelector("button")?.textContent).toBe("다시 시도");
  });

  it("한 번 비었다고 판정된 뒤 늦게 #app이 채워지면 안내를 걷고 iframe을 다시 보인다", async () => {
    await readyWithFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(screen.getByTestId("embed-blank-hint")).toBeTruthy();
    const doc = instances[0].iframe.contentDocument!;
    doc.body.innerHTML = '<div id="app"><div>대시보드</div></div>';
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RECHECK_MS + 100);
    });
    expect(screen.queryByTestId("embed-blank-hint")).toBeNull();
    expect((screen.getByTestId("dashboard-embed").querySelector(".embed-frame") as HTMLElement).hidden).toBe(false);
    // 채워진 뒤에는 더 이상 주기 확인 타이머가 남지 않는다.
    expect(vi.getTimerCount()).toBe(0);
  });

  it("안에 화면이 그려져 있으면(#app에 내용) 안내하지 않는다", async () => {
    await readyWithFakeTimers();
    const doc = instances[0].iframe.contentDocument!;
    doc.body.innerHTML = '<div id="app"><div>대시보드</div></div>';
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(screen.queryByTestId("embed-blank-hint")).toBeNull();
  });

  it("그 전에 언마운트하면 확인 타이머가 정리된다", async () => {
    setup();
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
    const view = render(<DashboardEmbed dashboard={DASH_A} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    view.unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("빈 화면 판정 뒤 재판정(3초) 진행 중 언마운트하면 타이머가 0이 된다", async () => {
    await readyWithFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(screen.getByTestId("embed-blank-hint")).toBeTruthy();
    expect(vi.getTimerCount()).toBeGreaterThan(0);
    cleanup();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("빈 화면 안내에서 '다시 시도'로 다시 마운트하면 이전 타이머가 정리되고 새 인스턴스가 정상 동작한다", async () => {
    await readyWithFakeTimers();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(screen.getByTestId("embed-blank-hint")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(embedMock).toHaveBeenCalledTimes(2);
    expect(instances[0].unmount).toHaveBeenCalledTimes(1);
    expect(screen.queryByTestId("embed-blank-hint")).toBeNull();
    expect(screen.getByTestId("dashboard-embed").querySelectorAll(".embed-mount")).toHaveLength(1);
    // 이전 타이머는 정리됐고 남은 것은 새 인스턴스의 첫 확인 타이머 하나뿐이다.
    expect(vi.getTimerCount()).toBe(1);
    // 새 인스턴스도 비어 있으면 다시 판정하고, 언마운트하면 모두 정리된다.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(EMPTY_CHECK_MS + 100);
    });
    expect(screen.getByTestId("embed-blank-hint")).toBeTruthy();
    cleanup();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("looksEmpty: iframe이 없거나 안을 읽을 수 없으면 판단하지 않는다", () => {
    expect(looksEmpty(null)).toBe(false);
    const fake = { get contentDocument(): Document { throw new Error("cross-origin"); } } as unknown as HTMLIFrameElement;
    expect(looksEmpty(fake)).toBe(false);
    expect(looksEmpty({ contentDocument: null } as unknown as HTMLIFrameElement)).toBe(false);
  });
});

describe("입장권은 어디에도 남지 않는다", () => {
  it("저장소·쿠키·URL·콘솔·화면(DOM)·이력에 입장권이 없다(정상과 실패 경로 모두)", async () => {
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    const pushState = vi.spyOn(window.history, "pushState");
    const replaceState = vi.spyOn(window.history, "replaceState");
    const consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((name) => vi.spyOn(console, name).mockImplementation(() => undefined));
    const cookieSet = vi.spyOn(document, "cookie", "set");
    let mode: "ok" | "limited" | "down" = "ok";
    const { fetchMock } = setup({
      "POST /dashboards/5/guest-token": () =>
        mode === "ok"
          ? tokenOk({} as never)
          : mode === "limited"
            ? json(429, { error: { code: "GUEST_TOKEN_RATE_LIMITED", message: `m ${TOKEN}`, details: { retry_after: 3, leaked: TOKEN }, request_id: "r" } }, { "Retry-After": "3" })
            : apiError(503, "SUPERSET_UNAVAILABLE", `m ${TOKEN}`),
    });
    render(<DashboardEmbed dashboard={DASH_A} />);
    await waitFor(() => expect(instances[0]?.token).toBe(TOKEN));
    for (const next of ["limited", "down"] as const) {
      mode = next;
      await act(async () => {
        await instances[0].params.fetchGuestToken().catch(() => undefined);
      });
    }
    // 요청 주소·옵션에도 입장권이 없다.
    for (const [url, init] of fetchMock.mock.calls as unknown as Array<[string, RequestInit]>) {
      expect(url).not.toContain("PAYLOAD-TOKEN-VALUE");
      expect(JSON.stringify(init)).not.toContain("PAYLOAD-TOKEN-VALUE");
    }
    expect(setItem).not.toHaveBeenCalled();
    expect(cookieSet).not.toHaveBeenCalled();
    expect(pushState).not.toHaveBeenCalled();
    expect(replaceState).not.toHaveBeenCalled();
    for (const spy of consoleSpies) expect(spy).not.toHaveBeenCalled();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain("PAYLOAD-TOKEN-VALUE");
    expect(JSON.stringify({ ...window.sessionStorage })).not.toContain("PAYLOAD-TOKEN-VALUE");
    expect(document.cookie).not.toContain("PAYLOAD-TOKEN-VALUE");
    expect(window.location.href).not.toContain("PAYLOAD-TOKEN-VALUE");
    expect(document.documentElement.outerHTML).not.toContain("PAYLOAD-TOKEN-VALUE");
    expect(Object.keys(window).filter((key) => /token|guest/i.test(key))).toEqual([]);
  });
});
