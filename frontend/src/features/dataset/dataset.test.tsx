import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler } from "../../test-utils";
import { WORK_TEAM_STORAGE_KEY } from "../access/MeContext";
import { makeDetail, makeFakeWorkspace } from "./test-server";

const BASE = "/bi-wizard";

const TEAMS = [
  { id: 10, code: "sales", name: "영업", is_active: true },
  { id: 20, code: "ops", name: "운영", is_active: true },
  { id: 30, code: "old", name: "폐쇄팀", is_active: false },
];

const DATASETS = [
  {
    id: 7,
    team_id: 10,
    name: "월별 매출",
    date_unit: "month",
    base_date_column_id: null,
    status: "active",
    def_version: 3,
    created_by: { id: 1, display_name: "관리자 김" },
    created_at: "2026-10-12T09:30:00+09:00",
  },
  {
    id: 8,
    team_id: 20,
    name: "일별 가동",
    date_unit: "day",
    base_date_column_id: null,
    status: "active",
    def_version: 1,
    created_by: { id: 2, display_name: "입력자 박" },
    created_at: "2026-09-01T00:10:00+09:00",
  },
];

const page = <T,>(items: T[], total = items.length, limit = 50, offset = 0) => json(200, { items, total, limit, offset });

function setup(me: unknown = ADMIN_ME, extra: Record<string, Handler> = {}) {
  return installFetch({
    ...HEALTH_HANDLERS,
    "GET /me": () => json(200, me),
    "GET /teams": () => page(TEAMS, TEAMS.length, 200),
    "GET /datasets": () => page(DATASETS),
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

const open = (path: string) => render(<App router={createTestRouter(BASE, `${BASE}${path}`)} />);
const openList = async () => {
  open("/datasets");
  await screen.findByRole("table", { name: "데이터셋 목록" });
};

describe("S2 데이터셋 목록 (B1)", () => {
  it("이름·팀·날짜 단위·생성자·생성일을 서버가 준 순서 그대로 보여 준다", async () => {
    const { calls } = setup();
    await openList();
    const table = screen.getByRole("table", { name: "데이터셋 목록" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["이름", "팀", "날짜 단위", "생성자", "생성일"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["월별 매출", "영업", "월", "관리자 김", "2026-10-12"],
      ["일별 가동", "운영", "일", "입력자 박", "2026-09-01"],
    ]);
    expect(within(table).getByRole("link", { name: "월별 매출" }).getAttribute("href")).toBe(`${BASE}/datasets/7`);
    const call = calls.find((c) => c.path === "/datasets")!;
    expect(call.query.get("limit")).toBe("50");
    expect(call.query.get("offset")).toBe("0");
    expect(call.query.has("team_id")).toBe(false);
  });

  it("동기 상태 열은 없고, 1e 전이라 /superset/datasets를 부르지 않는다", async () => {
    const { calls } = setup();
    await openList();
    expect(screen.queryByRole("columnheader", { name: /동기/ })).toBeNull();
    expect(screen.queryByText("준비 중")).toBeNull();
    expect(calls.some((c) => c.path.startsWith("/superset"))).toBe(false);
  });

  it("팀 필터를 고르면 team_id로 다시 읽고, '전체 팀'이면 team_id를 보내지 않는다", async () => {
    const { calls } = setup(ADMIN_ME, {
      "GET /datasets": (call) => (call.query.get("team_id") === "20" ? page([DATASETS[1]]) : page(DATASETS)),
    });
    await openList();
    const select = screen.getByLabelText("팀 필터") as HTMLSelectElement;
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["전체 팀", "영업", "운영", "폐쇄팀"]);
    fireEvent.change(select, { target: { value: "20" } });
    await waitFor(() => expect(screen.queryByText("월별 매출")).toBeNull());
    expect(screen.getByText("일별 가동")).toBeTruthy();
    const last = calls.filter((c) => c.path === "/datasets").at(-1)!;
    expect(last.query.get("team_id")).toBe("20");
    expect(last.query.get("offset")).toBe("0");
    fireEvent.change(select, { target: { value: "" } });
    await screen.findByText("월별 매출");
    expect(calls.filter((c) => c.path === "/datasets").at(-1)!.query.has("team_id")).toBe(false);
  });

  it("limit/offset 쪽 이동, 필터를 바꾸면 처음 쪽으로 돌아간다", async () => {
    const { calls } = setup(ADMIN_ME, { "GET /datasets": () => page(DATASETS, 120) });
    await openList();
    expect(screen.getByText(/전체 120개 중 1–50/)).toBeTruthy();
    expect((screen.getByRole("button", { name: "이전" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await screen.findByText(/전체 120개 중 51–100/);
    expect(calls.filter((c) => c.path === "/datasets").at(-1)!.query.get("offset")).toBe("50");
    fireEvent.change(screen.getByLabelText("팀 필터"), { target: { value: "10" } });
    await screen.findByText(/전체 120개 중 1–50/);
    expect(calls.filter((c) => c.path === "/datasets").at(-1)!.query.get("offset")).toBe("0");
  });

  it("비어 있으면 안내, 불러오기 실패는 쉬운 문구와 다시 불러오기", async () => {
    setup(ADMIN_ME, { "GET /datasets": () => page([]) });
    open("/datasets");
    expect(await screen.findByTestId("no-datasets")).toBeTruthy();
    cleanup();
    let fail = true;
    setup(ADMIN_ME, { "GET /datasets": () => (fail ? apiError(500, "INTERNAL_ERROR") : page(DATASETS)) });
    open("/datasets");
    expect((await screen.findByRole("alert")).textContent).toContain("예기치 않은 오류");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("월별 매출")).toBeTruthy();
  });

  it("503 SERVICE_UNAVAILABLE는 일시 장애 문구", async () => {
    setup(ADMIN_ME, { "GET /datasets": () => apiError(503, "SERVICE_UNAVAILABLE") });
    open("/datasets");
    expect((await screen.findByRole("alert")).textContent).toContain("일시적으로 응답하지 못합니다");
  });
});

describe("S2 '새 데이터셋' 버튼은 작업 팀에서 정의 담당자일 때만", () => {
  it("작업 팀(영업)에서 definer이면 보인다", async () => {
    setup();
    await openList();
    expect(screen.getByRole("link", { name: "새 데이터셋" }).getAttribute("href")).toBe(`${BASE}/datasets/new`);
  });

  it("작업 팀을 입력자 역할 팀(운영)으로 바꾸면 사라진다", async () => {
    window.sessionStorage.setItem(WORK_TEAM_STORAGE_KEY, "20");
    setup();
    await openList();
    expect(screen.queryByRole("link", { name: "새 데이터셋" })).toBeNull();
    expect(screen.getByTestId("define-hint").textContent).toContain("정의 담당자");
  });

  it("소속이 입력자뿐이거나 소속이 없으면 없다(열람은 가능)", async () => {
    setup(MEMBER_ME);
    await openList();
    expect(screen.queryByRole("link", { name: "새 데이터셋" })).toBeNull();
    cleanup();
    setup({ ...MEMBER_ME, memberships: [] });
    await openList();
    expect(screen.queryByRole("link", { name: "새 데이터셋" })).toBeNull();
  });

  it("작업 팀이 비활성이면 정의 담당자여도 없다", async () => {
    setup({
      ...ADMIN_ME,
      memberships: [{ team_id: 10, team_code: "sales", team_name: "영업", team_is_active: false, role: "definer" }],
    });
    await openList();
    expect(screen.queryByRole("link", { name: "새 데이터셋" })).toBeNull();
  });
});

describe("S3 데이터셋 만들기 (B2)", () => {
  const openForm = async (me: unknown = ADMIN_ME, extra: Record<string, Handler> = {}) => {
    const result = setup(me, extra);
    open("/datasets/new");
    await screen.findByRole("form", { name: "데이터셋 만들기" });
    return result;
  };

  it("팀 선택에는 정의 담당자인 활성 팀만 나오고 작업 팀이 기본이다", async () => {
    await openForm({
      ...ADMIN_ME,
      memberships: [
        { team_id: 10, team_code: "sales", team_name: "영업", team_is_active: true, role: "definer" },
        { team_id: 20, team_code: "ops", team_name: "운영", team_is_active: true, role: "entry" },
        { team_id: 30, team_code: "old", team_name: "폐쇄팀", team_is_active: false, role: "definer" },
        { team_id: 40, team_code: "hr", team_name: "인사", team_is_active: true, role: "definer" },
      ],
    });
    const select = screen.getByLabelText("팀") as HTMLSelectElement;
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["영업", "인사"]);
    expect(select.value).toBe("10");
  });

  it("작업 팀이 입력자 역할이면 기본은 첫 정의 담당 팀", async () => {
    window.sessionStorage.setItem(WORK_TEAM_STORAGE_KEY, "20");
    await openForm({
      ...ADMIN_ME,
      memberships: [
        { team_id: 20, team_code: "ops", team_name: "운영", team_is_active: true, role: "entry" },
        { team_id: 40, team_code: "hr", team_name: "인사", team_is_active: true, role: "definer" },
      ],
    });
    expect((screen.getByLabelText("팀") as HTMLSelectElement).value).toBe("40");
  });

  it("정의 담당자인 팀이 없으면 안내만 보이고 폼은 없다", async () => {
    setup(MEMBER_ME);
    open("/datasets/new");
    expect(await screen.findByTestId("no-definer-team")).toBeTruthy();
    expect(screen.queryByRole("form", { name: "데이터셋 만들기" })).toBeNull();
  });

  it("날짜 단위는 일·월·연 중 하나이고 이름은 100자 제한이 있다", async () => {
    await openForm();
    const unit = screen.getByLabelText("날짜 단위") as HTMLSelectElement;
    expect(within(unit).getAllByRole("option").map((o) => [o.textContent, (o as HTMLOptionElement).value])).toEqual([
      ["일", "day"],
      ["월", "month"],
      ["연", "year"],
    ]);
    expect((screen.getByLabelText("이름") as HTMLInputElement).maxLength).toBe(100);
  });

  it("이름이 비어 있거나 100자를 넘으면 호출 없이 거부한다", async () => {
    const { calls } = await openForm();
    const form = screen.getByRole("form", { name: "데이터셋 만들기" });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(within(form).getByRole("alert").textContent).toContain("이름을 입력");
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "가".repeat(101) } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(within(form).getByRole("alert").textContent).toContain("100자");
    expect(calls.filter((c) => c.method === "POST")).toEqual([]);
  });

  it("만들면 POST 본문(team_id·name·date_unit)을 보내고 작업공간으로 이동한다", async () => {
    const created = makeDetail({ id: 55, name: "새 표", date_unit: "year", def_version: 1 });
    const fake = makeFakeWorkspace(created);
    const { calls } = await openForm(ADMIN_ME, {
      ...fake.handlers,
      "POST /datasets": () => json(201, created),
    });
    const form = screen.getByRole("form", { name: "데이터셋 만들기" });
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "  새 표  " } });
    fireEvent.change(within(form).getByLabelText("날짜 단위"), { target: { value: "year" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect(await screen.findByTestId("screen-S4")).toBeTruthy();
    expect(await screen.findByRole("heading", { level: 1, name: /새 표/ })).toBeTruthy();
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.path).toBe("/datasets");
    expect(post.body).toEqual({ team_id: 10, name: "새 표", date_unit: "year" });
    expect(calls.some((c) => c.method === "GET" && c.path === "/datasets/55")).toBe(true);
  });

  it("같은 팀에 같은 이름이 있으면(409) 쉬운 문구, 폼은 그대로 남는다", async () => {
    await openForm(ADMIN_ME, { "POST /datasets": () => apiError(409, "ALREADY_EXISTS", "서버 문구", { field: "name" }) });
    const form = screen.getByRole("form", { name: "데이터셋 만들기" });
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "월별 매출" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect((await within(form).findByRole("alert")).textContent).toContain("같은 이름");
    expect((within(form).getByLabelText("이름") as HTMLInputElement).value).toBe("월별 매출");
    expect(screen.queryByTestId("screen-S4")).toBeNull();
  });

  it("비활성 팀이라는 409 TARGET_INACTIVE(field=team)는 데이터셋 생성 불가 문구", async () => {
    await openForm(ADMIN_ME, { "POST /datasets": () => apiError(409, "TARGET_INACTIVE", "서버 문구", { field: "team" }) });
    const form = screen.getByRole("form", { name: "데이터셋 만들기" });
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "x" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    const alert = await within(form).findByRole("alert");
    expect(alert.textContent).toContain("비활성 팀에는 데이터셋을 만들 수 없습니다");
    expect(alert.textContent).not.toContain("소속");
  });

  it.each([
    [403, "FORBIDDEN", "권한이 없습니다"],
    [503, "DEFINITION_BUSY", "잠시 뒤"],
    [422, "VALIDATION_ERROR", "입력한 내용을 확인"],
  ])("%i %s는 쉬운 문구로 알린다", async (status, code, text) => {
    await openForm(ADMIN_ME, { "POST /datasets": () => apiError(status, code) });
    const form = screen.getByRole("form", { name: "데이터셋 만들기" });
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "x" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    expect((await within(form).findByRole("alert")).textContent).toContain(text);
  });
});
