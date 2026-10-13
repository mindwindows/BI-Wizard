import type { GridApi } from "ag-grid-community";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import { sortColumns } from "../dataset/api";
import { COL } from "../dataset/test-server";
import type { DatasetDetail } from "../dataset/types";
import { EntryGrid } from "./EntryGrid";
import type { GridRow } from "./model";
import { SALES_ROWS, makeFakeRows, row, salesDetail, type FakeRows } from "./test-server";
import type { Row } from "./types";

/**
 * 입력 그리드 시험(단위 1c). fetch는 계약(05 C1~C4)대로 동작하는 가짜 서버(test-server.ts)로 대신한다.
 *
 * jsdom 한계(시험의 범위):
 *  - 레이아웃이 없어 AG Grid가 마우스 더블클릭·Enter로 편집을 시작하지 못한다. 그래서 편집은 그리드 API(startEditingCell)로 시작하고,
 *    편집기에 입력(input 이벤트) -> Enter 키로 확정하는 부분은 실제 DOM 이벤트로 시험한다.
 *  - 열 가상화는 코드에서 끈다(suppressColumnVirtualisation). 행은 한 쪽(최대 200행) 안에서만 시험한다. 가로 스크롤·Tab 이동 순서·
 *    1920x1080 배치는 jsdom에서 확인하지 못한다(Playwright 스크린샷 단계에서 확인).
 *  - 붙여넣기는 그리드 래퍼에 paste 이벤트(clipboardData.getData("text/plain"))를 보내 시험한다. 실제 Excel 클립보드는 검증하지 못했다.
 *  - 로직(파서·계획 만들기·값 표현)은 순수 함수라 paste/*.test.ts, values.test.ts에서 따로 시험한다.
 */
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

interface Ctx {
  fake: FakeRows;
  calls: RecordedCall[];
  grid: HTMLElement;
  api: GridApi<GridRow>;
  onVersion: ReturnType<typeof vi.fn>;
  stale: ReturnType<typeof vi.fn>;
}

interface OpenOptions {
  detail?: DatasetDetail;
  rows?: Row[];
  handlers?: Record<string, Handler>;
  total?: number;
  waitRows?: boolean;
}

/** 작업공간 없이 EntryGrid만 올린다(정의 버전은 시험이 직접 관리). */
async function openGrid(options: OpenOptions = {}): Promise<Ctx> {
  const detail = options.detail ?? salesDetail();
  const fake = makeFakeRows(detail, options.rows ?? SALES_ROWS, { total: options.total });
  const { calls } = installFetch({ ...HEALTH_HANDLERS, ...fake.handlers, ...options.handlers });
  const onVersion = vi.fn();
  const holder: { api: GridApi<GridRow> | null } = { api: null };
  const version = { current: detail.def_version };
  const stale = vi.fn(async () => {
    version.current = fake.detail.def_version;
  });
  function Harness() {
    const ref = useRef(version);
    return (
      <EntryGrid
        datasetId={detail.id}
        columns={sortColumns(detail.columns)}
        baseDateColumnId={detail.base_date_column_id}
        canEnter={detail.permissions.enter}
        selectedColumnId={null}
        onSelectColumn={() => undefined}
        getVersion={() => ref.current.current}
        onVersion={onVersion}
        onDefinitionStale={stale}
        onGridApi={(api) => {
          holder.api = api;
        }}
      />
    );
  }
  render(<Harness />);
  const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
  if (options.waitRows !== false && (options.rows ?? SALES_ROWS).length > 0) {
    await waitFor(() => expect(grid.querySelector('[row-id^="r"]')).toBeTruthy());
  }
  return { fake, calls, grid, api: holder.api as unknown as GridApi<GridRow>, onVersion, stale };
}

const cell = (grid: HTMLElement, rowKey: string, colId: string): HTMLElement => {
  const found = grid.querySelector<HTMLElement>(`[row-id="${rowKey}"] [col-id="${colId}"]`);
  if (!found) throw new Error(`칸 없음: ${rowKey}/${colId}`);
  return found;
};
const text = (grid: HTMLElement, rowKey: string, colId: string) => {
  const c = cell(grid, rowKey, colId);
  return (c.querySelector(".cell-value") ?? c).textContent?.trim() ?? "";
};
const writes = (calls: RecordedCall[]) => calls.filter((c) => c.method !== "GET");
const reads = (calls: RecordedCall[]) => calls.filter((c) => c.method === "GET" && c.path.endsWith("/rows"));
const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)));

/** 저장된 행의 칸에서 편집기를 열고(API) 값을 넣어(input) Enter로 확정한다. */
async function edit(ctx: Ctx, rowKey: string, colId: string, value: string) {
  const index = ctx.api.getRenderedNodes().find((n) => n.data?.key === rowKey)?.rowIndex;
  if (index === null || index === undefined) throw new Error(`행 없음: ${rowKey}`);
  act(() => {
    ctx.api.setFocusedCell(index, colId);
    ctx.api.startEditingCell({ rowIndex: index, colKey: colId });
  });
  const input = await within(cell(ctx.grid, rowKey, colId)).findByRole("textbox");
  fireEvent.input(input, { target: { value } });
  fireEvent.keyDown(input, { key: "Enter", code: "Enter", keyCode: 13 });
  // Enter로 닫히지 않는 환경(jsdom)에서는 포커스를 잃을 때와 같은 stopEditing으로 확정한다.
  await sleep(30);
  if (ctx.api.getEditingCells().length > 0) act(() => ctx.api.stopEditing());
}

/** 맨 아래 '새 행 입력' 줄(고정 행)에서 편집한다. */
async function editEntry(ctx: Ctx, colId: string, value: string) {
  act(() => {
    ctx.api.setFocusedCell(0, colId, "bottom");
    ctx.api.startEditingCell({ rowIndex: 0, colKey: colId, rowPinned: "bottom" });
  });
  const input = await within(cell(ctx.grid, "entry", colId)).findByRole("textbox");
  fireEvent.input(input, { target: { value } });
  act(() => ctx.api.stopEditing());
  await sleep(10);
}

/** 붙여넣기 이벤트. 시작 칸은 먼저 포커스를 옮겨 정한다. */
function paste(ctx: Ctx, clipboard: string, at?: { rowIndex: number; colId: string; pinned?: "bottom" }) {
  if (at) act(() => ctx.api.setFocusedCell(at.rowIndex, at.colId, at.pinned));
  fireEvent.paste(ctx.grid, { clipboardData: { getData: (type: string) => (type === "text/plain" ? clipboard : "") } });
}

const dialog = () => screen.getByRole("dialog", { name: "붙여넣기 확인" });
const applyPaste = () => fireEvent.click(within(dialog()).getByRole("button", { name: "붙여넣기 적용" }));

