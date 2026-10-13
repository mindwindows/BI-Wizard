import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../../App";
import { createTestRouter } from "../../../routes";
import {
  ADMIN_ME,
  HEALTH_HANDLERS,
  apiError,
  installFetch,
  json,
  noContent,
  type Handler,
  type RecordedCall,
} from "../../../test-utils";

const BASE = "/bi-wizard";

const TEAMS = [
  { id: 10, code: "sales", name: "영업", is_active: true },
  { id: 20, code: "ops", name: "운영", is_active: false },
];

const USERS = [
  { id: 1, login_id: "kim", display_name: "관리자 김", is_admin: true, is_active: true, memberships: [{ team_id: 10, role: "definer" }] },
  { id: 2, login_id: "park", display_name: "입력자 박", is_admin: false, is_active: true, memberships: [{ team_id: 20, role: "entry" }] },
  { id: 3, login_id: "lee", display_name: "퇴사자 이", is_admin: false, is_active: false, memberships: [] },
];

const page = <T,>(items: T[], total = items.length, limit = 50, offset = 0) => json(200, { items, total, limit, offset });

function setup(extra: Record<string, Handler> = {}) {
  return installFetch({
    ...HEALTH_HANDLERS,
    "GET /me": () => json(200, ADMIN_ME),
    "GET /teams": () => page(TEAMS, TEAMS.length, 200),
    "GET /users": () => page(USERS),
    ...extra,
  });
}

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

async function openS6() {
  render(<App router={createTestRouter(BASE, `${BASE}/admin/permissions`)} />);
  await screen.findByRole("table", { name: "팀과 사용자 권한" });
}

const writes = (calls: RecordedCall[]) => calls.filter((c) => c.method !== "GET").map((c) => `${c.method} ${c.path}`);
const cell = (user: string, team: string) => screen.getByLabelText(`${user} - ${team} 역할`) as HTMLSelectElement;

