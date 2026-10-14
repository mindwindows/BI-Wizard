import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler } from "../../test-utils";
import { buildAuditQuery } from "./api";
import { EMPTY_FILTERS } from "./types";

/** S10 감사 기록 목록 시험(FU-2a). 응답은 05 §2-7 F1 계약대로 만든 가짜 서버다(F1은 backend에 구현됐고 시험은 계약 모양의 목으로 한다). */
const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: "" };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const USERS = [
  { id: 1, login_id: "admin", display_name: "관리자 김", is_admin: true, is_active: true, memberships: [] },
  { id: 7, login_id: "entry", display_name: "박입력", is_admin: false, is_active: true, memberships: [] },
  { id: 8, login_id: "old", display_name: "이퇴사", is_admin: false, is_active: false, memberships: [] },
];

const item = (id: number, extra: Record<string, unknown> = {}) => ({
  id,
  occurred_at: "2026-10-13T09:05:07+09:00",
  actor: { id: 1, display_name: "관리자 김" },
  actor_source: "user",
  action: "team.update",
  target_type: "team",
  target_id: 10,
  details: { target_name: "영업", changes: { name: { from: "영업", to: "영업1" } } },
  ...extra,
});

const pageOf = (items: unknown[], total = items.length, offset = 0) => json(200, { items, total, limit: 50, offset });

function open(handlers: Record<string, Handler>, me: unknown = ADMIN_ME, path = "/admin/audit", basePath = BASE) {
  window.__APP_CONFIG__ = { basePath, supersetRoot: "" };
  const installed = installFetch(
    {
      ...HEALTH_HANDLERS,
      "GET /me": () => json(200, me),
      "GET /users": () => json(200, { items: USERS, total: USERS.length, limit: 200, offset: 0 }),
      ...handlers,
    },
    basePath,
  );
  render(<App router={createTestRouter(basePath, `${basePath}${path}`)} />);
  return installed;
}

const auditCalls = (calls: Array<{ path: string; query: URLSearchParams }>) => calls.filter((c) => c.path === "/audit-logs");
const lastQuery = (calls: Array<{ path: string; query: URLSearchParams }>) => Object.fromEntries(auditCalls(calls).at(-1)!.query.entries());
const rows = () => within(screen.getByRole("table", { name: "감사 기록" })).getAllByRole("row").slice(1);
const field = (name: string) => screen.getByLabelText(name) as HTMLInputElement | HTMLSelectElement;
const ready = async () => {
  await screen.findByTestId("screen-S10");
  await waitFor(() => expect((field("행위자") as HTMLSelectElement).disabled).toBe(false));
};

describe("buildAuditQuery", () => {
  it("빈 필터는 limit·offset만 보낸다", () => {
    expect(buildAuditQuery(EMPTY_FILTERS, 0)).toBe("?limit=50&offset=0");
  });
  it("모든 필터를 05 F1 이름으로 바꾼다(actor → actor_user_id, targetType → target_type)", () => {
    const q = buildAuditQuery({ from: "2026-10-01", to: "2026-10-13", actor: "7", targetType: "dataset", targetId: "12", action: "column.add" }, 100);
    expect(q).toBe("?from=2026-10-01&to=2026-10-13&actor_user_id=7&target_type=dataset&target_id=12&action=column.add&limit=50&offset=100");
  });
  it("대상 종류가 없으면 대상 번호를 보내지 않는다", () => {
    expect(buildAuditQuery({ ...EMPTY_FILTERS, targetId: "12" }, 0)).toBe("?limit=50&offset=0");
  });
});

