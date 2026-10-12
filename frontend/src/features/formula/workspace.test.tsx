import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import type { DatasetDetail } from "../dataset/types";
import type { Row } from "../entry/types";
import { resetCatalogCache } from "./catalog";
import { CHECK_OK, makeFormulaFake, salesDetail, type FormulaFake } from "./test-server";
import type { FormulaView } from "./types";

/**
 * S4 작업공간 안의 수식 열 화면 시험(단위 1d): 계산 열 추가·수정 흐름, 수식 보기, 읽기 전용, 입력 그리드의 계산 열.
 * 수식 편집기 자체의 입력 동작은 editor.test.tsx에서 시험한다. 여기서는 작업공간과 이어지는 저장 호출 본문,
 * 정의 버전 충돌, 그리드 갱신을 본다. 실제 백엔드와 브라우저 레이아웃은 쓰지 않는다(Playwright 단계 몫).
 */
const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
  resetCatalogCache();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const ROWS: Row[] = [
  { row_id: 3, cells: { "1": "2026-03-01", "2": "100", "3": "40", "4": null, "5": "60" } },
  { row_id: 2, cells: { "1": "2026-02-01", "2": "50", "3": "0", "4": null, "5": null }, errors: { "5": "E1" } },
  { row_id: 1, cells: { "1": "2026-01-01", "2": null, "3": "10", "4": null, "5": null } },
];

interface Opened {
  fake: FormulaFake;
  calls: RecordedCall[];
}

async function openWorkspace(detail: DatasetDetail = salesDetail(), rows: Row[] = ROWS, handlers: Record<string, Handler> = {}): Promise<Opened> {
  const fake = makeFormulaFake(detail, rows);
  const { calls } = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), ...fake.handlers, ...handlers });
  render(<App router={createTestRouter(BASE, `${BASE}/datasets/${detail.id}`)} />);
  await screen.findByRole("region", { name: "데이터셋 정보" });
  return { fake, calls };
}

const inspector = () => screen.getByRole("complementary", { name: "Inspector" });
const selectColumn = (name: RegExp) => fireEvent.click(within(screen.getByRole("region", { name: "열 목록" })).getByRole("button", { name }));
const of = (calls: RecordedCall[], method: string, suffix: string) => calls.filter((c) => c.method === method && c.path.endsWith(suffix));
const area = () => within(inspector()).getByLabelText("수식") as HTMLTextAreaElement;
const typeExpr = (value: string) => fireEvent.change(area(), { target: { value } });