describe("S6 팀×사용자 격자 (A2·A5)", () => {
  it("A2·A5 응답으로 격자를 그리고 목록 규칙(limit/offset)으로 호출한다", async () => {
    const { calls } = setup();
    await openS6();
    const teamsCall = calls.find((c) => c.path === "/teams")!;
    expect(teamsCall.query.get("limit")).toBe("200");
    expect(teamsCall.query.get("offset")).toBe("0");
    const usersCall = calls.find((c) => c.path === "/users")!;
    expect(usersCall.query.get("limit")).toBe("50");
    expect(usersCall.query.get("offset")).toBe("0");
    expect(cell("관리자 김", "영업").value).toBe("definer");
    expect(cell("입력자 박", "운영").value).toBe("entry");
    expect(cell("퇴사자 이", "영업").value).toBe("");
  });

  it("비활성 팀·사용자를 표시한다", async () => {
    setup();
    await openS6();
    expect(screen.getByText(/ops · 비활성/)).toBeTruthy();
    expect(screen.getByText("비활성")).toBeTruthy();
    expect(screen.getAllByText("관리자").length).toBeGreaterThan(0);
  });

  it("사용자가 없으면 빈 상태 안내, 팀이 없으면 팀 안내", async () => {
    setup({ "GET /users": () => page([]), "GET /teams": () => page([], 0, 200) });
    render(<App router={createTestRouter(BASE, `${BASE}/admin/permissions`)} />);
    expect(await screen.findByTestId("no-users")).toBeTruthy();
    expect(screen.getByTestId("no-teams-admin")).toBeTruthy();
  });

  it("불러오기 실패는 쉬운 문구와 다시 불러오기", async () => {
    setup({ "GET /users": () => apiError(403, "FORBIDDEN") });
    render(<App router={createTestRouter(BASE, `${BASE}/admin/permissions`)} />);
    expect((await screen.findByRole("alert")).textContent).toContain("권한이 없습니다");
    expect(screen.getByRole("button", { name: "다시 불러오기" })).toBeTruthy();
  });

  it("사용자 목록은 offset으로 쪽을 넘기고 검색은 q를 보낸다", async () => {
    const { calls } = setup({ "GET /users": () => page(USERS, 120) });
    await openS6();
    expect(screen.getByText(/전체 120명 중 1–50/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "이전" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText(/전체 120명 중 51–100/);
    expect(calls.filter((c) => c.path === "/users").at(-1)!.query.get("offset")).toBe("50");
    fireEvent.change(screen.getByLabelText("사용자 검색"), { target: { value: " 김 " } });
    fireEvent.click(screen.getByRole("button", { name: "검색" }));
    await waitFor(() => expect(calls.filter((c) => c.path === "/users").at(-1)!.query.get("q")).toBe("김"));
    expect(calls.filter((c) => c.path === "/users").at(-1)!.query.get("offset")).toBe("0");
  });

  it("팀이 200개를 넘으면 이어서 읽는다", async () => {
    const many = Array.from({ length: 201 }, (_, i) => ({ id: i + 1, code: `t${i}`, name: `팀${i}`, is_active: true }));
    const { calls } = setup({
      "GET /teams": (call) => {
        const offset = Number(call.query.get("offset"));
        return page(many.slice(offset, offset + 200), 201, 200, offset);
      },
    });
    await openS6();
    expect(calls.filter((c) => c.path === "/teams").map((c) => c.query.get("offset"))).toEqual(["0", "200"]);
  });
});

describe("S6 변경 요약 확인창 (저장 전 확인)", () => {
  it("칸을 바꿔도 확인 전에는 아무것도 호출하지 않고, 돌아가기를 누르면 호출 없이 닫는다", async () => {
    const { calls } = setup();
    await openS6();
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("소속 추가: 입력자 박 → 영업 (입력자)")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "돌아가기" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(writes(calls)).toEqual([]);
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
  });

  it("값을 원래대로 되돌리면 변경 목록에서 빠진다", async () => {
    setup();
    await openS6();
    fireEvent.change(cell("관리자 김", "영업"), { target: { value: "entry" } });
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
    fireEvent.change(cell("관리자 김", "영업"), { target: { value: "definer" } });
    expect(screen.getByText("변경 목록 (0건)")).toBeTruthy();
    expect((screen.getByRole("button", { name: "저장하기" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("여러 변경을 한 번에 요약하고 확인 뒤 정해진 순서와 본문으로 호출한다", async () => {
    const { calls } = setup({
      "POST /teams": () => json(201, { id: 30, code: "hr", name: "인사", is_active: true }),
      "POST /users": () => json(201, { ...USERS[2], id: 9 }),
      "PATCH /teams/10": () => json(200, TEAMS[0]),
      "PATCH /users/1": () => json(200, USERS[0]),
      "PATCH /users/2": () => json(200, USERS[1]),
      "PUT /teams/10/members/2": () => json(200, { team_id: 10, user_id: 2, role: "entry" }),
      "PUT /teams/10/members/1": () => json(200, { team_id: 10, user_id: 1, role: "entry" }),
      "DELETE /teams/20/members/2": () => noContent(),
    });
    await openS6();

    // 1) 팀 만들기
    const teamForm = screen.getByRole("form", { name: "팀 만들기" });
    fireEvent.change(within(teamForm).getByLabelText("팀 코드"), { target: { value: "hr" } });
    fireEvent.change(within(teamForm).getByLabelText("팀 이름"), { target: { value: " 인사 " } });
    fireEvent.click(within(teamForm).getByRole("button", { name: "변경 목록에 담기" }));
    // 2) 사용자 사전 등록
    const userForm = screen.getByRole("form", { name: "사용자 사전 등록" });
    fireEvent.change(within(userForm).getByLabelText("로그인 ID"), { target: { value: "new1" } });
    fireEvent.change(within(userForm).getByLabelText("표시 이름"), { target: { value: "신입 최" } });
    fireEvent.click(within(userForm).getByLabelText("관리자로 등록"));
    fireEvent.click(within(userForm).getByRole("button", { name: "변경 목록에 담기" }));
    // 3) 관리자 해제(관리자 김) - 가장 마지막에 호출돼야 한다
    fireEvent.click(screen.getByRole("button", { name: "관리자 김 수정" }));
    const editUser = screen.getByRole("form", { name: "사용자 수정: 관리자 김" });
    fireEvent.click(within(editUser).getByLabelText("관리자"));
    fireEvent.click(within(editUser).getByRole("button", { name: "변경 목록에 담기" }));
    // 4) 팀 이름 변경
    fireEvent.click(screen.getByRole("button", { name: "영업 수정" }));
    const editTeam = screen.getByRole("form", { name: "팀 수정: 영업" });
    fireEvent.change(within(editTeam).getByLabelText("팀 이름"), { target: { value: "영업1팀" } });
    fireEvent.click(within(editTeam).getByRole("button", { name: "변경 목록에 담기" }));
    // 5) 소속 해제, 역할 변경, 소속 추가
    fireEvent.change(cell("입력자 박", "운영"), { target: { value: "" } });
    fireEvent.change(cell("관리자 김", "영업"), { target: { value: "entry" } });
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });

    expect(screen.getByText("변경 목록 (7건)")).toBeTruthy();
    expect(writes(calls)).toEqual([]);

    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    const dialog = screen.getByRole("dialog");
    const items = within(dialog).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual([
      "팀 만들기: 인사 (코드 hr)",
      "사용자 사전 등록: 신입 최 (new1), 관리자",
      '팀 수정: 영업 - 이름을 "영업1팀"(으)로 변경',
      "역할 변경: 관리자 김 / 영업 (정의 담당자 → 입력자)",
      "소속 추가: 입력자 박 → 영업 (입력자)",
      "소속 해제: 입력자 박 ← 운영 (현재 입력자)",
      "사용자 수정: 관리자 김 - 관리자 권한 해제",
    ]);
    expect(writes(calls)).toEqual([]);

    fireEvent.click(within(dialog).getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(writes(calls)).toEqual([
      "POST /teams",
      "POST /users",
      "PATCH /teams/10",
      "PUT /teams/10/members/1",
      "PUT /teams/10/members/2",
      "DELETE /teams/20/members/2",
      "PATCH /users/1",
    ]);
    const byKey = (m: string, p: string) => calls.find((c) => c.method === m && c.path === p)!;
    expect(byKey("POST", "/teams").body).toEqual({ code: "hr", name: "인사" });
    expect(byKey("POST", "/users").body).toEqual({ login_id: "new1", display_name: "신입 최", is_admin: true });
    expect(byKey("PATCH", "/teams/10").body).toEqual({ name: "영업1팀" });
    expect(byKey("PUT", "/teams/10/members/1").body).toEqual({ role: "entry" });
    expect(byKey("PUT", "/teams/10/members/2").body).toEqual({ role: "entry" });
    expect(byKey("DELETE", "/teams/20/members/2").body).toBeUndefined();
    expect(byKey("PATCH", "/users/1").body).toEqual({ is_admin: false });

    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.getByText("7건을 저장했습니다.")).toBeTruthy();
    expect(screen.getByText("변경 목록 (0건)")).toBeTruthy();
    // 저장 뒤 목록을 다시 읽는다.
    expect(calls.filter((c) => c.path === "/users").length).toBeGreaterThanOrEqual(2);
  });

  it("사용자 수정은 바뀐 필드만 보낸다(비활성)", async () => {
    const { calls } = setup({ "PATCH /users/2": () => json(200, USERS[1]) });
    await openS6();
    fireEvent.click(screen.getByRole("button", { name: "입력자 박 수정" }));
    const form = screen.getByRole("form", { name: "사용자 수정: 입력자 박" });
    fireEvent.click(within(form).getByLabelText("사용 중"));
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    expect(within(screen.getByRole("dialog")).getByText("사용자 수정: 입력자 박 - 사용 중지(비활성)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_active: false });
  });

  it("팀 비활성도 같은 확인창을 거치고 is_active만 보낸다", async () => {
    const { calls } = setup({ "PATCH /teams/10": () => json(200, TEAMS[0]) });
    await openS6();
    fireEvent.click(screen.getByRole("button", { name: "영업 수정" }));
    const form = screen.getByRole("form", { name: "팀 수정: 영업" });
    fireEvent.click(within(form).getByLabelText("사용 중"));
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(writes(calls)).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(calls.find((c) => c.method === "PATCH")!.body).toEqual({ is_active: false });
  });

  it("LAST_ADMIN 409는 쉬운 문구로 알리고, 뒤 변경은 실행하지 않고, 실패분은 목록에 남긴다", async () => {
    const { calls } = setup({
      "PATCH /users/1": () => apiError(409, "LAST_ADMIN", "서버 내부 문구"),
      "PUT /teams/10/members/2": () => json(200, { team_id: 10, user_id: 2, role: "entry" }),
    });
    await openS6();
    fireEvent.click(screen.getByRole("button", { name: "관리자 김 수정" }));
    const form = screen.getByRole("form", { name: "사용자 수정: 관리자 김" });
    fireEvent.click(within(form).getByLabelText("관리자"));
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    // 소속 추가(권한을 거두지 않는 변경)가 먼저 성공하고, 관리자 해제가 마지막에 실패한다.
    expect(writes(calls)).toEqual(["PUT /teams/10/members/2", "PATCH /users/1"]);
    const alert = screen.getByRole("dialog").querySelector("[role=alert]")!;
    expect(alert.textContent).toContain("마지막 관리자");
    expect(alert.textContent).not.toContain("서버 내부 문구");
    fireEvent.click(screen.getByRole("button", { name: "닫기" }));
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
    expect(screen.queryByText(/건을 저장했습니다/)).toBeNull();
  });

  it("중간 실패 뒤 항목은 '실행 안 함'으로 표시한다", async () => {
    const { calls } = setup({
      "POST /teams": () => apiError(409, "ALREADY_EXISTS", "x", { field: "code" }),
    });
    await openS6();
    const teamForm = screen.getByRole("form", { name: "팀 만들기" });
    fireEvent.change(within(teamForm).getByLabelText("팀 코드"), { target: { value: "hr" } });
    fireEvent.change(within(teamForm).getByLabelText("팀 이름"), { target: { value: "인사" } });
    fireEvent.click(within(teamForm).getByRole("button", { name: "변경 목록에 담기" }));
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(writes(calls)).toEqual(["POST /teams"]);
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("실행 안 함")).toBeTruthy();
    expect(within(dialog).getByRole("alert").textContent).toContain("같은 코드의 팀이 이미 있습니다");
  });

  it("422 검증 오류는 필드별로 쉬운 문구를 보여 준다", async () => {
    setup({
      "POST /users": () =>
        apiError(422, "VALIDATION_ERROR", "x", { fields: [{ field: "display_name", code: "TOO_LONG", message: "x" }] }),
    });
    await openS6();
    const userForm = screen.getByRole("form", { name: "사용자 사전 등록" });
    fireEvent.change(within(userForm).getByLabelText("로그인 ID"), { target: { value: "a" } });
    fireEvent.change(within(userForm).getByLabelText("표시 이름"), { target: { value: "b" } });
    fireEvent.click(within(userForm).getByRole("button", { name: "변경 목록에 담기" }));
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(within(screen.getByRole("dialog")).getByRole("alert").textContent).toContain("표시 이름: 너무 깁니다");
  });

  it("Escape로 확인창을 닫을 수 있고 호출은 없다", async () => {
    const { calls } = setup();
    await openS6();
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(writes(calls)).toEqual([]);
  });

  it("빼기와 모두 취소로 변경 목록을 비울 수 있다", async () => {
    setup();
    await openS6();
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    fireEvent.change(cell("관리자 김", "영업"), { target: { value: "entry" } });
    fireEvent.click(screen.getByRole("button", { name: /^빼기: 소속 추가/ }));
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "모두 취소" }));
    expect(screen.getByText("변경 목록 (0건)")).toBeTruthy();
    expect(cell("관리자 김", "영업").value).toBe("definer");
  });
});

describe("S6 입력 검증", () => {
  it.each([["Sales"], ["영업"], ["a-b"], [""], ["a".repeat(33)]])("팀 코드 %j는 거부하고 목록에 담지 않는다", async (code) => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "팀 만들기" });
    fireEvent.change(within(form).getByLabelText("팀 코드"), { target: { value: code } });
    fireEvent.change(within(form).getByLabelText("팀 이름"), { target: { value: "영업" } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("영문 소문자");
    expect(screen.getByText("변경 목록 (0건)")).toBeTruthy();
  });

  it.each([["a"], ["sales_01"], ["a".repeat(32)], ["0_"]])("팀 코드 %j는 통과한다", async (code) => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "팀 만들기" });
    fireEvent.change(within(form).getByLabelText("팀 코드"), { target: { value: code } });
    fireEvent.change(within(form).getByLabelText("팀 이름"), { target: { value: "x" } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
  });

  it("팀 이름은 50자 입력 제한이 있고, 비어 있으면 거부한다", async () => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "팀 만들기" });
    expect((within(form).getByLabelText("팀 이름") as HTMLInputElement).maxLength).toBe(50);
    expect((within(form).getByLabelText("팀 코드") as HTMLInputElement).maxLength).toBe(32);
    fireEvent.change(within(form).getByLabelText("팀 코드"), { target: { value: "ok" } });
    fireEvent.change(within(form).getByLabelText("팀 이름"), { target: { value: "   " } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("1~50자");
  });

  it("이미 있는 팀 코드는 서버 호출 전에 알려 준다", async () => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "팀 만들기" });
    fireEvent.change(within(form).getByLabelText("팀 코드"), { target: { value: "sales" } });
    fireEvent.change(within(form).getByLabelText("팀 이름"), { target: { value: "다른" } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("이미 있");
  });

  it("사용자 등록은 로그인 ID와 표시 이름이 필수다", async () => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "사용자 사전 등록" });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("입력해 주세요");
  });
});