describe("S10 목록", () => {
  it("표(일시·행위자·행위·대상·요약)를 보여 주고 첫 요청은 필터 없이 50건 단위다", async () => {
    const { calls } = open({
      "GET /audit-logs": () =>
        pageOf([
          item(3),
          item(2, { actor: null, actor_source: "cli", action: "user.bootstrap_admin", target_type: "user", target_id: 1, details: { target_name: "관리자 김", is_admin: true } }),
          item(1, { action: "member.set", target_id: 20, details: { target_name: "운영", user_id: 7, role: "definer", role_from: "entry" } }),
        ]),
    });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    expect(Object.fromEntries(auditCalls(calls)[0].query.entries())).toEqual({ limit: "50", offset: "0" });
    expect(within(screen.getByRole("table", { name: "감사 기록" })).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["일시", "행위자", "행위", "대상", "요약"]);
    expect(rows().map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["2026-10-13 09:05:07", "관리자 김", "팀 수정", "팀 #10 영업", "이름 '영업'→'영업1'"],
      ["2026-10-13 09:05:07", "서버 명령", "최초 관리자 등록", "사용자 #1 관리자 김", "서버 명령으로 최초 관리자 등록"],
      ["2026-10-13 09:05:07", "관리자 김", "소속 지정·변경", "팀 #20 운영", "사용자 '박입력', 역할 입력자→정의 담당자"],
    ]);
    expect(screen.getByRole("navigation", { name: "관리 메뉴" })).toBeTruthy();
  });

  it("행위자 표시: actor가 null이면 '서버 명령', actor가 있는데 이름이 비면 '사용자 #번호'", async () => {
    open({
      "GET /audit-logs": () =>
        pageOf([item(2, { actor: null, actor_source: "cli" }), item(1, { actor: { id: 42, display_name: "" } })]),
    });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    expect(rows().map((r) => within(r).getAllByRole("cell")[1].textContent)).toEqual(["서버 명령", "사용자 #42"]);
  });

  it("읽기 전용이다: 수정·삭제·내보내기·저장 버튼이 없다", async () => {
    open({ "GET /audit-logs": () => pageOf([item(1)]) });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    const names = screen.getAllByRole("button").map((b) => b.textContent);
    expect(names).toEqual(["조회", "필터 지우기"]);
    expect(names.some((n) => /수정|삭제|내보내기|저장|엑셀|다운로드/.test(n ?? ""))).toBe(false);
  });

  it("허용 키 밖 값(행 값·수식·토큰 모양)은 화면 어디에도 나오지 않는다", async () => {
    open({
      "GET /audit-logs": () =>
        pageOf([
          item(1, { details: { target_name: "영업", changes: { name: { from: "가", to: "나" }, c_9: { from: "행값-ZZ", to: "행값-YY" } }, row_values: { c_1: "행값-XX" }, formula: "=SECRET()", token: "eyJhbGciOiJIUzI1NiJ9.abc.def" } }),
          item(2, { action: "future.action", details: { anything: "행값-WW" } }),
        ]),
    });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    const text = document.body.textContent ?? "";
    expect(text).toContain("이름 '가'→'나' (일부 상세 생략)");
    expect(text).toContain("(상세 생략)");
    expect(text).toContain("알 수 없는 행위");
    for (const leaked of ["행값-", "SECRET", "eyJ", "row_values", "c_9", "c_1", "future.action"]) expect(text).not.toContain(leaked);
  });

  it("소속 요약에 사용자 목록(A5)의 표시 이름을 쓴다", async () => {
    open({ "GET /audit-logs": () => pageOf([item(1, { action: "member.remove", target_id: 20, details: { target_name: "운영", user_id: 8, role_from: "entry" } })]) });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    expect(rows()[0].textContent).toContain("사용자 '이퇴사' 소속 해제, 이전 역할 입력자");
  });

  it("루트 배포(빈 basePath)에서도 /api 상대경로로 부른다", async () => {
    const { calls } = open({ "GET /audit-logs": () => pageOf([item(1)]) }, ADMIN_ME, "/admin/audit", "");
    await screen.findByRole("table", { name: "감사 기록" });
    expect(auditCalls(calls)).toHaveLength(1);
  });
});

