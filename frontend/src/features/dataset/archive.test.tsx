import type { GridApi } from "ag-grid-community";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { describeApiError } from "../../errors";
import { ApiError } from "../../api";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import { EntryGrid } from "../entry/EntryGrid";
import type { GridRow } from "../entry/model";
import { SALES_ROWS, makeFakeRows, salesDetail } from "../entry/test-server";
import { sortColumns } from "./api";
import { ARCHIVE_CONFIRM_TEXT, ARCHIVE_LIMIT_TEXT, RESTORE_CONFIRM_TEXT } from "./ArchiveAction";
import { makeDetail } from "./test-server";
import type { Dataset, DatasetDetail } from "./types";

/**
 * FU-2b 데이터셋 보관·복구 화면 시험. 05 계약(B1 status, B7·B8, DATASET_ARCHIVED)대로 답하는 모의 fetch를 쓴다.
 * 실제 백엔드를 부르지 않으므로 서버와의 일치는 이 시험이 보증하지 않는다(통합 시험·스크린샷 단계에서 확인).
 */
const BASE = "/bi-wizard";

const TEAMS = [
  { id: 10, code: "sales", name: "영업", is_active: true },
  { id: 20, code: "ops", name: "운영", is_active: true },
  { id: 30, code: "old", name: "폐쇄팀", is_active: false },
];

const mk = (id: number, team_id: number, name: string, status: Dataset["status"]): Dataset => ({
  id,
  team_id,
  name,
  date_unit: "month",
  base_date_column_id: null,
  status,
  def_version: 1,
  created_by: { id: 1, display_name: "관리자 김" },
  created_at: "2026-10-12T09:30:00+09:00",
});

// 영업(10, 내가 정의 담당자) 사용 중 / 영업 보관 / 운영(20, 내가 입력자) 사용 중 / 폐쇄팀(30, 비활성, 내가 정의 담당자) 보관
const ALL = [mk(7, 10, "월별 매출", "active"), mk(9, 10, "작년 매출", "archived"), mk(8, 20, "일별 가동", "active"), mk(11, 30, "옛 데이터", "archived")];
const ME_WITH_CLOSED_TEAM = {
  ...ADMIN_ME,
  memberships: [...ADMIN_ME.memberships, { team_id: 30, team_code: "old", team_name: "폐쇄팀", team_is_active: false, role: "definer" }],
};

const page = <T,>(items: T[]) => json(200, { items, total: items.length, limit: 50, offset: 0 });

function listHandler(): Handler {
  return (call) => {
    const status = call.query.get("status") ?? "active";
    return page(ALL.filter((d) => status === "all" || d.status === status));
  };
}