describe("S6 비활성 팀·사용자 칸 (03b 17-1 결정 3: 소속 추가·변경은 서버가 409)", () => {
  it("비활성 사용자 칸(소속 없음)과 비활성 팀 칸(소속 없음)은 컨트롤이 비활성이다", async () => {
    setup();
    await openS6();
    expect(cell("퇴사자 이", "영업").disabled).toBe(true);
    expect(cell("퇴사자 이", "운영").disabled).toBe(true);
    expect(cell("관리자 김", "운영").disabled).toBe(true);
    // 활성 사용자 x 활성 팀 칸은 그대로 쓸 수 있다.
    expect(cell("입력자 박", "영업").disabled).toBe(false);
    expect(cell("관리자 김", "영업").disabled).toBe(false);
  });

  it("이미 소속이 있는 비활성 팀 칸은 역할 변경·추가 선택이 막히고 소속 해제만 가능하다", async () => {
    const { calls } = setup({ "DELETE /teams/20/members/2": () => noContent() });
    await openS6();
    const select = cell("입력자 박", "운영");
    expect(select.disabled).toBe(false);
    const option = (name: string) => within(select).getByRole("option", { name }) as HTMLOptionElement;
    expect(option("정의 담당자").disabled).toBe(true);
    expect(option("입력자").disabled).toBe(false); // 현재 값
    expect(option("소속 없음").disabled).toBe(false);
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    expect(writes(calls)).toEqual(["DELETE /teams/20/members/2"]);
  });

  it("비활성 안내 문구를 격자 위에 보여 준다", async () => {
    setup();
    await openS6();
    expect(screen.getByTestId("inactive-guide").textContent).toContain("비활성 팀이나 사용자에게는 소속을 지정할 수 없습니다");
  });

  it("서버가 409 TARGET_INACTIVE를 주면 결과 창에 details.field별 문구를 보여 준다", async () => {
    setup({
      // 화면이 막아도 서버가 최종 방어선이다: 목록이 낡았을 때 오는 409를 그대로 문구로 보여 준다.
      "PUT /teams/10/members/2": () => apiError(409, "TARGET_INACTIVE", "서버 문구", { field: "team_id" }),
    });
    await openS6();
    fireEvent.change(cell("입력자 박", "영업"), { target: { value: "entry" } });
    fireEvent.click(screen.getByRole("button", { name: "저장하기" }));
    fireEvent.click(screen.getByRole("button", { name: "확인하고 저장" }));
    await screen.findByText("저장 결과");
    const alert = within(screen.getByRole("dialog")).getByRole("alert");
    expect(alert.textContent).toContain("비활성 팀");
    expect(alert.textContent).not.toContain("서버 문구");
  });
});