describe("계산 열 추가(D4)", () => {
  it("저장 요청에 expected_version·이름·수식이 실리고, 저장되면 새 열이 선택되어 수식 보기가 나온다", async () => {
    const { fake, calls } = await openWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "계산 열 추가" }));
    const form = within(inspector()).getByRole("form", { name: "계산 열 추가" });
    fireEvent.change(within(form).getByLabelText("계산 열 이름"), { target: { value: "이익률" } });
    typeExpr("[매출] / [비용]");
    await waitFor(() => expect((within(form).getByRole("button", { name: "계산 열 추가" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(form).getByRole("button", { name: "계산 열 추가" }));
    await waitFor(() => expect(of(calls, "POST", "/datasets/7/formulas")).toHaveLength(1));
    expect(of(calls, "POST", "/datasets/7/formulas")[0].body).toEqual({ expected_version: 3, display_name: "이익률", expression: "[매출] / [비용]" });
    expect((await within(inspector()).findByRole("status")).textContent).toBe("계산 열을 추가했습니다.");
    // 새 열이 선택되고 수식 보기가 열린다
    expect((await within(inspector()).findByTestId("formula-text")).textContent).toBe("[매출] / [비용]");
    expect(fake.state.columns.map((c) => c.display_name)).toContain("이익률");
    // 계산 열 값이 바뀌므로 그리드가 행을 다시 읽는다(처음 1회 + 저장 뒤)
    await waitFor(() => expect(of(calls, "GET", "/datasets/7/rows").length).toBeGreaterThanOrEqual(2));
    const grid = screen.getByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(Array.from(grid.querySelectorAll(".header-formula")).map((h) => h.textContent?.trim())).toContain("이익률"));
  });

  it("정의 권한이 없으면 '계산 열 추가' 버튼이 없다", async () => {
    await openWorkspace(salesDetail({ permissions: { define: false, enter: true } }));
    expect(screen.queryByRole("button", { name: "계산 열 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: "열 추가" })).toBeNull();
  });
});

describe("수식 보기(D6)와 수식 고치기(D5)", () => {
  const VIEW: FormulaView = {
    column_id: 5,
    text: "[매출] - [비용] + SUMTAG(\"수입\")",
    refs: [
      { column_id: 2, display_name: "매출", kind: "raw" },
      { column_id: 6, display_name: "보너스", kind: "formula" },
    ],
    tag_columns: ["매출", "보조 매출"],
    error_count: 12,
  };

  it("계산 열을 고르면 수식 보기가 먼저 나오고 읽기 전용 열 정보는 접힌 '열 정보' 구역에 있다", async () => {
    const { fake } = await openWorkspace();
    fake.views[5] = VIEW;
    selectColumn(/^이익/);
    const view = await within(inspector()).findByRole("region", { name: "수식 보기" });
    const info = inspector().querySelector("details.column-info") as HTMLDetailsElement;
    expect(info).not.toBeNull();
    expect(info.open).toBe(false);
    expect(info.querySelector("summary")?.textContent).toBe("열 정보");
    expect(view.compareDocumentPosition(info) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("계산 열을 고르면 현재 열 이름으로 풀어 쓴 수식·쓰는 열·태그 열·오류 칸 수가 읽기 전용으로 보인다", async () => {
    const { fake, calls } = await openWorkspace();
    fake.views[5] = VIEW;
    selectColumn(/^이익/);
    const view = await within(inspector()).findByRole("region", { name: "수식 보기" });
    expect(within(view).getByTestId("formula-text").textContent).toBe(VIEW.text);
    expect(of(calls, "GET", "/datasets/7/formulas/5")).toHaveLength(1);
    expect(within(view).getByTestId("formula-refs").textContent).toBe("매출 (입력 열), 보너스 (계산 열)");
    expect(within(view).getByTestId("formula-tag-columns").textContent).toBe("매출, 보조 매출");
    const errors = within(view).getByTestId("formula-error-count");
    expect(errors.textContent).toContain("12개");
    expect(within(errors).getByRole("link", { name: "점검 화면에서 보기" }).getAttribute("href")).toBe(`${BASE}/checks?dataset=7&column=5`);
    // 수식 보기는 쓰기가 없다
    expect(view.querySelector("textarea, input")).toBeNull();
  });

  it("오류 칸이 없고 태그 열이 없으면 '없음'만 보인다", async () => {
    await openWorkspace();
    selectColumn(/^이익/);
    const view = await within(inspector()).findByRole("region", { name: "수식 보기" });
    expect(within(view).getByTestId("formula-error-count").textContent).toBe("없음");
    expect(within(view).queryByTestId("formula-tag-columns")).toBeNull();
  });

  it("수식 보기 실패는 쉬운 문구와 다시 불러오기", async () => {
    let n = 0;
    await openWorkspace(salesDetail(), ROWS, { "GET /datasets/7/formulas/5": () => (n++ === 0 ? apiError(503, "SERVICE_UNAVAILABLE") : json(200, { column_id: 5, text: "1", refs: [], tag_columns: [], error_count: 0 })) });
    selectColumn(/^이익/);
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("일시적으로 응답하지 못합니다");
    fireEvent.click(within(inspector()).getByRole("button", { name: "다시 불러오기" }));
    expect((await within(inspector()).findByTestId("formula-text")).textContent).toBe("1");
  });

  it("정의 담당자는 '수식 고치기'로 편집기를 열고 시작값은 수식 보기의 text다", async () => {
    const { calls } = await openWorkspace();
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    expect(area().value).toBe("[매출] - [비용]");
    // 같은 수식이면 저장할 수 없다
    expect((within(inspector()).getByRole("button", { name: "수식 저장" }) as HTMLButtonElement).disabled).toBe(true);
    typeExpr("[매출] - [비용] - 1");
    await waitFor(() => expect((within(inspector()).getByRole("button", { name: "수식 저장" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    await waitFor(() => expect(of(calls, "PUT", "/datasets/7/formulas/5")).toHaveLength(1));
    expect(of(calls, "PUT", "/datasets/7/formulas/5")[0].body).toEqual({ expected_version: 3, expression: "[매출] - [비용] - 1" });
    expect((await within(inspector()).findByText("수식을 저장했습니다.")).getAttribute("role")).toBe("status");
    // 저장한 수식으로 수식 보기가 새로 읽힌다
    await waitFor(() => expect(within(inspector()).getByTestId("formula-text").textContent).toBe("[매출] - [비용] - 1"));
    expect(of(calls, "GET", "/datasets/7/rows").length).toBeGreaterThanOrEqual(2); // 그리드 다시 읽기
  });

  it("결과 종류가 바뀌면(result_type_changed) 저장된 차트 확인 안내", async () => {
    await openWorkspace(salesDetail(), ROWS, {
      "PUT /datasets/7/formulas/5": () => json(200, { column: salesDetail().columns[4], def_version: 4, result_type_changed: true }),
    });
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    typeExpr('"가" & "나"');
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    expect((await within(inspector()).findByText(/결과 종류가 바뀌었습니다/)).textContent).toContain("저장된 차트가 있으면");
  });

  it("다른 사람이 먼저 정의를 바꿨으면(409) 최신 정의를 다시 읽고 입력한 수식은 남긴다. 다시 저장하면 새 버전으로 보낸다", async () => {
    const { fake, calls } = await openWorkspace();
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    typeExpr("[매출] * 2");
    fake.state.def_version = 4; // 다른 사람이 먼저 정의를 바꿈
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    expect((await within(inspector()).findByText(/다른 사람이 먼저 바꿨습니다/)).textContent).toContain("최신 내용을 다시 읽었습니다");
    expect(of(calls, "PUT", "/datasets/7/formulas/5")[0].body).toMatchObject({ expected_version: 3 });
    await waitFor(() => expect(of(calls, "GET", "/datasets/7").length).toBeGreaterThanOrEqual(2));
    expect(area().value).toBe("[매출] * 2");
    await waitFor(() => expect(screen.getByRole("region", { name: "데이터셋 정보" }).textContent).toContain("4")); // 정의 버전
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    await waitFor(() => expect(of(calls, "PUT", "/datasets/7/formulas/5")).toHaveLength(2));
    expect(of(calls, "PUT", "/datasets/7/formulas/5")[1].body).toMatchObject({ expected_version: 4 });
  });

  it("FORMULA_CIRCULAR(422)는 순환 경로를 열 이름으로 보여 준다", async () => {
    await openWorkspace(salesDetail(), ROWS, {
      "PUT /datasets/7/formulas/5": () => apiError(422, "FORMULA_CIRCULAR", "서버", { path: ["이익", "보너스", "이익"] }),
    });
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    typeExpr("[보너스]");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    expect((await within(inspector()).findByText(/순환 경로/)).textContent).toContain("이익 → 보너스 → 이익");
  });

  it("FORMULA_INVALID(422)는 입력창 아래 오류 위치로 보인다", async () => {
    await openWorkspace(salesDetail(), ROWS, {
      "PUT /datasets/7/formulas/5": () => apiError(422, "FORMULA_INVALID", "서버", { errors: [{ code: "X", message: "알 수 없는 열 [가나]입니다.", start: 0, end: 4 }] }),
    });
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    typeExpr("[가나]");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    const box = await within(inspector()).findByRole("alert", { name: "수식 오류" });
    expect(box.textContent).toContain("알 수 없는 열 [가나]입니다.");
    expect(box.querySelector("mark")?.textContent).toBe("[가나]");
  });

  it("DEFINITION_BUSY(503)는 잠시 뒤 다시 저장하라는 안내", async () => {
    await openWorkspace(salesDetail(), ROWS, {
      "PUT /datasets/7/formulas/5": () => apiError(503, "DEFINITION_BUSY", "서버", { retry_after: 3 }),
    });
    selectColumn(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
    typeExpr("[매출]");
    fireEvent.click(within(inspector()).getByRole("button", { name: "수식 저장" }));
    expect((await within(inspector()).findByText(/다른 작업이 진행 중입니다/)).textContent).toContain("약 3초 뒤");
  });

  it("정의 권한이 없으면 수식 보기만 있고 편집기·고치기 버튼·검사 호출이 없다", async () => {
    const { calls } = await openWorkspace(salesDetail({ permissions: { define: false, enter: true } }));
    selectColumn(/^이익/);
    expect((await within(inspector()).findByTestId("formula-text")).textContent).toBe("[매출] - [비용]");
    expect(within(inspector()).getByTestId("formula-readonly").textContent).toContain("정의 담당자만");
    expect(within(inspector()).queryByRole("button", { name: "수식 고치기" })).toBeNull();
    expect(within(inspector()).queryByLabelText("수식")).toBeNull();
    expect(calls.filter((c) => c.method === "POST" && c.path.includes("/formulas"))).toHaveLength(0);
  });
});

describe("입력 그리드의 계산 열", () => {
  const cell = (grid: HTMLElement, rowKey: string, colId: string) => grid.querySelector<HTMLElement>(`[row-id="${rowKey}"] [col-id="${colId}"]`) as HTMLElement;

  it("오류 칸은 D1 문구로 설명되고 코드가 보이며, 값 없는 칸은 빗금 빈 칸으로 오류와 구별된다", async () => {
    const { calls } = await openWorkspace();
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(grid.querySelector('[row-id="r3"]')).toBeTruthy());
    await waitFor(() => expect(calls.some((c) => c.path === "/formulas/functions")).toBe(true));
    await waitFor(() => expect(cell(grid, "r2", "5").querySelector(".cell-text")?.getAttribute("title")).toBe("계산 오류(E1): 서버 문구: 0으로 나눌 수 없습니다."));
    const error = cell(grid, "r2", "5");
    expect(error.classList.contains("cell-error")).toBe(true);
    expect(error.querySelector(".cell-value")?.textContent).toBe("오류");
    expect(error.querySelector(".cell-errcode")?.textContent?.trim()).toBe("E1");
    expect(error.querySelector('[aria-label^="계산 오류 E1"]')?.getAttribute("aria-label")).toContain("서버 문구");
    const blank = cell(grid, "r1", "5"); // 입력 값이 비어 결과도 빈 값 (오류 아님)
    expect(blank.classList.contains("cell-blank")).toBe(true);
    expect(blank.classList.contains("cell-error")).toBe(false);
    expect(blank.querySelector('[aria-label="빈 칸"]')).not.toBeNull();
    const value = cell(grid, "r3", "5");
    expect(value.classList.contains("cell-formula")).toBe(true);
    expect(value.querySelector(".cell-value")?.textContent).toBe("60");
  });

  it("D1을 받지 못해도 기본 문구로 오류 칸을 설명한다", async () => {
    await openWorkspace(salesDetail(), ROWS, { "GET /formulas/functions": () => apiError(503, "SERVICE_UNAVAILABLE") });
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    await waitFor(() => expect(grid.querySelector('[row-id="r2"]')).toBeTruthy());
    expect(cell(grid, "r2", "5").querySelector(".cell-text")?.getAttribute("title")).toBe("계산 오류(E1): 0으로 나누어 계산할 수 없습니다.");
  });

  it("계산 열 머리글은 구별 표시(header-formula)이고 입력 열은 아니다", async () => {
    await openWorkspace();
    const grid = await screen.findByRole("group", { name: "입력 그리드 표" });
    const headers = Array.from(await within(grid).findAllByRole("columnheader"));
    const profit = headers.find((h) => h.textContent?.includes("이익")) as HTMLElement;
    const sales = headers.find((h) => h.textContent?.includes("매출")) as HTMLElement;
    expect(profit.classList.contains("header-formula")).toBe(true);
    expect(sales.classList.contains("header-formula")).toBe(false);
    expect(profit.getAttribute("title") ?? profit.textContent).toBeTruthy();
  });

  it("계산 열이 없는 데이터셋은 D1을 읽지 않는다", async () => {
    const detail = salesDetail();
    detail.columns = detail.columns.filter((c) => c.kind === "raw");
    const { calls } = await openWorkspace(detail, []);
    await screen.findByRole("group", { name: "입력 그리드 표" });
    expect(calls.some((c) => c.path === "/formulas/functions")).toBe(false);
  });
});

it("검사 호출 본문에 column_id가 실린다(수정 중 순환 기준)", async () => {
  const { calls } = await openWorkspace(salesDetail(), ROWS, { "POST /datasets/7/formulas/check": () => json(200, CHECK_OK) });
  selectColumn(/^이익/);
  await within(inspector()).findByTestId("formula-text");
  fireEvent.click(within(inspector()).getByRole("button", { name: "수식 고치기" }));
  typeExpr("[매출] + 1");
  await waitFor(() => expect(of(calls, "POST", "/formulas/check")).toHaveLength(1), { timeout: 3000 });
  expect(of(calls, "POST", "/formulas/check")[0].body).toEqual({ expression: "[매출] + 1", column_id: 5 });
});