describe("그리드 렌더링", () => {
  it("열은 위치 순이고 맨 앞에 기간/행 번호 열이 있다", async () => {
    const { grid } = await openGrid();
    const headers = within(grid).getAllByRole("columnheader").map((h) => h.textContent?.trim());
    expect(headers[0]).toContain("기간 / 행 번호");
    expect(headers.slice(1).map((h) => h?.split(" (")[0])).toEqual(["기준일", "매출", "메모", "등급", "합계"]);
    expect(headers[1]).toContain("(기간)"); // 기준 날짜 열 표시
    // 기본 순서는 최근 순(desc): 행 3, 2, 1
    expect(Array.from(grid.querySelectorAll('[row-id^="r"]')).map((r) => r.getAttribute("row-id"))).toEqual(["r3", "r2", "r1"]);
    expect(text(grid, "r1", "__row")).toBe("2026-03-01 · #1");
  });

  it("숫자는 십진 문자열 그대로 서식만 입히고 오른쪽 정렬 클래스를 단다(끝자리 0 보존)", async () => {
    const { grid } = await openGrid({
      rows: [
        row(1, { "1": "2026-03-01", "2": "1234.5" }),
        row(2, { "1": "2026-02-01", "2": "12345678901234567890.12345" }),
        row(3, { "1": "2026-01-01", "2": "-5" }),
      ],
    });
    expect(text(grid, "r1", "2")).toBe("1,234.50"); // decimals 2 규칙으로 끝자리 0을 채움
    expect(text(grid, "r2", "2")).toBe("12,345,678,901,234,567,890.12345"); // 부동소수점이면 깨질 값, 깎지 않음
    expect(text(grid, "r3", "2")).toBe("-5.00");
    expect(cell(grid, "r1", "2").classList.contains("cell-number")).toBe(true);
  });

  it("빈 칸(미입력)과 값 0은 구별되어 보인다", async () => {
    const { grid } = await openGrid();
    expect(text(grid, "r2", "2")).toBe("0.00"); // 값 0
    expect(cell(grid, "r2", "2").querySelector('[aria-label="빈 칸"]')).toBeNull();
    expect(cell(grid, "r3", "2").querySelector('[aria-label="빈 칸"]')).not.toBeNull(); // null
    expect(cell(grid, "r3", "2").classList.contains("cell-blank")).toBe(true);
    expect(cell(grid, "r2", "2").classList.contains("cell-blank")).toBe(false);
  });

  it("계산 열은 읽기 전용으로 구별 표시되고 오류 칸은 오류로 표시된다", async () => {
    const detail = salesDetail();
    const { grid, api } = await openGrid({ detail });
    expect(cell(grid, "r1", "5").classList.contains("cell-formula")).toBe(true);
    expect(cell(grid, "r2", "5").classList.contains("cell-error")).toBe(true);
    expect(text(grid, "r2", "5")).toBe("오류");
    expect(cell(grid, "r2", "5").querySelector(".cell-text")?.getAttribute("title")).toContain("0으로 나누어");
    // 오류가 아닌 계산 열의 미입력(null)은 오류가 아니라 빈 칸
    expect(cell(grid, "r1", "5").classList.contains("cell-error")).toBe(false);
    // 편집 불가
    const index = api.getRenderedNodes().find((n) => n.data?.key === "r1")?.rowIndex as number;
    act(() => {
      api.setFocusedCell(index, "5");
      api.startEditingCell({ rowIndex: index, colKey: "5" });
    });
    await sleep(20);
    expect(api.getEditingCells()).toHaveLength(0);
  });

  it("계산 열 빈 칸은 입력 열과 같은 빗금(cell-blank)을 유지하고 계산 열 표지(cell-formula)가 함께 붙는다, 오류 칸은 빗금이 아니다", async () => {
    // jsdom은 CSS를 계산하지 않아 실제 색은 확인하지 못한다. 대신 클래스 조합(스타일 규칙의 입력)을 확인한다.
    // styles.css: .cell-formula는 배경을 갖지 않고, 배경은 :not(.cell-blank):not(.cell-error)에만 준다(스크린샷으로 눈 확인).
    const { grid } = await openGrid({ detail: salesDetail() });
    const blank = cell(grid, "r1", "5");
    expect(blank.classList.contains("cell-formula")).toBe(true);
    expect(blank.classList.contains("cell-blank")).toBe(true);
    const err = cell(grid, "r2", "5");
    expect(err.classList.contains("cell-error")).toBe(true);
    expect(err.classList.contains("cell-blank")).toBe(false);
  });

  it("계산 열 칸을 두 번 누르면 직접 고칠 수 없다는 안내가 나오고 편집기는 열리지 않는다", async () => {
    const { grid, api } = await openGrid({ detail: salesDetail() });
    expect(screen.queryByTestId("formula-edit-notice")).toBeNull();
    fireEvent.doubleClick(cell(grid, "r2", "5"));
    const notice = await screen.findByTestId("formula-edit-notice");
    expect(notice.textContent).toContain("계산 열은 수식으로 계산되어 직접 고칠 수 없습니다");
    expect(notice.textContent).toContain("Inspector");
    expect(api.getEditingCells()).toHaveLength(0);
  });

  it("입력 열 칸을 두 번 눌러도 계산 열 안내는 나오지 않는다", async () => {
    const { grid } = await openGrid({ detail: salesDetail() });
    fireEvent.doubleClick(cell(grid, "r1", "2"));
    await sleep(20);
    expect(screen.queryByTestId("formula-edit-notice")).toBeNull();
  });

  it("선택 목록·예/아니오 열은 선택 편집기를 쓰고 예/아니오는 글자로 보인다", async () => {
    const detail = salesDetail({
      columns: [COL(1, "기준일", "date", { required: true }), COL(4, "등급", "choice", { rules: { options: ["상", "중"] } }), COL(6, "승인", "boolean")],
    });
    const { grid } = await openGrid({
      detail,
      rows: [row(1, { "1": "2026-03-01", "4": "상", "6": true }), row(2, { "1": "2026-02-01", "4": null, "6": false }), row(3, { "1": "2026-01-01", "4": "중", "6": null })],
    });
    expect(text(grid, "r1", "6")).toBe("예");
    expect(text(grid, "r2", "6")).toBe("아니오");
    expect(cell(grid, "r3", "6").querySelector('[aria-label="빈 칸"]')).not.toBeNull();
  });

  it("행이 없으면 빈 상태 안내", async () => {
    await openGrid({ rows: [] });
    expect(await screen.findByTestId("no-rows")).toBeTruthy();
  });

  it("읽기에 실패하면 쉬운 문구와 다시 불러오기, 누르면 다시 읽는다", async () => {
    let fail = true;
    const { calls } = await openGrid({
      waitRows: false,
      handlers: { "GET /datasets/7/rows": () => (fail ? apiError(503, "SERVICE_UNAVAILABLE") : json(200, { def_version: 3, items: [], total: 0, limit: 50, offset: 0 })) },
    }).catch(() => ({ calls: [] as RecordedCall[] }));
    void calls;
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("일시적으로 응답하지 못합니다");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "다시 불러오기" }));
    await screen.findByTestId("no-rows");
  });

  it("불러오는 동안 로딩 문구", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const detail = salesDetail();
    const fake = makeFakeRows(detail, SALES_ROWS);
    installFetch({ ...fake.handlers, "GET /datasets/7/rows": async (call) => (await gate, fake.handlers["GET /datasets/7/rows"](call)) });
    render(
      <EntryGrid
        datasetId={7}
        columns={detail.columns}
        baseDateColumnId={1}
        canEnter
        selectedColumnId={null}
        onSelectColumn={() => undefined}
        getVersion={() => 3}
        onVersion={() => undefined}
        onDefinitionStale={async () => undefined}
      />,
    );
    expect((await screen.findByRole("status")).textContent).toContain("불러오는 중");
    release();
    await screen.findByRole("group", { name: "입력 그리드 표" });
  });

  it("작업공간(S4)에 통합되어 정의의 열과 permissions.enter를 따른다", async () => {
    const detail = salesDetail({ permissions: { define: false, enter: false } });
    const fake = makeFakeRows(detail, SALES_ROWS);
    installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), ...fake.handlers });
    render(<App router={createTestRouter(BASE, `${BASE}/datasets/7`)} />);
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(grid.querySelector('[row-id="r1"]')).toBeTruthy());
    expect(within(screen.getByRole("region", { name: "입력 그리드" })).getByRole("note").textContent).toContain("읽기 전용입니다");
    expect(screen.queryByRole("button", { name: "새 행 추가" })).toBeNull();
  });
});