function setup(me: unknown = ADMIN_ME, extra: Record<string, Handler> = {}) {
  return installFetch({
    ...HEALTH_HANDLERS,
    "GET /me": () => json(200, me),
    "GET /teams": () => page(TEAMS),
    "GET /datasets": listHandler(),
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
const listCalls = (calls: RecordedCall[]) => calls.filter((c) => c.method === "GET" && c.path === "/datasets");
const confirmDialog = () => screen.getByRole("dialog");
const postCalls = (calls: RecordedCall[]) => calls.filter((c) => c.method === "POST");

describe("S2 보기 선택과 배지", () => {
  it("기본은 '사용 중'이고 status=active로 읽는다. 보기를 바꾸면 status를 바꿔 다시 읽는다", async () => {
    const { calls } = setup();
    await openList();
    const select = screen.getByLabelText("보기") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["사용 중", "보관됨", "전체"]);
    expect(select.value).toBe("active");
    expect(listCalls(calls).at(-1)!.query.get("status")).toBe("active");
    expect(screen.queryByText("작년 매출")).toBeNull();

    fireEvent.change(select, { target: { value: "archived" } });
    await waitFor(() => expect(screen.getByText("작년 매출")).toBeTruthy());
    expect(listCalls(calls).at(-1)!.query.get("status")).toBe("archived");
    expect(listCalls(calls).at(-1)!.query.get("offset")).toBe("0");
    expect(screen.queryByText("월별 매출")).toBeNull();

    fireEvent.change(select, { target: { value: "all" } });
    await waitFor(() => expect(screen.getByText("월별 매출")).toBeTruthy());
    expect(listCalls(calls).at(-1)!.query.get("status")).toBe("all");
    expect(screen.getByText("작년 매출")).toBeTruthy();
  });

  it("보관 행에만 '보관' 배지가 붙는다", async () => {
    setup();
    await openList();
    fireEvent.change(screen.getByLabelText("보기"), { target: { value: "all" } });
    await waitFor(() => expect(screen.getByText("작년 매출")).toBeTruthy());
    const rows = within(screen.getByRole("table", { name: "데이터셋 목록" })).getAllByRole("row").slice(1);
    const badge = (name: string) => within(rows.find((r) => r.textContent?.includes(name))!).queryByText("보관", { selector: ".badge" });
    expect(badge("작년 매출")).toBeTruthy();
    expect(badge("월별 매출")).toBeNull();
    expect(badge("일별 가동")).toBeNull();
  });

  it("보관된 데이터셋이 없으면 안내 문구", async () => {
    setup(ADMIN_ME, { "GET /datasets": (call) => page(call.query.get("status") === "archived" ? [] : ALL.slice(0, 1)) });
    await openList();
    fireEvent.change(screen.getByLabelText("보기"), { target: { value: "archived" } });
    expect((await screen.findByTestId("no-datasets")).textContent).toBe("보관된 데이터셋이 없습니다.");
  });
});

describe("S2 보관·복구 버튼 노출", () => {
  it("그 팀의 정의 담당자에게만 보인다: 사용 중 행은 '보관', 보관 행은 '복구'(입력자인 팀 행에는 없다)", async () => {
    setup();
    await openList();
    fireEvent.change(screen.getByLabelText("보기"), { target: { value: "all" } });
    await waitFor(() => expect(screen.getByText("작년 매출")).toBeTruthy());
    expect(screen.getByRole("button", { name: "월별 매출 보관" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "작년 매출 복구" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /일별 가동/ })).toBeNull();
    // 비활성 팀 소유여도 정의 담당자면 표시한다.
  });

  it("비활성 팀 소유 데이터셋도 그 팀 정의 담당자에게는 '복구'가 보인다", async () => {
    setup(ME_WITH_CLOSED_TEAM);
    await openList();
    fireEvent.change(screen.getByLabelText("보기"), { target: { value: "archived" } });
    expect(await screen.findByRole("button", { name: "옛 데이터 복구" })).toBeTruthy();
  });

  it("입력자·소속 없는 관리자에게는 버튼도 '관리' 열도 없다", async () => {
    for (const me of [MEMBER_ME, { ...ADMIN_ME, memberships: [] }]) {
      setup(me);
      await openList();
      fireEvent.change(screen.getByLabelText("보기"), { target: { value: "all" } });
      await waitFor(() => expect(screen.getByText("작년 매출")).toBeTruthy());
      expect(screen.queryByRole("button", { name: /보관$|복구$/ })).toBeNull();
      expect(screen.queryByRole("columnheader", { name: "관리" })).toBeNull();
      cleanup();
    }
  });
});

describe("S2 확인창", () => {
  const archiveHandler = (record: { calls: number }): Handler => () => {
    record.calls += 1;
    return json(200, { ...makeDetail({ id: 7, status: "archived" }) });
  };

  it("보관 확인창은 뜻과 한계를 쉬운 말로 적고, 취소하면 아무것도 보내지 않는다", async () => {
    const record = { calls: 0 };
    const { calls } = setup(ADMIN_ME, { "POST /datasets/7/archive": archiveHandler(record) });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "월별 매출 보관" }));
    const dialog = confirmDialog();
    expect(within(dialog).getByRole("heading").textContent).toContain("월별 매출");
    const text = dialog.textContent ?? "";
    expect(text).toContain("입력과 정의 변경이 멈추고 포털 목록에서 숨겨집니다.");
    expect(text).toContain("Superset 차트와 읽기 전용 데이터로는 계속 보입니다.");
    expect(text).toContain("데이터를 아예 감추려면 영구 삭제가 따로 필요합니다(아직 없음).");
    expect(text).toContain(ARCHIVE_CONFIRM_TEXT);
    expect(text).toContain(ARCHIVE_LIMIT_TEXT);
    // 이름 입력 칸이 없는 단순 확인창이다.
    expect(within(dialog).queryByRole("textbox")).toBeNull();
    fireEvent.click(within(dialog).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(postCalls(calls)).toHaveLength(0);
  });

  it("보관 확인: B7을 본문 없이 부르고 목록을 다시 읽고 안내한다", async () => {
    const record = { calls: 0 };
    const { calls } = setup(ADMIN_ME, { "POST /datasets/7/archive": archiveHandler(record) });
    await openList();
    const before = listCalls(calls).length;
    fireEvent.click(screen.getByRole("button", { name: "월별 매출 보관" }));
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "보관하기" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(postCalls(calls)).toHaveLength(1);
    expect(postCalls(calls)[0].body).toBeUndefined();
    await waitFor(() => expect(listCalls(calls).length).toBe(before + 1));
    expect(screen.getByTestId("archive-notice").textContent).toContain("월별 매출");
    expect(screen.getByTestId("archive-notice").textContent).toContain("보관했습니다");
  });

  it("복구 확인창은 짧은 한 줄이고, 확인하면 B8을 부른다", async () => {
    const { calls } = setup(ADMIN_ME, { "POST /datasets/9/restore": () => json(200, makeDetail({ id: 9, status: "active" })) });
    await openList();
    fireEvent.change(screen.getByLabelText("보기"), { target: { value: "archived" } });
    fireEvent.click(await screen.findByRole("button", { name: "작년 매출 복구" }));
    const dialog = confirmDialog();
    expect(dialog.textContent).toContain(RESTORE_CONFIRM_TEXT);
    expect(dialog.textContent).not.toContain("영구 삭제");
    fireEvent.click(within(dialog).getByRole("button", { name: "복구하기" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(postCalls(calls).map((c) => c.path)).toEqual(["/datasets/9/restore"]);
    expect(screen.getByTestId("archive-notice").textContent).toContain("복구했습니다");
  });

  it("503 DEFINITION_BUSY: 창을 닫지 않고 '다시 시도' 안내, 다시 누르면 성공한다", async () => {
    let n = 0;
    setup(ADMIN_ME, {
      "POST /datasets/7/archive": () => (++n === 1 ? apiError(503, "DEFINITION_BUSY", "서버 문구", { retry_after: 2 }) : json(200, makeDetail({ id: 7, status: "archived" }))),
    });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "월별 매출 보관" }));
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "보관하기" }));
    const alert = await within(confirmDialog()).findByRole("alert");
    expect(alert.textContent).toContain("다른 작업이 진행 중입니다");
    expect(alert.textContent).toContain("다시 시도");
    const retry = within(confirmDialog()).getByRole("button", { name: "다시 시도" });
    fireEvent.click(retry);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(n).toBe(2);
  });

  it("403: 정의 담당자만 할 수 있다는 권한 안내", async () => {
    setup(ADMIN_ME, { "POST /datasets/7/archive": () => apiError(403, "FORBIDDEN") });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "월별 매출 보관" }));
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "보관하기" }));
    expect((await within(confirmDialog()).findByRole("alert")).textContent).toBe("정의 담당자만 할 수 있습니다.");
  });

  it("이미 보관된 데이터셋에 대한 보관(200)도 성공으로 본다(멱등)", async () => {
    setup(ADMIN_ME, { "POST /datasets/7/archive": () => json(200, makeDetail({ id: 7, status: "archived" })) });
    await openList();
    fireEvent.click(screen.getByRole("button", { name: "월별 매출 보관" }));
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "보관하기" }));
    await waitFor(() => expect(screen.getByTestId("archive-notice")).toBeTruthy());
  });
});

