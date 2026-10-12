import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import {
  ADMIN_ME,
  HEALTH_HANDLERS,
  MEMBER_ME,
  apiError,
  installFetch,
  json,
  noContent,
  type Handler,
} from "../../test-utils";
import { WORK_TEAM_STORAGE_KEY } from "./MeContext";

const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

function open(path = "/") {
  return render(<App router={createTestRouter(BASE, `${BASE}${path}`)} />);
}

const withMe = (me: Handler, extra: Record<string, Handler> = {}) => installFetch({ ...HEALTH_HANDLERS, "GET /me": me, ...extra });

describe("/me 상태별 화면", () => {
  it("정상: 내 정보와 소속 팀, 주 메뉴를 보여 준다", async () => {
    withMe(() => json(200, MEMBER_ME));
    open();
    expect(await screen.findByRole("navigation", { name: "주 메뉴" })).toBeTruthy();
    expect(screen.getAllByText(/입력자 박/).length).toBeGreaterThan(0);
    const table = await screen.findByRole("table", { name: "소속 팀" });
    expect(within(table).getByText("운영")).toBeTruthy();
    expect(within(table).getByText("입력자")).toBeTruthy();
  });

  it("소속 팀이 없으면 안내 문구를 보여 준다(접근 거부가 아님)", async () => {
    withMe(() => json(200, { ...MEMBER_ME, memberships: [] }));
    open();
    expect(await screen.findByTestId("no-teams")).toBeTruthy();
    expect(screen.queryByText("접근 권한이 없습니다")).toBeNull();
    expect(screen.getByText("소속 팀 없음")).toBeTruthy();
  });

  it("401: 접근 권한이 없습니다 + 보조 안내, 메뉴는 숨긴다", async () => {
    withMe(() => apiError(401, "UNAUTHENTICATED"));
    open();
    expect(await screen.findByRole("heading", { name: /접근 권한이 없습니다/ })).toBeTruthy();
    expect(screen.getByTestId("access-denied-guide").textContent).toContain("로그인 정보를 확인하지 못했습니다");
    expect(screen.queryByRole("navigation", { name: "주 메뉴" })).toBeNull();
    expect(screen.queryByRole("navigation", { name: "관리 메뉴" })).toBeNull();
  });

  it("403 USER_NOT_REGISTERED: 미등록 보조 안내", async () => {
    withMe(() => apiError(403, "USER_NOT_REGISTERED"));
    open("/datasets");
    expect(await screen.findByRole("heading", { name: /접근 권한이 없습니다/ })).toBeTruthy();
    expect(screen.getByTestId("access-denied-guide").textContent).toContain("등록되지 않은 사용자");
    // 딥링크로 들어와도 본문 화면은 열리지 않는다.
    expect(screen.queryByTestId("screen-S2")).toBeNull();
  });

  it("403 USER_INACTIVE: 비활성 보조 안내", async () => {
    withMe(() => apiError(403, "USER_INACTIVE"));
    open();
    expect(await screen.findByRole("heading", { name: /접근 권한이 없습니다/ })).toBeTruthy();
    expect(screen.getByTestId("access-denied-guide").textContent).toContain("사용이 중지된 계정");
  });

  it("다시 확인을 누르면 /me를 다시 읽는다", async () => {
    let n = 0;
    const { calls } = withMe(() => (n++ === 0 ? apiError(403, "USER_NOT_REGISTERED") : json(200, MEMBER_ME)));
    open();
    fireEvent.click(await screen.findByRole("button", { name: "다시 확인" }));
    expect(await screen.findByRole("navigation", { name: "주 메뉴" })).toBeTruthy();
    expect(calls.filter((c) => c.path === "/me")).toHaveLength(2);
  });

  it("그 밖의 /me 실패는 접근 거부가 아니라 일반 오류와 다시 시도", async () => {
    withMe(() => apiError(500, "INTERNAL_ERROR"));
    open();
    expect(await screen.findByRole("button", { name: "다시 시도" })).toBeTruthy();
    expect(screen.queryByText("접근 권한이 없습니다")).toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("문의 번호: req-test");
  });

  it("503 SERVICE_UNAVAILABLE: 접근 안내가 아니라 일시 장애 문구와 다시 시도(로그아웃과 구분)", async () => {
    let n = 0;
    const { calls } = withMe(() => (n++ === 0 ? apiError(503, "SERVICE_UNAVAILABLE") : json(200, MEMBER_ME)));
    open();
    const retry = await screen.findByRole("button", { name: "다시 시도" });
    expect(screen.getByRole("alert").textContent).toContain("서버가 일시적으로 응답하지 못합니다. 잠시 뒤 다시 시도하세요");
    expect(screen.queryByRole("heading", { name: /접근 권한이 없습니다/ })).toBeNull();
    expect(screen.queryByTestId("access-denied-guide")).toBeNull();
    fireEvent.click(retry);
    expect(await screen.findByRole("navigation", { name: "주 메뉴" })).toBeTruthy();
    expect(calls.filter((c) => c.path === "/me")).toHaveLength(2);
  });

  it("계약과 다른 /me 응답은 오류로 처리한다", async () => {
    withMe(() => json(200, { hello: "x" }));
    open();
    expect(await screen.findByRole("button", { name: "다시 시도" })).toBeTruthy();
  });
});