describe("작업공간 통합: 정의 버전", () => {
  it("행 조회가 더 큰 정의 버전을 알리면 작업공간이 정의를 다시 읽는다", async () => {
    const detail = salesDetail();
    const fake = makeFakeRows(detail, SALES_ROWS);
    const { calls } = installFetch({
      ...HEALTH_HANDLERS,
      "GET /me": () => json(200, ADMIN_ME),
      ...fake.handlers,
      "GET /datasets/7/rows": () => json(200, { def_version: 4, items: [], total: 0, limit: 50, offset: 0 }),
    });
    render(<App router={createTestRouter(BASE, `${BASE}/datasets/7`)} />);
    await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7")).toHaveLength(2));
  });
});

describe("조회 순서와 쪽 이동 (C1)", () => {
  it("정렬과 쪽 이동은 order·limit·offset 쿼리로 서버에 요청한다", async () => {
    const { calls } = await openGrid({ total: 120 });
    expect(reads(calls)[0].query.toString()).toBe("order=desc&limit=50&offset=0");
    expect(screen.getByText("1–3 / 전체 120행")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("정렬 순서"), { target: { value: "asc" } });
    await waitFor(() => expect(reads(calls)).toHaveLength(2));
    expect(reads(calls)[1].query.toString()).toBe("order=asc&limit=50&offset=0");
    // 이 가짜 서버는 total을 120으로 말하지만 항목은 3개뿐이다. 다음 쪽 버튼은 offset을 limit만큼 올린다.
    fireEvent.change(screen.getByLabelText("한 쪽 행 수"), { target: { value: "100" } });
    await waitFor(() => expect(reads(calls)).toHaveLength(3));
    expect(reads(calls)[2].query.toString()).toBe("order=asc&limit=100&offset=0");
    fireEvent.click(screen.getByRole("button", { name: "다음 쪽" }));
    await waitFor(() => expect(reads(calls)).toHaveLength(4));
    expect(reads(calls)[3].query.toString()).toBe("order=asc&limit=100&offset=100");
    fireEvent.click(screen.getByRole("button", { name: "이전 쪽" }));
    await waitFor(() => expect(reads(calls)).toHaveLength(5));
    expect(reads(calls)[4].query.get("offset")).toBe("0");
  });

  it("C1이 알려 준 정의 버전을 작업공간에 알린다", async () => {
    const { onVersion } = await openGrid();
    expect(onVersion).toHaveBeenCalledWith(3);
  });
});