describe("S6 길이 상한 (05 §1: 사용자 표시 이름 100자, 로그인 ID 200자)", () => {
  it("사용자 등록 입력은 maxLength 200/100이다", async () => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "사용자 사전 등록" });
    expect((within(form).getByLabelText("로그인 ID") as HTMLInputElement).maxLength).toBe(200);
    expect((within(form).getByLabelText("표시 이름") as HTMLInputElement).maxLength).toBe(100);
  });

  it("사용자 수정의 표시 이름도 maxLength 100이다", async () => {
    setup();
    await openS6();
    fireEvent.click(screen.getByRole("button", { name: "입력자 박 수정" }));
    const form = screen.getByRole("form", { name: "사용자 수정: 입력자 박" });
    expect((within(form).getByLabelText("표시 이름") as HTMLInputElement).maxLength).toBe(100);
  });

  it("붙여넣기 등으로 한도를 넘긴 값은 제출 때 한 번 더 막는다", async () => {
    setup();
    await openS6();
    const form = screen.getByRole("form", { name: "사용자 사전 등록" });
    fireEvent.change(within(form).getByLabelText("로그인 ID"), { target: { value: "a".repeat(201) } });
    fireEvent.change(within(form).getByLabelText("표시 이름"), { target: { value: "이름" } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("200자");
    fireEvent.change(within(form).getByLabelText("로그인 ID"), { target: { value: "ok" } });
    fireEvent.change(within(form).getByLabelText("표시 이름"), { target: { value: "가".repeat(101) } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(within(form).getByRole("alert").textContent).toContain("100자");
    expect(screen.getByText("변경 목록 (0건)")).toBeTruthy();
    fireEvent.change(within(form).getByLabelText("표시 이름"), { target: { value: "가".repeat(100) } });
    fireEvent.click(within(form).getByRole("button", { name: "변경 목록에 담기" }));
    expect(screen.getByText("변경 목록 (1건)")).toBeTruthy();
  });
});