describe("관리 메뉴 표시 조건", () => {
  it("관리자에게만 S6·S8·S9 메뉴를 보여 준다", async () => {
    withMe(() => json(200, ADMIN_ME));
    open();
    const nav = await screen.findByRole("navigation", { name: "관리 메뉴" });
    expect(within(nav).getByRole("link", { name: "권한 관리" }).getAttribute("href")).toBe(`${BASE}/admin/permissions`);
    expect(within(nav).getByRole("link", { name: "대시보드 연결" })).toBeTruthy();
    expect(within(nav).getByRole("link", { name: "현황" })).toBeTruthy();
  });

  it("일반 사용자에게는 관리 메뉴가 없고, 직접 접속해도 S6 API를 부르지 않는다", async () => {
    const { calls } = withMe(() => json(200, MEMBER_ME));
    open("/admin/permissions");
    expect(await screen.findByText("관리자만 사용할 수 있는 화면입니다.")).toBeTruthy();
    expect(screen.queryByRole("navigation", { name: "관리 메뉴" })).toBeNull();
    expect(calls.some((c) => c.path === "/users" || c.path === "/teams")).toBe(false);
  });
});

describe("작업 팀 선택", () => {
  it("여러 팀 소속이면 첫 팀이 기본이고, 바꾸면 sessionStorage에 남아 다음 화면에서도 유지된다", async () => {
    withMe(() => json(200, ADMIN_ME));
    const first = open();
    const select = (await screen.findByLabelText("작업 팀")) as HTMLSelectElement;
    expect(select.value).toBe("10");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["영업", "운영"]);
    fireEvent.change(select, { target: { value: "20" } });
    expect((screen.getByLabelText("작업 팀") as HTMLSelectElement).value).toBe("20");
    expect(window.sessionStorage.getItem(WORK_TEAM_STORAGE_KEY)).toBe("20");
    first.unmount();

    open();
    expect(((await screen.findByLabelText("작업 팀")) as HTMLSelectElement).value).toBe("20");
  });

  it("저장된 팀이 현재 소속에 없으면 첫 소속 팀을 쓴다", async () => {
    window.sessionStorage.setItem(WORK_TEAM_STORAGE_KEY, "999");
    withMe(() => json(200, ADMIN_ME));
    open();
    expect(((await screen.findByLabelText("작업 팀")) as HTMLSelectElement).value).toBe("10");
  });

  const MIXED_ME = {
    ...ADMIN_ME,
    memberships: [
      { team_id: 10, team_code: "old", team_name: "폐쇄팀", team_is_active: false, role: "definer" },
      { team_id: 20, team_code: "ops", team_name: "운영", team_is_active: true, role: "entry" },
      { team_id: 30, team_code: "hr", team_name: "인사", team_is_active: true, role: "definer" },
    ],
  };

  it("비활성 팀은 선택할 수 없고, 기본 선택은 첫 활성 팀이다", async () => {
    withMe(() => json(200, MIXED_ME));
    open();
    const select = (await screen.findByLabelText("작업 팀")) as HTMLSelectElement;
    expect(select.value).toBe("20");
    const inactive = within(select).getByRole("option", { name: /폐쇄팀/ }) as HTMLOptionElement;
    expect(inactive.disabled).toBe(true);
    expect(inactive.textContent).toContain("비활성");
    expect((within(select).getByRole("option", { name: "운영" }) as HTMLOptionElement).disabled).toBe(false);
  });

  it("저장된 선택이 비활성 팀이면 첫 활성 팀을 쓴다", async () => {
    window.sessionStorage.setItem(WORK_TEAM_STORAGE_KEY, "10");
    withMe(() => json(200, MIXED_ME));
    open();
    expect(((await screen.findByLabelText("작업 팀")) as HTMLSelectElement).value).toBe("20");
  });

  it("활성 팀이 하나도 없으면 작업 팀이 없다는 안내를 보인다", async () => {
    withMe(() =>
      json(200, { ...MEMBER_ME, memberships: [{ team_id: 20, team_code: "ops", team_name: "운영", team_is_active: false, role: "entry" }] }),
    );
    open();
    expect(await screen.findByText("활성 팀 없음")).toBeTruthy();
    expect(screen.queryByLabelText("작업 팀")).toBeNull();
  });

  it("홈의 소속 목록은 비활성 팀에 '비활성'을 표시한다", async () => {
    withMe(() => json(200, MIXED_ME));
    open();
    const table = await screen.findByRole("table", { name: "소속 팀" });
    const row = within(table).getByText("폐쇄팀").closest("tr")!;
    expect(within(row).getByText("비활성")).toBeTruthy();
    expect(within(table).getByText("운영").closest("tr")!.textContent).not.toContain("비활성");
    expect(within(row).queryByText("선택됨")).toBeNull();
  });

  it("선택은 서버로 보내지 않는다(쓰기 호출 없음)", async () => {
    const { calls } = withMe(() => json(200, ADMIN_ME));
    open();
    fireEvent.change(await screen.findByLabelText("작업 팀"), { target: { value: "20" } });
    expect(calls.filter((c) => c.method !== "GET")).toEqual([]);
  });
});