describe("칸 편집 (C3)", () => {
  it("호출 본문: expected(편집 전 화면 값)·value·expected_version, 성공하면 서버 행으로 갱신", async () => {
    const ctx = await openGrid();
    await edit(ctx, "r1", "3", "새 메모");
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    const call = writes(ctx.calls)[0];
    expect(`${call.method} ${call.path}`).toBe("PATCH /datasets/7/rows/1");
    expect(call.body).toEqual({ expected_version: 3, changes: [{ column_id: 3, expected: null, value: "새 메모" }] });
    await waitFor(() => expect(text(ctx.grid, "r1", "3")).toBe("새 메모"));
    expect(cell(ctx.grid, "r1", "3").classList.contains("cell-pending")).toBe(false);
    expect(ctx.onVersion).toHaveBeenLastCalledWith(3);
  });

  it("숫자는 문자열 그대로 보내고 expected도 서버가 준 문자열 그대로다", async () => {
    const ctx = await openGrid();
    await edit(ctx, "r1", "2", "99.50");
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    expect(writes(ctx.calls)[0].body).toEqual({ expected_version: 3, changes: [{ column_id: 2, expected: "1234.50", value: "99.50" }] });
    await waitFor(() => expect(text(ctx.grid, "r1", "2")).toBe("99.50"));
  });

  it("칸을 비우면 null(미입력)을 보낸다", async () => {
    const ctx = await openGrid();
    await edit(ctx, "r2", "3", "");
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    expect(writes(ctx.calls)[0].body).toEqual({ expected_version: 3, changes: [{ column_id: 3, expected: "2월 메모", value: null }] });
  });

  it("값이 그대로면 호출하지 않는다", async () => {
    const ctx = await openGrid();
    await edit(ctx, "r2", "3", "2월 메모");
    await sleep(30);
    expect(writes(ctx.calls)).toHaveLength(0);
  });

  it("형식이 분명히 틀린 값은 서버 호출 없이 쉬운 문구를 보이고 값은 그대로 둔다", async () => {
    const ctx = await openGrid();
    await edit(ctx, "r1", "2", "abc");
    const panel = await screen.findByRole("alert", { name: "확인이 필요한 칸" });
    expect(panel.textContent).toContain("숫자만 입력해 주세요");
    expect(panel.textContent).toContain("행 #1 · 매출");
    expect(writes(ctx.calls)).toHaveLength(0);
    expect(text(ctx.grid, "r1", "2")).toBe("1,234.50");
    expect(cell(ctx.grid, "r1", "2").classList.contains("cell-invalid")).toBe(true);
    fireEvent.click(within(panel).getByRole("button", { name: "닫기" }));
    await waitFor(() => expect(screen.queryByRole("alert", { name: "확인이 필요한 칸" })).toBeNull());
  });

  it("낙관적으로 새 값을 보이다가 실패하면 되돌린다", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const ctx = await openGrid({ handlers: { "PATCH /datasets/7/rows/1": async () => (await gate, apiError(500, "INTERNAL_ERROR", "서버 내부 문구 SELECT")) } });
    await edit(ctx, "r1", "3", "임시값");
    await waitFor(() => expect(text(ctx.grid, "r1", "3")).toBe("임시값"));
    expect(cell(ctx.grid, "r1", "3").classList.contains("cell-pending")).toBe(true);
    release();
    await waitFor(() => expect(cell(ctx.grid, "r1", "3").querySelector('[aria-label="빈 칸"]')).not.toBeNull());
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("예기치 않은 오류");
    expect(alert.textContent).not.toContain("SELECT");
  });

  it("CELL_CONFLICT: 서버 값을 보이고 충돌 목록에서 내 값으로 다시 저장할 수 있다", async () => {
    const ctx = await openGrid();
    // 다른 사람이 먼저 메모를 바꿈
    ctx.fake.rows.find((r) => r.row_id === 1)!.cells["3"] = "남이 쓴 메모";
    await edit(ctx, "r1", "3", "내 메모");
    const panel = await screen.findByRole("alert", { name: "충돌 목록" });
    expect(panel.textContent).toContain('내 값 "내 메모"');
    expect(panel.textContent).toContain('서버 값 "남이 쓴 메모"');
    expect(text(ctx.grid, "r1", "3")).toBe("남이 쓴 메모");
    expect(cell(ctx.grid, "r1", "3").classList.contains("cell-conflict")).toBe(true);
    // 내 값으로 저장: expected는 방금 본 서버 값
    fireEvent.click(within(panel).getByRole("button", { name: "내 값으로 저장" }));
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(2));
    expect(writes(ctx.calls)[1].body).toEqual({ expected_version: 3, changes: [{ column_id: 3, expected: "남이 쓴 메모", value: "내 메모" }] });
    await waitFor(() => expect(text(ctx.grid, "r1", "3")).toBe("내 메모"));
    expect(screen.queryByRole("alert", { name: "충돌 목록" })).toBeNull();
  });

  it("CELL_CONFLICT: 서버 값 유지를 고르면 충돌 표시만 사라지고 저장하지 않는다", async () => {
    const ctx = await openGrid();
    ctx.fake.rows.find((r) => r.row_id === 1)!.cells["3"] = "남이 쓴 메모";
    await edit(ctx, "r1", "3", "내 메모");
    const panel = await screen.findByRole("alert", { name: "충돌 목록" });
    fireEvent.click(within(panel).getByRole("button", { name: "서버 값 유지" }));
    await waitFor(() => expect(screen.queryByRole("alert", { name: "충돌 목록" })).toBeNull());
    expect(writes(ctx.calls)).toHaveLength(1);
    expect(text(ctx.grid, "r1", "3")).toBe("남이 쓴 메모");
    expect(cell(ctx.grid, "r1", "3").classList.contains("cell-conflict")).toBe(false);
  });

  it("DEFINITION_VERSION_MISMATCH: 값을 되돌리고 정의와 행을 다시 읽는다", async () => {
    const ctx = await openGrid();
    ctx.fake.detail.def_version = 4; // 다른 사람이 열을 추가함
    await edit(ctx, "r1", "3", "내 메모");
    await waitFor(() => expect(ctx.stale).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(reads(ctx.calls)).toHaveLength(2));
    expect((await screen.findAllByRole("alert")).map((a) => a.textContent).join(" ")).toContain("다른 사람이 먼저 바꿨습니다");
    expect(cell(ctx.grid, "r1", "3").querySelector('[aria-label="빈 칸"]')).not.toBeNull();
    // 이제 새 버전으로 저장된다
    await edit(ctx, "r1", "3", "내 메모");
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(2));
    expect((writes(ctx.calls)[1].body as { expected_version: number }).expected_version).toBe(4);
  });

  it("WRITE_BUSY: 되돌리고 '다시 시도' 버튼으로 같은 저장을 다시 한다", async () => {
    let busy = true;
    const ctx = await openGrid({
      handlers: {
        "PATCH /datasets/7/rows/1": (call) => (busy ? apiError(503, "WRITE_BUSY", "서버 문구", { retry_after: 2 }) : makeFake(ctx).handlers["PATCH /datasets/7/rows/1"](call)),
      },
    });
    function makeFake(c: Ctx) {
      return c.fake;
    }
    await edit(ctx, "r1", "3", "내 메모");
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("다른 작업이 진행 중");
    expect(alert.textContent).toContain("약 2초 뒤");
    expect(cell(ctx.grid, "r1", "3").querySelector('[aria-label="빈 칸"]')).not.toBeNull();
    busy = false;
    fireEvent.click(within(alert).getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(text(ctx.grid, "r1", "3")).toBe("내 메모"));
    expect(writes(ctx.calls)).toHaveLength(2);
  });

  it("422 필드 오류: 되돌리고 칸 옆에 쉬운 문구(허용 범위)를 보인다", async () => {
    const ctx = await openGrid({
      detail: salesDetail({
        columns: [COL(1, "기준일", "date", { required: true }), COL(2, "매출", "number", { rules: { min: "0", max: "100", decimals: 2 } })],
      }),
      rows: [row(1, { "1": "2026-03-01", "2": "50" })],
      handlers: {
        "PATCH /datasets/7/rows/1": () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ column_id: 2, code: "OUT_OF_RANGE", message: "범위" }] }),
      },
    });
    await edit(ctx, "r1", "2", "500");
    const panel = await screen.findByRole("alert", { name: "확인이 필요한 칸" });
    expect(panel.textContent).toContain("매출: 허용 범위를 벗어났습니다(0 ~ 100)");
    expect(text(ctx.grid, "r1", "2")).toBe("50.00");
  });

  it("행이 없어졌으면(ROW_NOT_FOUND) 안내하고 다시 읽는다", async () => {
    const ctx = await openGrid({ handlers: { "PATCH /datasets/7/rows/1": () => apiError(404, "ROW_NOT_FOUND") } });
    await edit(ctx, "r1", "3", "내 메모");
    expect((await screen.findByRole("alert")).textContent).toContain("행을 찾을 수 없습니다");
    await waitFor(() => expect(reads(ctx.calls)).toHaveLength(2));
  });

  it("읽기 전용(permissions.enter=false)이면 편집이 시작되지 않고 안내가 보인다", async () => {
    const ctx = await openGrid({ detail: salesDetail({ permissions: { define: false, enter: false } }) });
    expect(screen.getByRole("note").textContent).toContain("읽기 전용");
    const index = ctx.api.getRenderedNodes().find((n) => n.data?.key === "r1")?.rowIndex as number;
    act(() => {
      ctx.api.setFocusedCell(index, "3");
      ctx.api.startEditingCell({ rowIndex: index, colKey: "3" });
    });
    await sleep(20);
    expect(ctx.api.getEditingCells()).toHaveLength(0);
    expect(screen.queryByRole("button", { name: "새 행 추가" })).toBeNull();
    expect(ctx.grid.querySelector('[row-id="entry"]')).toBeNull(); // 새 행 입력 줄 없음
    // 읽기 전용에서는 붙여넣기도 호출 없이 안내만
    paste(ctx, "1\t2", { rowIndex: index, colId: "2" });
    expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("읽기 전용");
    expect(writes(ctx.calls)).toHaveLength(0);
  });
});