describe("S10 필터", () => {
  it("조회를 누르면 모든 필터를 쿼리로 보내고 첫 쪽부터 다시 읽는다", async () => {
    const { calls } = open({ "GET /audit-logs": () => pageOf([item(1)], 120) });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(lastQuery(calls).offset).toBe("50"));

    const before = auditCalls(calls).length;
    fireEvent.change(field("시작일"), { target: { value: "2026-10-01" } });
    fireEvent.change(field("종료일"), { target: { value: "2026-10-13" } });
    fireEvent.change(field("행위자"), { target: { value: "7" } });
    fireEvent.change(field("대상 종류"), { target: { value: "dataset" } });
    fireEvent.change(field("대상 번호"), { target: { value: "12" } });
    fireEvent.change(field("행위"), { target: { value: "column.add" } });
    // 조회 전에는 요청이 늘지 않는다(바꾼 입력이 화면에 반영될 시간을 준 뒤 확인).
    await screen.findByTestId("audit-draft-hint");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(auditCalls(calls)).toHaveLength(before);
    fireEvent.click(screen.getByRole("button", { name: "조회" }));
    await waitFor(() => expect(auditCalls(calls)).toHaveLength(before + 1));
    expect(lastQuery(calls)).toEqual({ from: "2026-10-01", to: "2026-10-13", actor_user_id: "7", target_type: "dataset", target_id: "12", action: "column.add", limit: "50", offset: "0" });
  });

  it("행위자·행위·대상 종류 선택지는 한국어이고 행위는 17개다", async () => {
    open({ "GET /audit-logs": () => pageOf([]) });
    await ready();
    const actions = [...(field("행위") as HTMLSelectElement).options].map((o) => o.textContent);
    expect(actions).toHaveLength(18);
    expect(actions.slice(0, 5)).toEqual(["전체", "데이터셋 만들기", "데이터셋 설정 변경", "데이터셋 보관", "데이터셋 복구"]);
    expect([...(field("대상 종류") as HTMLSelectElement).options].map((o) => o.textContent)).toEqual(["전체", "팀", "사용자", "데이터셋", "대시보드"]);
    expect([...(field("행위자") as HTMLSelectElement).options].map((o) => o.textContent)).toEqual(["전체", "관리자 김", "박입력", "이퇴사 (사용 중지)"]);
  });

  it("대상 번호는 대상 종류를 고른 뒤에만 입력할 수 있고 종류를 바꾸면 비워진다", async () => {
    open({ "GET /audit-logs": () => pageOf([]) });
    await ready();
    expect(field("대상 번호").disabled).toBe(true);
    fireEvent.change(field("대상 종류"), { target: { value: "team" } });
    expect(field("대상 번호").disabled).toBe(false);
    fireEvent.change(field("대상 번호"), { target: { value: "5" } });
    fireEvent.change(field("대상 종류"), { target: { value: "user" } });
    expect(field("대상 번호").value).toBe("");
    fireEvent.change(field("대상 종류"), { target: { value: "" } });
    expect(field("대상 번호").disabled).toBe(true);
  });

  it("시작일이 종료일보다 늦거나 번호가 정수가 아니면 요청하지 않고 알린다", async () => {
    const { calls } = open({ "GET /audit-logs": () => pageOf([]) });
    await ready();
    await screen.findByTestId("audit-empty");
    const before = auditCalls(calls).length;
    fireEvent.change(field("시작일"), { target: { value: "2026-10-13" } });
    fireEvent.change(field("종료일"), { target: { value: "2026-10-01" } });
    fireEvent.click(screen.getByRole("button", { name: "조회" }));
    expect((await screen.findByTestId("audit-form-error")).textContent).toContain("시작일이 종료일보다 늦습니다");
    fireEvent.change(field("시작일"), { target: { value: "" } });
    fireEvent.change(field("종료일"), { target: { value: "" } });
    fireEvent.change(field("대상 종류"), { target: { value: "team" } });
    fireEvent.change(field("대상 번호"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "조회" }));
    expect((await screen.findByTestId("audit-form-error")).textContent).toContain("1 이상의 정수");
    expect(auditCalls(calls)).toHaveLength(before);
  });

  it("필터 지우기는 입력과 조건을 모두 비우고 처음부터 다시 읽는다", async () => {
    const { calls } = open({ "GET /audit-logs": () => pageOf([item(1)]) });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    fireEvent.change(field("행위"), { target: { value: "team.create" } });
    fireEvent.click(screen.getByRole("button", { name: "조회" }));
    await waitFor(() => expect(lastQuery(calls).action).toBe("team.create"));
    fireEvent.click(screen.getByRole("button", { name: "필터 지우기" }));
    await waitFor(() => expect(lastQuery(calls)).toEqual({ limit: "50", offset: "0" }));
    expect(field("행위").value).toBe("");
  });

  it("사용자 목록을 못 읽어도 다른 필터로 조회할 수 있다", async () => {
    open({ "GET /users": () => apiError(503, "SERVICE_UNAVAILABLE"), "GET /audit-logs": () => pageOf([item(1)]) });
    await screen.findByRole("table", { name: "감사 기록" });
    expect(await screen.findByText(/행위자를 고를 수 없습니다/)).toBeTruthy();
    expect(field("행위자").disabled).toBe(true);
    expect(field("행위").disabled).toBe(false);
  });
});

describe("S10 빈 상태", () => {
  it("필터가 없으면 '아직 기록이 없습니다'", async () => {
    open({ "GET /audit-logs": () => pageOf([]) });
    await ready();
    expect((await screen.findByTestId("audit-empty")).textContent).toBe("아직 기록이 없습니다.");
    expect(screen.queryByRole("table", { name: "감사 기록" })).toBeNull();
  });

  it("필터가 있으면 '조건에 맞는 기록이 없습니다'와 필터 지우기, 누르면 필터 없이 다시 읽는다", async () => {
    const { calls } = open({ "GET /audit-logs": (call) => (call.query.get("action") ? pageOf([]) : pageOf([item(1)])) });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    fireEvent.change(field("행위"), { target: { value: "dashboard.create" } });
    fireEvent.click(screen.getByRole("button", { name: "조회" }));
    const empty = await screen.findByTestId("audit-empty");
    expect(empty.textContent).toContain("조건에 맞는 기록이 없습니다.");
    fireEvent.click(within(empty).getByRole("button", { name: "필터 지우기" }));
    await screen.findByRole("table", { name: "감사 기록" });
    expect(lastQuery(calls)).toEqual({ limit: "50", offset: "0" });
  });
});