describe("스텁 신원 전환기", () => {
  const STUBS = {
    items: [
      { login_id: "admin1", display_name: "관리자 김", is_admin: true },
      { login_id: "user1", display_name: "입력자 박", is_admin: false },
    ],
    current: "admin1",
  };

  it("DV1이 200이면 전환기를 보여 준다", async () => {
    withMe(() => json(200, ADMIN_ME), { "GET /dev/stub-users": () => json(200, STUBS) });
    open();
    const select = (await screen.findByLabelText("개발용 신원")) as HTMLSelectElement;
    expect(select.value).toBe("admin1");
    expect(within(select).getAllByRole("option")).toHaveLength(3);
  });

  it("DV1이 404(운영 설정)이면 전환기가 없다", async () => {
    const { calls } = withMe(() => json(200, ADMIN_ME), { "GET /dev/stub-users": () => apiError(404, "NOT_FOUND") });
    open();
    await screen.findByRole("navigation", { name: "주 메뉴" });
    await waitFor(() => expect(calls.some((c) => c.path === "/dev/stub-users")).toBe(true));
    expect(screen.queryByTestId("stub-switcher")).toBeNull();
    expect(screen.queryByLabelText("개발용 신원")).toBeNull();
  });

  it("스텁 호출이 아예 실패(연결 불가)해도 숨기고 화면은 정상이다", async () => {
    withMe(() => json(200, ADMIN_ME), { "GET /dev/stub-users": () => apiError(500, "INTERNAL_ERROR") });
    open();
    await screen.findByRole("navigation", { name: "주 메뉴" });
    expect(screen.queryByTestId("stub-switcher")).toBeNull();
  });

  it("사용자를 고르면 PUT 뒤 /me를 다시 읽고 신원이 바뀐다", async () => {
    let who = ADMIN_ME;
    const { calls } = withMe(() => json(200, who), {
      "GET /dev/stub-users": () => json(200, STUBS),
      "PUT /dev/stub-user": () => {
        who = MEMBER_ME;
        return noContent();
      },
    });
    open();
    fireEvent.change(await screen.findByLabelText("개발용 신원"), { target: { value: "user1" } });
    await waitFor(() => expect(screen.queryByRole("navigation", { name: "관리 메뉴" })).toBeNull());
    expect(screen.getAllByText("입력자 박").length).toBeGreaterThan(0);
    const put = calls.find((c) => c.method === "PUT")!;
    expect(put.path).toBe("/dev/stub-user");
    expect(put.body).toEqual({ login_id: "user1" });
    const putIndex = calls.indexOf(put);
    expect(calls.slice(putIndex + 1).some((c) => c.path === "/me")).toBe(true);
  });

  it("선택 안 함을 고르면 DELETE 뒤 /me를 다시 읽는다(스텁 해제 -> 401)", async () => {
    let cleared = false;
    const { calls } = withMe(() => (cleared ? apiError(401, "UNAUTHENTICATED") : json(200, ADMIN_ME)), {
      "GET /dev/stub-users": () => json(200, STUBS),
      "DELETE /dev/stub-user": () => {
        cleared = true;
        return noContent();
      },
    });
    open();
    fireEvent.change(await screen.findByLabelText("개발용 신원"), { target: { value: "" } });
    expect(await screen.findByRole("heading", { name: /접근 권한이 없습니다/ })).toBeTruthy();
    // 접근 거부 화면에서도 전환기는 남아 다시 고를 수 있다.
    expect(screen.getByLabelText("개발용 신원")).toBeTruthy();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/dev/stub-user")).toBe(true);
  });

  it("PUT 실패(미등록 404)는 쉬운 문구로 알린다", async () => {
    withMe(() => json(200, ADMIN_ME), {
      "GET /dev/stub-users": () => json(200, STUBS),
      "PUT /dev/stub-user": () => apiError(404, "NOT_FOUND"),
    });
    open();
    fireEvent.change(await screen.findByLabelText("개발용 신원"), { target: { value: "user1" } });
    expect((await screen.findByText(/대상을 찾을 수 없습니다/)).textContent).toBeTruthy();
  });
});