describe("임시 행 (C2)", () => {
  const required2 = () =>
    salesDetail({
      columns: [COL(1, "기준일", "date", { required: true }), COL(2, "매출", "number", { required: true }), COL(3, "메모", "text")],
    });

  it("맨 아래 입력 줄에 입력하면 임시 행이 되고, 필수 칸이 모두 찰 때 C2를 한 번만 부른다", async () => {
    const ctx = await openGrid({ detail: required2(), rows: [row(1, { "1": "2026-03-01", "2": "10" })] });
    await editEntry(ctx, "3", "먼저 쓴 메모");
    const panel = await screen.findByRole("region", { name: "저장 전 새 행" });
    await waitFor(() => expect(ctx.grid.querySelector('[row-id^="d"]')).toBeTruthy());
    expect(panel.textContent).toContain("채워야 할 필수 칸 — 기준일, 매출");
    expect(panel.textContent).toContain("새로고침하면 사라집니다");
    expect(writes(ctx.calls)).toHaveLength(0); // 필수 칸이 비어 서버에 저장하지 않는다
    // 임시 행에서 계속 입력
    const draftIndex = 1; // 저장된 행 1개 다음
    const editDraft = async (colId: string, value: string) => {
      act(() => {
        ctx.api.setFocusedCell(draftIndex, colId);
        ctx.api.startEditingCell({ rowIndex: draftIndex, colKey: colId });
      });
      const input = await within(ctx.grid.querySelector(`[row-id^="d"] [col-id="${colId}"]`) as HTMLElement).findByRole("textbox");
      fireEvent.input(input, { target: { value } });
      act(() => ctx.api.stopEditing());
      await sleep(10);
    };
    await editDraft("1", "2026-04-01");
    expect(writes(ctx.calls)).toHaveLength(0);
    await editDraft("2", "12.5");
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    const call = writes(ctx.calls)[0];
    expect(`${call.method} ${call.path}`).toBe("POST /datasets/7/rows");
    expect(call.body).toEqual({ expected_version: 3, cells: { "1": "2026-04-01", "2": "12.5", "3": "먼저 쓴 메모" } });
    // 저장 뒤 임시 행은 사라지고 행 목록을 다시 읽는다
    await waitFor(() => expect(screen.queryByRole("region", { name: "저장 전 새 행" })).toBeNull());
    await waitFor(() => expect(reads(ctx.calls).length).toBeGreaterThanOrEqual(2));
    expect(writes(ctx.calls)).toHaveLength(1);
  });

  it("'새 행 추가' 버튼은 임시 행을 만들고, 버릴 수 있다", async () => {
    const ctx = await openGrid({ detail: required2() });
    fireEvent.click(screen.getByRole("button", { name: "새 행 추가" }));
    const panel = await screen.findByRole("region", { name: "저장 전 새 행" });
    expect(panel.textContent).toContain("임시 행 1");
    await waitFor(() => expect(ctx.grid.querySelector('[row-id^="d"]')).toBeTruthy());
    fireEvent.click(within(panel).getByRole("button", { name: "버리기" }));
    await waitFor(() => expect(screen.queryByRole("region", { name: "저장 전 새 행" })).toBeNull());
    expect(writes(ctx.calls)).toHaveLength(0);
  });

  it("같은 기간이 이미 있으면 PERIOD_CONFLICT를 알리고 임시 행을 유지한다", async () => {
    const ctx = await openGrid({ detail: required2(), rows: [row(1, { "1": "2026-03-01", "2": "10" })] });
    await editEntry(ctx, "1", "2026-03-01");
    expect(writes(ctx.calls)).toHaveLength(0);
    await waitFor(() => expect(ctx.grid.querySelector('[row-id^="d"]')).toBeTruthy());
    const index = 1;
    act(() => {
      ctx.api.setFocusedCell(index, "2");
      ctx.api.startEditingCell({ rowIndex: index, colKey: "2" });
    });
    const input = await within(ctx.grid.querySelector('[row-id^="d"] [col-id="2"]') as HTMLElement).findByRole("textbox");
    fireEvent.input(input, { target: { value: "7" } });
    act(() => ctx.api.stopEditing());
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    const panel = await screen.findByRole("region", { name: "저장 전 새 행" });
    await waitFor(() => expect(panel.textContent).toContain("이미 같은 기간의 행이 있습니다"));
    expect(ctx.grid.querySelector('[row-id^="d"]')).toBeTruthy(); // 입력한 내용은 남아 있다
    expect(within(await screen.findByRole("alert", { name: "확인이 필요한 칸" })).getByText(/기준일/)).toBeTruthy();
  });
});