describe("오류 문구", () => {
  const err = (status: number, code: string, message: string, details: unknown = null) =>
    new ApiError(status, { code, message, details, request_id: "r" });

  it("DATASET_ARCHIVED는 복구 안내 문구", () => {
    expect(describeApiError(err(409, "DATASET_ARCHIVED", "서버 문구", { status: "archived" }))).toBe("보관된 데이터셋은 고칠 수 없습니다. 복구한 뒤 다시 시도하세요.");
  });

  it("이름 충돌: 충돌 상대가 보관이면 서버 메시지를 그대로, 아니면 기존 문구", () => {
    const archived = "같은 이름의 데이터셋이 이미 있습니다(보관된 데이터셋과 같은 이름). 다른 이름을 쓰거나 복구하세요.";
    expect(describeApiError(err(409, "ALREADY_EXISTS", archived, { field: "name" }))).toBe(archived);
    expect(describeApiError(err(409, "ALREADY_EXISTS", "서버 문구", { field: "name" }))).toBe("같은 이름이 이미 있습니다.");
  });

  it("S3 만들기에서 보관된 데이터셋과 이름이 겹치면 폼에 서버 메시지가 보인다", async () => {
    const message = "같은 이름의 데이터셋이 있습니다(보관된 데이터셋과 같은 이름).";
    setup(ADMIN_ME, { "POST /datasets": () => apiError(409, "ALREADY_EXISTS", message, { field: "name" }) });
    open("/datasets/new");
    const form = await screen.findByRole("form", { name: "데이터셋 만들기" });
    fireEvent.change(within(form).getByLabelText("이름"), { target: { value: "작년 매출" } });
    fireEvent.click(within(form).getByRole("button", { name: "만들기" }));
    const alert = await within(form).findByRole("alert");
    expect(alert.textContent).toContain("보관된 데이터셋과 같은 이름");
  });
});