describe("S10 페이지 이동", () => {
  it("50건 단위로 이전·다음을 누르면 offset이 바뀌고 건수 표시가 갱신된다", async () => {
    const { calls } = open({
      "GET /audit-logs": (call) => {
        const offset = Number(call.query.get("offset"));
        return pageOf(Array.from({ length: Math.min(50, 120 - offset) }, (_, i) => item(1000 - offset - i)), 120, offset);
      },
    });
    await ready();
    await screen.findByRole("table", { name: "감사 기록" });
    expect(rows()).toHaveLength(50);
    expect(screen.getByText("전체 120건 중 1–50")).toBeTruthy();
    expect((screen.getByRole("button", { name: "이전" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText("전체 120건 중 51–100");
    expect(lastQuery(calls).offset).toBe("50");
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText("전체 120건 중 101–120");
    expect(rows()).toHaveLength(20);
    expect((screen.getByRole("button", { name: "다음" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "이전" }));
    await screen.findByText("전체 120건 중 51–100");
    expect(lastQuery(calls).offset).toBe("50");
  });

  it("50건 이하면 쪽 이동줄이 없다", async () => {
    open({ "GET /audit-logs": () => pageOf([item(1)]) });
    await screen.findByRole("table", { name: "감사 기록" });
    expect(screen.queryByRole("button", { name: "다음" })).toBeNull();
  });
});

describe("S10 권한과 오류", () => {
  it("관리 메뉴의 '감사 기록'은 관리자에게만 보이고 주소는 basePath를 포함한다", async () => {
    open({ "GET /audit-logs": () => pageOf([]) }, ADMIN_ME, "/");
    const nav = await screen.findByRole("navigation", { name: "관리 메뉴" });
    expect(within(nav).getByRole("link", { name: "감사 기록" }).getAttribute("href")).toBe(`${BASE}/admin/audit`);
    cleanup();
    open({ "GET /audit-logs": () => pageOf([]) }, MEMBER_ME, "/");
    await screen.findByRole("navigation", { name: "주 메뉴" });
    expect(screen.queryByRole("navigation", { name: "관리 메뉴" })).toBeNull();
    expect(screen.queryByRole("link", { name: "감사 기록" })).toBeNull();
  });

  it("비관리자가 주소로 직접 열면 안내만 보이고 목록·필터를 그리지 않으며 API도 부르지 않는다", async () => {
    const { calls } = open({ "GET /audit-logs": () => pageOf([item(1)]) }, MEMBER_ME);
    expect((await screen.findByTestId("audit-forbidden")).textContent).toBe("관리자만 볼 수 있습니다");
    expect(screen.queryByRole("form", { name: "감사 기록 필터" })).toBeNull();
    expect(screen.queryByRole("table", { name: "감사 기록" })).toBeNull();
    expect(screen.queryByRole("button", { name: "조회" })).toBeNull();
    expect(calls.some((c) => c.path === "/audit-logs" || c.path === "/users")).toBe(false);
  });

  it("서버가 403 FORBIDDEN을 주면(화면은 관리자로 알고 있어도) 안내만 보이고 필터를 지운다", async () => {
    open({ "GET /audit-logs": () => apiError(403, "FORBIDDEN") });
    expect((await screen.findByTestId("audit-forbidden")).textContent).toBe("관리자만 볼 수 있습니다");
    expect(screen.queryByRole("form", { name: "감사 기록 필터" })).toBeNull();
    expect(screen.queryByRole("table", { name: "감사 기록" })).toBeNull();
  });

  it("503이면 잠시 뒤 다시 시도 안내와 다시 시도 버튼이 나오고, 누르면 다시 읽는다", async () => {
    let fail = true;
    const { calls } = open({ "GET /audit-logs": () => (fail ? apiError(503, "SERVICE_UNAVAILABLE") : pageOf([item(1)])) });
    const alert = await screen.findByText(/잠시 뒤 다시 시도하세요/);
    expect(alert).toBeTruthy();
    expect(screen.getByRole("form", { name: "감사 기록 필터" })).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await screen.findByRole("table", { name: "감사 기록" });
    expect(auditCalls(calls)).toHaveLength(2);
    expect(screen.queryByText(/잠시 뒤 다시 시도하세요/)).toBeNull();
  });

  it("422 오류는 필드 이름을 한국어로 알려 준다", async () => {
    open({
      "GET /audit-logs": () => apiError(422, "VALIDATION_ERROR", "x", { fields: [{ field: "to", code: "OUT_OF_RANGE" }] }),
    });
    expect((await screen.findByRole("alert")).textContent).toContain("종료일: 허용 범위를 벗어났습니다");
  });
});