describe("엑셀 붙여넣기 (C4)", () => {
  it("기존 행에 덮어쓰기: 확인창 요약 -> 호출 본문(row_id·expected·values) -> 성공 요약", async () => {
    const ctx = await openGrid();
    // 화면 순서(최근 순): r3, r2, r1. 두 번째 행(r2)의 '매출' 칸에서 시작한다.
    paste(ctx, "10.5\t메모A\r\n20\t메모B\r\n", { rowIndex: 1, colId: "2" });
    const confirm = dialog();
    expect(confirm.textContent).toContain("2줄 × 2열");
    expect(confirm.textContent).toContain("기존 행 2개의 값을 덮어쓰고");
    expect(confirm.textContent).toContain("새 행 0개");
    expect(writes(ctx.calls)).toHaveLength(0); // 확인 전에는 보내지 않는다
    applyPaste();
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    const call = writes(ctx.calls)[0];
    expect(`${call.method} ${call.path}`).toBe("POST /datasets/7/rows/paste");
    expect(call.body).toEqual({
      expected_version: 3,
      column_ids: [2, 3],
      rows: [
        { row_id: 2, expected: ["0", "2월 메모"], values: ["10.5", "메모A"] },
        { row_id: 1, expected: ["1234.50", null], values: ["20", "메모B"] },
      ],
    });
    const result = await screen.findByRole("status", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("2행을 고치고 0행을 새로 추가했습니다");
    await waitFor(() => expect(text(ctx.grid, "r2", "3")).toBe("메모A"));
    expect(ctx.fake.rows.find((r) => r.row_id === 1)!.cells["2"]).toBe("20");
  });

  it("빈 칸은 null로 보내고(지우기), 공백은 자르지 않는다", async () => {
    const ctx = await openGrid();
    paste(ctx, "\t 앞뒤 공백 \r\n", { rowIndex: 1, colId: "2" });
    applyPaste();
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    expect((writes(ctx.calls)[0].body as { rows: { values: unknown[] }[] }).rows[0].values).toEqual([null, " 앞뒤 공백 "]);
  });

  it("맨 아래 새 행 입력 줄에서 붙이면 모두 새 행(row_id=null, expected 없음)", async () => {
    const ctx = await openGrid();
    paste(ctx, "2026-04-01\t5\r\n2026-05-01\t6\r\n", { rowIndex: 0, colId: "1", pinned: "bottom" });
    expect(dialog().textContent).toContain("새 행 2개");
    applyPaste();
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    expect(writes(ctx.calls)[0].body).toEqual({
      expected_version: 3,
      column_ids: [1, 2],
      rows: [
        { row_id: null, values: ["2026-04-01", "5"] },
        { row_id: null, values: ["2026-05-01", "6"] },
      ],
    });
    expect(await screen.findByText(/0행을 고치고 2행을 새로 추가했습니다/)).toBeTruthy();
    await waitFor(() => expect(ctx.grid.querySelector('[row-id="r4"]')).toBeTruthy());
  });

  it("마지막 쪽에서 끝을 넘는 줄은 새 행이 된다(기존 행의 기준 날짜가 저장된 값과 같으면 통과)", async () => {
    const ctx = await openGrid();
    // 마지막 화면 행(r1, 2026-03-01)의 기준일 칸에서 3줄 -> 1줄은 기존 행(같은 기준월), 2줄은 새 행
    paste(ctx, "2026-03-01\t7\r\n2026-04-01\t8\r\n2026-05-01\t9", { rowIndex: 2, colId: "1" });
    expect(dialog().textContent).toContain("기존 행 1개");
    expect(dialog().textContent).toContain("새 행 2개");
    applyPaste();
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(1));
    const body = writes(ctx.calls)[0].body as { rows: { row_id: number | null; expected?: unknown[]; values: unknown[] }[] };
    expect(body.rows.map((r) => r.row_id)).toEqual([1, null, null]);
    expect("expected" in body.rows[1]).toBe(false);
    expect(body.rows[0]).toEqual({ row_id: 1, expected: ["2026-03-01", "1234.50"], values: ["2026-03-01", "7"] });
    expect(await screen.findByText(/1행을 고치고 2행을 새로 추가했습니다/)).toBeTruthy();
    expect(ctx.fake.rows.find((r) => r.row_id === 1)!.cells).toMatchObject({ "1": "2026-03-01", "2": "7" });
  });

  it("새 행에 기준 날짜 열이 없으면 확인창 전에 안내하고 보내지 않는다", async () => {
    const ctx = await openGrid();
    paste(ctx, "a\r\nb\r\nc", { rowIndex: 2, colId: "3" });
    const alert = await screen.findByRole("alert", { name: "붙여넣기 오류" });
    expect(alert.textContent).toContain("2번째 줄 · 새 행에는 기준 열 값이 필요합니다");
    // 1c 후속: 줄 번호는 항목마다 한 번만 나온다("2번째 줄 · 2번째 줄: …" 중복 없음)
    for (const item of alert.querySelectorAll("li")) expect(item.textContent?.match(/번째 줄/g)).toHaveLength(1);
    expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull();
    expect(writes(ctx.calls)).toHaveLength(0);
  });

  it("쪽 끝을 넘지만 마지막 쪽이 아니면 새 행으로 만들지 않고 안내한다", async () => {
    const ctx = await openGrid({ total: 120 });
    paste(ctx, "a\r\nb\r\nc\r\nd", { rowIndex: 2, colId: "3" });
    const alert = await screen.findByRole("alert", { name: "붙여넣기 오류" });
    expect(alert.textContent).toContain("마지막 쪽에서만");
    expect(writes(ctx.calls)).toHaveLength(0);
  });

  it("PASTE_CONFLICT: 전부 취소 안내, 충돌 칸을 강조하고 서버 값을 보인다, 서버 값 기준으로 다시 붙여넣을 수 있다", async () => {
    const ctx = await openGrid();
    ctx.fake.rows.find((r) => r.row_id === 1)!.cells["2"] = "777"; // 다른 사람이 먼저 바꿈
    paste(ctx, "1\r\n2\r\n3", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("아무것도 저장되지 않았습니다");
    expect(result.textContent).toContain("일부만 반영되는 일은 없으며");
    expect(result.textContent).toContain('3번째 줄 · 행 #1 · 매출: 서버에는 "777.00" 값이 있습니다.');
    expect(ctx.fake.rows.find((r) => r.row_id === 3)!.cells["2"] ?? null).toBeNull(); // 서버에 부분 반영 없음
    await waitFor(() => expect(cell(ctx.grid, "r1", "2").classList.contains("cell-conflict")).toBe(true));
    expect(text(ctx.grid, "r1", "2")).toBe("777.00");
    expect(screen.getByRole("alert", { name: "충돌 목록" }).textContent).toContain("행 #1 · 매출");
    // 서버 값 기준으로 다시 붙여넣기 -> 확인창 -> 이번에는 expected가 서버 값
    fireEvent.click(within(result).getByRole("button", { name: "서버 값 기준으로 다시 붙여넣기" }));
    applyPaste();
    await waitFor(() => expect(writes(ctx.calls)).toHaveLength(2));
    const retry = writes(ctx.calls)[1].body as { rows: { row_id: number; expected: unknown[] }[] };
    expect(retry.rows.find((r) => r.row_id === 1)?.expected).toEqual(["777"]);
    expect(await screen.findByText(/3행을 고치고 0행을 새로 추가했습니다/)).toBeTruthy();
  });

  it("PASTE_CONFLICT의 period·row_missing 종류도 목록에 쉬운 말로 나온다", async () => {
    const ctx = await openGrid({
      handlers: {
        "POST /datasets/7/rows/paste": () =>
          apiError(409, "PASTE_CONFLICT", "서버 문구", {
            conflicts: [
              { row_index: 0, row_id: null, column_id: 1, kind: "period", current: null },
              { row_index: 1, row_id: 99, column_id: null, kind: "row_missing", current: null },
            ],
          }),
      },
    });
    paste(ctx, "2026-06-01\t1", { rowIndex: 0, colId: "1", pinned: "bottom" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("1번째 줄 · 새 행의 기간이 이미 있습니다");
    expect(result.textContent).toContain("2번째 줄 · 행 #99이(가) 사라졌습니다");
  });

  it("nginx의 JSON 아닌 413도 PAYLOAD_TOO_LARGE와 같은 안내(5,000행·1MiB)", async () => {
    const ctx = await openGrid({
      handlers: { "POST /datasets/7/rows/paste": () => new Response("<html><body>413 Request Entity Too Large</body></html>", { status: 413, headers: { "Content-Type": "text/html" } }) },
    });
    paste(ctx, "1", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("너무 큽니다");
    expect(result.textContent).toContain("5,000행");
    expect(result.textContent).toContain("1MiB");
    expect(result.textContent).not.toContain("nginx");
  });

  it("JSON PAYLOAD_TOO_LARGE(413)도 같은 안내", async () => {
    const ctx = await openGrid({ handlers: { "POST /datasets/7/rows/paste": () => apiError(413, "PAYLOAD_TOO_LARGE", "서버 문구", { limit: 5000 }) } });
    paste(ctx, "1", { rowIndex: 0, colId: "2" });
    applyPaste();
    expect((await screen.findByRole("alert", { name: "붙여넣기 결과" })).textContent).toContain("5,000행");
  });

  it("422 필드 오류: 줄 번호와 열 이름으로 위치를 보이고 기존 행 칸을 표시한다", async () => {
    const ctx = await openGrid({
      detail: salesDetail({
        columns: [COL(1, "기준일", "date", { required: true }), COL(2, "매출", "number", { rules: { min: "0", max: "100" } })],
      }),
      rows: [row(1, { "1": "2026-03-01", "2": "5" }), row(2, { "1": "2026-02-01", "2": "6" })],
      handlers: {
        "POST /datasets/7/rows/paste": () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ row_index: 1, column_id: 2, code: "OUT_OF_RANGE", message: "x" }] }),
      },
    });
    paste(ctx, "50\r\n500", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("2번째 줄 · 매출: 허용 범위를 벗어났습니다(0 ~ 100)");
    expect(result.textContent).toContain("아무것도 저장하지 않았습니다");
    // 화면 순서(최근 순) 2번째 줄 = r1
    await waitFor(() => expect(cell(ctx.grid, "r1", "2").classList.contains("cell-invalid")).toBe(true));
  });

  it("422가 잘렸으면(truncated) 붙여넣기 결과에 '일부만 표시됨'을 보이고 외 N건 계산은 서버 값이 우선", async () => {
    const ctx = await openGrid({
      detail: salesDetail({
        columns: [COL(1, "기준일", "date", { required: true }), COL(2, "매출", "number", { rules: { min: "0", max: "1000000" } })],
      }),
      rows: [row(1, { "1": "2026-03-01", "2": "5" })],
      handlers: {
        "POST /datasets/7/rows/paste": () =>
          apiError(422, "VALIDATION_ERROR", "서버 문구", {
            fields: Array.from({ length: 25 }, () => ({ row_index: 0, column_id: 2, code: "OUT_OF_RANGE", message: "x" })),
            truncated: true,
            total: 480,
          }),
      },
    });
    paste(ctx, "9999999", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("일부만 표시됨(전체 480건 중 일부)");
    expect(result.textContent).not.toContain("외 5건");
    // 범위 문구는 칸 표시와 같은 쉼표 서식
    expect(result.textContent).toContain("(0 ~ 1,000,000)");
  });

  it("잘리지 않았으면 일부만 표시됨 문구가 없다", async () => {
    const ctx = await openGrid({
      detail: salesDetail({ columns: [COL(1, "기준일", "date", { required: true }), COL(2, "매출", "number", { rules: { min: "0", max: "100" } })] }),
      rows: [row(1, { "1": "2026-03-01", "2": "5" })],
      handlers: {
        "POST /datasets/7/rows/paste": () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ row_index: 0, column_id: 2, code: "OUT_OF_RANGE", message: "x" }], truncated: false, total: 1 }),
      },
    });
    paste(ctx, "500", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).not.toContain("일부만 표시됨");
  });

  it("충돌이 잘렸으면(truncated) 붙여넣기 충돌 결과에 안내를 보인다", async () => {
    const ctx = await openGrid({
      rows: [row(1, { "1": "2026-03-01", "2": "5" })],
      handlers: {
        "POST /datasets/7/rows/paste": () =>
          apiError(409, "PASTE_CONFLICT", "서버 문구", {
            conflicts: [{ row_index: 0, row_id: 1, column_id: 2, kind: "cell", current: "7" }],
            truncated: true,
            total: 2500,
          }),
      },
    });
    paste(ctx, "9", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("일부만 표시됨(전체 2,500건 중 일부)");
  });

  it("WRITE_BUSY는 다시 시도 버튼으로 같은 요청을 다시 보낸다", async () => {
    let busy = true;
    const ctx = await openGrid({
      handlers: { "POST /datasets/7/rows/paste": (call) => (busy ? apiError(503, "WRITE_BUSY", "서버 문구", { retry_after: 1 }) : ctx.fake.handlers["POST /datasets/7/rows/paste"](call)) },
    });
    paste(ctx, "9", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("다른 작업이 진행 중");
    busy = false;
    fireEvent.click(within(result).getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByText(/1행을 고치고 0행을 새로 추가했습니다/)).toBeTruthy();
    expect(writes(ctx.calls)).toHaveLength(2);
  });

  it("정의 버전이 바뀌었으면(DEFINITION_VERSION_MISMATCH) 저장되지 않았음을 알리고 정의를 다시 읽는다", async () => {
    const ctx = await openGrid();
    ctx.fake.detail.def_version = 9;
    paste(ctx, "9", { rowIndex: 0, colId: "2" });
    applyPaste();
    const result = await screen.findByRole("alert", { name: "붙여넣기 결과" });
    expect(result.textContent).toContain("붙여넣기는 저장되지 않았습니다");
    await waitFor(() => expect(ctx.stale).toHaveBeenCalledTimes(1));
  });

  it("확인창에서 Esc나 취소를 누르면 아무것도 보내지 않는다", async () => {
    const ctx = await openGrid();
    paste(ctx, "9", { rowIndex: 0, colId: "2" });
    fireEvent.keyDown(dialog(), { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull());
    paste(ctx, "9");
    fireEvent.click(within(dialog()).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull();
    expect(writes(ctx.calls)).toHaveLength(0);
  });

  describe("서버 호출 전에 막는 경우", () => {
    it("5,001행은 거부한다", async () => {
      const ctx = await openGrid();
      paste(ctx, Array.from({ length: 5001 }, () => "1").join("\n"), { rowIndex: 0, colId: "2" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("5,000행까지");
      expect(writes(ctx.calls)).toHaveLength(0);
    });

    it("요청 1MiB 초과는 거부한다", async () => {
      const ctx = await openGrid();
      const long = "가".repeat(400_000); // UTF-8 1.2MB
      paste(ctx, long, { rowIndex: 0, colId: "3" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("1MiB");
      expect(writes(ctx.calls)).toHaveLength(0);
    });

    it("계산 열에 걸치면 거부한다", async () => {
      const ctx = await openGrid();
      paste(ctx, "a\tb", { rowIndex: 0, colId: "4" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("계산 열에는 붙여넣을 수 없습니다(합계)");
    });

    it("기존 행의 기간(기준 날짜 열)은 붙여넣기로 바꿀 수 없다", async () => {
      const ctx = await openGrid();
      paste(ctx, "2026-09-01\t1", { rowIndex: 0, colId: "1" });
      const alert = await screen.findByRole("alert", { name: "붙여넣기 오류" });
      expect(alert.textContent).toContain("1번째 줄 · 기준일");
      expect(alert.textContent).toContain("기간");
      expect(writes(ctx.calls)).toHaveLength(0);
    });

    it("모호한 숫자·날짜(쉼표·단위·한글 날짜)는 위치와 함께 오류로 표시하고 보내지 않는다", async () => {
      const ctx = await openGrid();
      paste(ctx, "1,234.50\r\n12.5%\r\n7", { rowIndex: 0, colId: "2" });
      const alert = await screen.findByRole("alert", { name: "붙여넣기 오류" });
      expect(alert.textContent).toContain("1번째 줄 · 매출");
      expect(alert.textContent).toContain("2번째 줄 · 매출");
      expect(alert.textContent).not.toContain("3번째 줄");
      expect(writes(ctx.calls)).toHaveLength(0);
      paste(ctx, "2026년 10월 11일", { rowIndex: 0, colId: "1", pinned: "bottom" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("날짜로 읽을 수 없습니다");
    });

    it("NUL이나 닫히지 않은 따옴표는 거부한다", async () => {
      const ctx = await openGrid();
      paste(ctx, "a\u0000b", { rowIndex: 0, colId: "3" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("NUL");
      paste(ctx, '"abc\tdef');
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("따옴표가 닫히지 않아");
      expect(writes(ctx.calls)).toHaveLength(0);
    });

    it("열이 모자라면 거부한다", async () => {
      const ctx = await openGrid();
      paste(ctx, "1\t2\t3", { rowIndex: 0, colId: "4" });
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("열이 모자랍니다");
    });

    it("시작 칸을 고르지 않으면 안내한다", async () => {
      const ctx = await openGrid();
      act(() => ctx.api.clearFocusedCell());
      paste(ctx, "1");
      expect((await screen.findByRole("alert", { name: "붙여넣기 오류" })).textContent).toContain("시작할 칸을 먼저");
    });

    it("기존 행에 걸치는 줄의 칸 수가 모자라면(빈 칸이 지워질 수 있어) 거부한다", async () => {
      const ctx = await openGrid();
      paste(ctx, "1\t가\r\n2", { rowIndex: 0, colId: "2" });
      const alert = await screen.findByRole("alert", { name: "붙여넣기 오류" });
      expect(alert.textContent).toContain("2번째 줄 · 칸 수(1개)");
      for (const item of alert.querySelectorAll("li")) expect(item.textContent?.match(/번째 줄/g)).toHaveLength(1);
    });
  });

  describe("붙여넣기 이벤트 대상(document 수준 리스너)", () => {
    const clip = (data: string) => ({ clipboardData: { getData: (type: string) => (type === "text/plain" ? data : "") } });

    // jsdom 한계: 실제 브라우저의 '글자 선택 후 칸 클릭'(선택된 요소가 paste 대상이 됨)을 만들 수 없다.
    // 여기서는 칸에 DOM 포커스를 두고, paste 이벤트의 대상을 그리드 밖 요소(안내 문단)로 보내 같은 상황을 흉내 낸다.
    function focusCell(ctx: Ctx, rowIndex: number, colId: string) {
      act(() => ctx.api.setFocusedCell(rowIndex, colId));
      const target = cell(ctx.grid, "r1", colId);
      act(() => target.focus());
      expect(ctx.grid.contains(document.activeElement)).toBe(true);
    }

    it("그리드 안에 포커스가 있으면 이벤트 대상이 그리드 밖의 선택된 글자여도 붙여넣기가 동작한다", async () => {
      const ctx = await openGrid();
      focusCell(ctx, 2, "2");
      const help = document.querySelector(".entry-help") as HTMLElement;
      expect(ctx.grid.contains(help)).toBe(false);
      const notPrevented = fireEvent.paste(help, clip("5"));
      expect(notPrevented).toBe(false); // 가로챘다
      expect(dialog().textContent).toContain("기존 행 1개");
    });

    it("그리드 밖 입력창(다른 폼)의 붙여넣기는 가로채지 않는다", async () => {
      const ctx = await openGrid();
      focusCell(ctx, 2, "2");
      const outside = document.createElement("input");
      document.body.appendChild(outside);
      outside.focus();
      const notPrevented = fireEvent.paste(outside, clip("x\ty"));
      expect(notPrevented).toBe(true);
      expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull();
      expect(screen.queryByRole("alert", { name: "붙여넣기 오류" })).toBeNull();
      const area = document.createElement("textarea");
      document.body.appendChild(area);
      expect(fireEvent.paste(area, clip("x"))).toBe(true);
      outside.remove();
      area.remove();
    });

    it("그리드에 포커스가 없고 대상도 그리드 밖이면 처리하지 않는다", async () => {
      const ctx = await openGrid();
      act(() => ctx.api.setFocusedCell(2, "2"));
      (document.activeElement as HTMLElement | null)?.blur();
      const help = document.querySelector(".entry-help") as HTMLElement;
      expect(fireEvent.paste(help, clip("5"))).toBe(true);
      expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull();
    });

    it("그리드가 사라지면 리스너도 사라진다", async () => {
      const ctx = await openGrid();
      focusCell(ctx, 2, "2");
      cleanup();
      expect(fireEvent.paste(document.body, clip("5"))).toBe(true);
    });
  });

  it("편집 중인 칸에서는 브라우저 기본 붙여넣기를 그대로 둔다(그리드가 가로채지 않음)", async () => {
    const ctx = await openGrid();
    const index = ctx.api.getRenderedNodes().find((n) => n.data?.key === "r1")?.rowIndex as number;
    act(() => {
      ctx.api.setFocusedCell(index, "3");
      ctx.api.startEditingCell({ rowIndex: index, colKey: "3" });
    });
    const input = await within(cell(ctx.grid, "r1", "3")).findByRole("textbox");
    const notPrevented = fireEvent.paste(input, { clipboardData: { getData: () => "x\ty" } });
    expect(notPrevented).toBe(true);
    expect(screen.queryByRole("dialog", { name: "붙여넣기 확인" })).toBeNull();
    act(() => ctx.api.stopEditing(true));
  });
});


describe("계산 열 표시 자릿수(결정 2026-10-12): 칸은 소수 최대 6자리, 전체 값은 툴팁과 복사", () => {
  const LONG: Row[] = [
    row(1, { "1": "2026-03-01", "2": "0.1234567890", "3": null, "4": null, "5": "1234.5000000" }),
    row(2, { "1": "2026-02-01", "2": "3", "3": null, "4": null, "5": "-0.0000004" }),
    row(3, { "1": "2026-01-01", "2": null, "3": null, "4": null, "5": "12345678901234567890123456789012345678" }),
    row(4, { "1": "2025-12-01", "2": null, "3": null, "4": null, "5": "2.718281828459" }),
  ];
  const title = (grid: HTMLElement, rowKey: string, colId: string) => cell(grid, rowKey, colId).querySelector(".cell-text")?.getAttribute("title");

  it("칸에는 줄인 값이, 6자리를 넘게 잘린 칸의 툴팁에는 전체 값이 있다", async () => {
    const { grid } = await openGrid({ rows: LONG });
    expect(text(grid, "r1", "5")).toBe("1,234.5");
    expect(title(grid, "r1", "5")).not.toContain("전체 값"); // 끝자리 0만 잘렸으면 툴팁 없음(기존 안내)
    expect(text(grid, "r2", "5")).toBe("0"); // -0 아님
    expect(title(grid, "r2", "5")).toBe("전체 값: -0.0000004");
    expect(text(grid, "r3", "5")).toBe("12,345,678,901,234,567,890,123,456,789,012,345,678");
    expect(text(grid, "r4", "5")).toBe("2.718282");
    expect(title(grid, "r4", "5")).toBe("전체 값: 2.718281828459");
  });

  it("입력 열의 표시는 그대로(깎지 않음), 계산 열 폭은 190px 정의를 유지한다", async () => {
    const { grid } = await openGrid({ rows: LONG });
    expect(text(grid, "r1", "2")).toBe("0.1234567890");
    expect(text(grid, "r2", "2")).toBe("3.00");
    expect(cell(grid, "r1", "5").style.width).toBe("190px");
  });

  async function focusCell(api: GridApi<GridRow>, rowKey: string, colId: string) {
    const index = api.getRenderedNodes().find((n) => n.data?.key === rowKey)?.rowIndex as number;
    act(() => api.setFocusedCell(index, colId));
    await sleep(10);
  }

  // jsdom에는 ClipboardEvent/DataTransfer가 없다. 일반 Event에 clipboardData 모양만 붙여 보내므로, 실제 브라우저의 클립보드 기록은 확인하지 못한다.
  function copyEvent(target: Element) {
    const data: Record<string, string> = {};
    const event = new Event("copy", { bubbles: true, cancelable: true }) as Event & { clipboardData: { setData: (t: string, v: string) => void } };
    event.clipboardData = { setData: (type, value) => void (data[type] = value) };
    act(() => void target.dispatchEvent(event));
    return { event, data };
  }

  it("계산 칸을 고르고 복사하면 쉼표·반올림 없는 전체 값이 text/plain에 들어간다", async () => {
    const { grid, api } = await openGrid({ rows: LONG });
    for (const [key, full] of [["r4", "2.718281828459"], ["r2", "-0.0000004"], ["r3", "12345678901234567890123456789012345678"], ["r1", "1234.5000000"]]) {
      await focusCell(api, key, "5");
      const { event, data } = copyEvent(cell(grid, key, "5"));
      expect(data["text/plain"]).toBe(full);
      expect(event.defaultPrevented).toBe(true);
    }
  });

  it("입력 열 칸·오류 칸·빈 계산 칸은 가로채지 않는다(브라우저 기본 동작)", async () => {
    const { grid, api } = await openGrid({ rows: [...LONG, row(5, { "1": "2025-11-01", "2": "1" }, { "5": "E1" }), row(6, { "1": "2025-10-01", "2": "1", "5": null })] });
    for (const [key, col] of [["r1", "2"], ["r5", "5"], ["r6", "5"]]) {
      await focusCell(api, key, col);
      const { event, data } = copyEvent(cell(grid, key, col));
      expect(data["text/plain"]).toBeUndefined();
      expect(event.defaultPrevented).toBe(false);
    }
  });

  it("그리드 밖에서 일어난 복사는 가로채지 않는다", async () => {
    const { api } = await openGrid({ rows: LONG });
    await focusCell(api, "r4", "5");
    (document.activeElement as HTMLElement | null)?.blur();
    const outside = document.body.appendChild(document.createElement("p"));
    const { event, data } = copyEvent(outside);
    expect(data["text/plain"]).toBeUndefined();
    expect(event.defaultPrevented).toBe(false);
    outside.remove();
  });

  it("복사해도 서버로 가는 요청이 없다(표시만 바뀜)", async () => {
    const { grid, api, calls } = await openGrid({ rows: LONG });
    await focusCell(api, "r4", "5");
    copyEvent(cell(grid, "r4", "5"));
    expect(writes(calls)).toHaveLength(0);
  });
});