/* ---------------- S4 작업공간 ---------------- */

async function openWorkspace(detail: DatasetDetail, extra: Record<string, Handler> = {}, me: unknown = ADMIN_ME) {
  const fake = makeFakeRows(detail, SALES_ROWS);
  const { calls } = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, me), ...fake.handlers, ...extra });
  render(<App router={createTestRouter(BASE, `${BASE}/datasets/${detail.id}`)} />);
  await screen.findByRole("region", { name: "데이터셋 정보" });
  return { fake, calls };
}
const inspector = () => screen.getByRole("complementary", { name: "Inspector" });

const archivedDetail = (patch: Partial<DatasetDetail> = {}) => salesDetail({ status: "archived", ...patch });

describe("S4 보관된 데이터셋 읽기 전용", () => {
  it("배너와 편집 비활성: 열/계산 열 추가, 데이터셋 설정, 열 수정, 그리드 입력이 막힌다", async () => {
    await openWorkspace(archivedDetail());
    const banner = screen.getByTestId("archived-banner");
    expect(banner.textContent).toContain("보관된 데이터셋입니다. 입력과 정의 변경이 멈춰 있습니다. 복구하면 다시 고칠 수 있습니다.");
    expect(within(banner).getByRole("button", { name: /복구/ })).toBeTruthy();
    expect((screen.getByRole("button", { name: "열 추가" }) as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("button", { name: "계산 열 추가" }) as HTMLButtonElement).disabled).toBe(true);
    // 데이터셋 설정: 입력칸 비활성, 저장 버튼 비활성
    const settings = within(inspector()).getByRole("form", { name: "데이터셋 설정" });
    expect((within(settings).getByLabelText("이름") as HTMLInputElement).disabled).toBe(true);
    expect((within(settings).getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    // 열 수정
    fireEvent.click(within(screen.getByRole("region", { name: "열 목록" })).getByRole("button", { name: /^매출/ }));
    const form = within(inspector()).getByRole("form", { name: /열 수정: 매출/ });
    expect((within(form).getByLabelText("열 이름") as HTMLInputElement).disabled).toBe(true);
    expect((within(form).getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
    // 그리드: 새 행 입력 줄·새 행 추가 버튼이 없고 읽기 전용 안내가 보관 사유를 말한다.
    await screen.findByRole("group", { name: "입력 그리드 표" });
    expect(screen.queryByRole("button", { name: "새 행 추가" })).toBeNull();
    expect(screen.getByRole("note").textContent).toContain("보관된 데이터셋");
  });

  it("사용 중인 데이터셋에는 배너가 없고 편집이 가능하다", async () => {
    await openWorkspace(salesDetail());
    expect(screen.queryByTestId("archived-banner")).toBeNull();
    expect((screen.getByRole("button", { name: "열 추가" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("정의 담당자가 아니면 배너에 복구 버튼이 없다(권한은 permissions 그대로)", async () => {
    await openWorkspace(archivedDetail({ permissions: { define: false, enter: true } }), {}, MEMBER_ME);
    const banner = screen.getByTestId("archived-banner");
    expect(within(banner).queryByRole("button")).toBeNull();
    expect(banner.textContent).toContain("정의 담당자만");
  });

  it("수식 보기·검사·미리보기는 쓸 수 있고 저장만 막힌다", async () => {
    const detail = archivedDetail({ columns: [...salesDetail().columns] });
    const formulaView = { column_id: 5, text: "[매출] * 2", refs: [], tag_columns: [], error_count: 0, result_type: "number" };
    await openWorkspace(detail, {
      "GET /datasets/7/formulas/5": () => json(200, formulaView),
      "POST /datasets/7/formulas/check": () => json(200, { ok: true, result_type: "number", errors: [] }),
    });
    fireEvent.click(within(screen.getByRole("region", { name: "열 목록" })).getByRole("button", { name: /^합계/ }));
    await screen.findByTestId("formula-text");
    fireEvent.click(await screen.findByRole("button", { name: "수식 고치기" }));
    const editor = await screen.findByRole("form", { name: /수식 고치기/ });
    expect(within(editor).getByTestId("save-blocked").textContent).toContain("보관된 데이터셋이라 저장할 수 없습니다");
    expect((within(editor).getByRole("button", { name: "수식 저장" }) as HTMLButtonElement).disabled).toBe(true);
    expect((within(editor).getByRole("button", { name: "미리보기" }) as HTMLButtonElement).disabled).toBe(false); // 검사·미리보기는 보관 중에도 쓴다
  });

  it("복구 버튼: B8 후 배너가 사라지고 편집이 다시 가능하다", async () => {
    const detail = archivedDetail();
    const { fake, calls } = await openWorkspace(detail, {
      "POST /datasets/7/restore": () => {
        fake.detail.status = "active";
        return json(200, fake.detail);
      },
    });
    fireEvent.click(within(screen.getByTestId("archived-banner")).getByRole("button", { name: /복구/ }));
    expect(confirmDialog().textContent).toContain(RESTORE_CONFIRM_TEXT);
    fireEvent.click(within(confirmDialog()).getByRole("button", { name: "복구하기" }));
    await waitFor(() => expect(screen.queryByTestId("archived-banner")).toBeNull());
    expect(postCalls(calls).map((c) => c.path)).toEqual(["/datasets/7/restore"]);
    expect((screen.getByRole("button", { name: "열 추가" }) as HTMLButtonElement).disabled).toBe(false);
    expect(within(inspector()).getByRole("status").textContent).toContain("복구했습니다");
  });
});

describe("저장 중 409 DATASET_ARCHIVED (열려 있던 화면)", () => {
  it("열 추가 저장이 거부되면 안내를 보이고 같은 배너로 바꾸며 상세를 다시 읽는다", async () => {
    const fake = makeFakeRows(salesDetail(), SALES_ROWS);
    const { calls } = installFetch({
      ...HEALTH_HANDLERS,
      "GET /me": () => json(200, ADMIN_ME),
      ...fake.handlers,
      "POST /datasets/7/columns": () => {
        fake.detail.status = "archived"; // 다른 사람이 방금 보관했다
        return apiError(409, "DATASET_ARCHIVED", "서버 문구", { status: "archived" });
      },
    });
    render(<App router={createTestRouter(BASE, `${BASE}/datasets/7`)} />);
    await screen.findByRole("region", { name: "데이터셋 정보" });
    expect(screen.queryByTestId("archived-banner")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "열 추가" }));
    const form = within(inspector()).getByRole("form", { name: "열 추가" });
    fireEvent.change(within(form).getByLabelText("열 이름"), { target: { value: "비고" } });
    const before = calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length;
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await screen.findByTestId("archived-banner");
    expect(within(inspector()).getByRole("alert").textContent).toContain("보관된 데이터셋은 고칠 수 없습니다");
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length).toBeGreaterThan(before));
    expect((screen.getByRole("button", { name: "열 추가" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("재조회가 실패해도 읽기 전용 전환은 유지된다", async () => {
    const fake = makeFakeRows(salesDetail(), SALES_ROWS);
    let reads = 0;
    installFetch({
      ...HEALTH_HANDLERS,
      "GET /me": () => json(200, ADMIN_ME),
      ...fake.handlers,
      "GET /datasets/7": () => (++reads === 1 ? json(200, fake.detail) : apiError(503, "SERVICE_UNAVAILABLE")),
      "PATCH /datasets/7": () => apiError(409, "DATASET_ARCHIVED", "서버 문구", { status: "archived" }),
    });
    render(<App router={createTestRouter(BASE, `${BASE}/datasets/7`)} />);
    await screen.findByRole("region", { name: "데이터셋 정보" });
    const settings = within(inspector()).getByRole("form", { name: "데이터셋 설정" });
    fireEvent.change(within(settings).getByLabelText("이름"), { target: { value: "새 이름" } });
    fireEvent.click(within(settings).getByRole("button", { name: "저장" }));
    await screen.findByTestId("archived-banner");
  });
});

describe("입력 그리드: 붙여넣기 중 DATASET_ARCHIVED", () => {
  it("붙여넣기 결과에 안내를 보이고 onArchived를 부른다", async () => {
    const detail = salesDetail();
    const fake = makeFakeRows(detail, SALES_ROWS);
    installFetch({
      ...HEALTH_HANDLERS,
      ...fake.handlers,
      "POST /datasets/7/rows/paste": () => apiError(409, "DATASET_ARCHIVED", "서버 문구", { status: "archived" }),
    });
    const onArchived = vi.fn();
    const holder: { api: GridApi<GridRow> | null } = { api: null };
    render(
      <EntryGrid
        datasetId={7}
        columns={sortColumns(detail.columns)}
        baseDateColumnId={detail.base_date_column_id}
        canEnter
        selectedColumnId={null}
        onSelectColumn={() => undefined}
        getVersion={() => 3}
        onVersion={() => undefined}
        onDefinitionStale={async () => undefined}
        onArchived={onArchived}
        onGridApi={(api) => {
          holder.api = api;
        }}
      />,
    );
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(grid.querySelector('[row-id^="r"]')).toBeTruthy());
    act(() => holder.api!.setFocusedCell(1, "2"));
    fireEvent.paste(grid, { clipboardData: { getData: (type: string) => (type === "text/plain" ? "10.5" : "") } });
    fireEvent.click(within(screen.getByRole("dialog", { name: "붙여넣기 확인" })).getByRole("button", { name: "붙여넣기 적용" }));
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    await waitFor(() => expect(result.textContent).toContain("보관된 데이터셋은 고칠 수 없습니다"));
    expect(result.textContent).toContain("저장되지 않았습니다");
    expect(onArchived).toHaveBeenCalledTimes(1);
  });

  it("보관 상태에서 붙여넣으면 보관 사유를 말하고 아무것도 보내지 않는다", async () => {
    const detail = salesDetail();
    const fake = makeFakeRows(detail, SALES_ROWS);
    const { calls } = installFetch({ ...HEALTH_HANDLERS, ...fake.handlers });
    const holder: { api: GridApi<GridRow> | null } = { api: null };
    render(
      <EntryGrid
        datasetId={7}
        columns={sortColumns(detail.columns)}
        baseDateColumnId={detail.base_date_column_id}
        canEnter={false}
        archived
        selectedColumnId={null}
        onSelectColumn={() => undefined}
        getVersion={() => 3}
        onVersion={() => undefined}
        onDefinitionStale={async () => undefined}
        onGridApi={(api) => {
          holder.api = api;
        }}
      />,
    );
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(grid.querySelector('[row-id^="r"]')).toBeTruthy());
    act(() => holder.api!.setFocusedCell(1, "2"));
    fireEvent.paste(grid, { clipboardData: { getData: (type: string) => (type === "text/plain" ? "10.5" : "") } });
    await waitFor(() => expect(screen.getByText(/보관된 데이터셋은 고칠 수 없어 붙여넣을 수 없습니다/)).toBeTruthy());
    expect(calls.filter((c) => c.method !== "GET")).toHaveLength(0);
  });
});
