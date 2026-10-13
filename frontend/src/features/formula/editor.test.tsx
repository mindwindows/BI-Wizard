import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api";
import { apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import type { Column } from "../dataset/types";
import { resetCatalogCache } from "./catalog";
import { FormulaEditor, type SaveInput, type SaveOutcome } from "./FormulaEditor";
import { CHECK_OK, PREVIEW_OK, SALES, makeFormulaFake } from "./test-server";
import type { CheckResult, PreviewResult } from "./types";

/**
 * 수식 편집기 시험(단위 1d). fetch는 계약(05 D1~D3)대로 응답하는 가짜 서버(test-server.ts)로 대신한다.
 * 디바운스 시간은 props로 줄여(20~30ms) 실제 타이머로 시험한다. 실제 백엔드·브라우저 레이아웃은 쓰지 않는다.
 */
const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  resetCatalogCache();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const sleep = (ms: number) => act(() => new Promise<void>((resolve) => setTimeout(resolve, ms)));

interface MountOptions {
  handlers?: Record<string, Handler>;
  editing?: Column | null;
  initial?: string;
  save?: (input: SaveInput) => Promise<SaveOutcome>;
  busyRetryMs?: number;
}

function mount(options: MountOptions = {}) {
  const fake = makeFormulaFake();
  const { calls, fetchMock } = installFetch({ ...fake.handlers, ...options.handlers });
  const save = vi.fn(options.save ?? (async () => ({ ok: true }) as SaveOutcome));
  render(
    <FormulaEditor
      datasetId={7}
      columns={SALES}
      editing={options.editing ?? null}
      initialExpression={options.initial ?? ""}
      save={save}
      checkDelayMs={20}
      previewDelayMs={20}
      busyRetryMs={options.busyRetryMs ?? 30}
    />,
  );
  return { calls, fetchMock, save };
}

const box = () => screen.getByLabelText("수식") as HTMLTextAreaElement;
const of = (calls: RecordedCall[], suffix: string) => calls.filter((c) => c.path.endsWith(suffix));

/** 수식 입력창에 글자를 넣고 커서를 옮긴다(입력 이벤트 + 키 뗌). */
function typeExpr(value: string, caret: number = value.length) {
  const area = box();
  fireEvent.change(area, { target: { value } });
  area.setSelectionRange(caret, caret);
  fireEvent.keyUp(area, { key: "x" });
}

describe("열 이름 칩", () => {
  it("칩을 누르면 커서 위치에 [열 이름]이 들어가고 커서는 그 뒤에 놓인다", async () => {
    mount();
    typeExpr("1 + ");
    fireEvent.click(screen.getByRole("button", { name: "매출" }));
    expect(box().value).toBe("1 + [매출]");
    expect(box().selectionStart).toBe(8);
    fireEvent.click(screen.getByRole("button", { name: "비용" }));
    expect(box().value).toBe("1 + [매출][비용]");
  });

  it("선택한 글자는 칩으로 바뀐다", () => {
    mount();
    typeExpr("1 + x");
    box().setSelectionRange(4, 5);
    fireEvent.click(screen.getByRole("button", { name: "비용" }));
    expect(box().value).toBe("1 + [비용]");
  });

  it("고치는 계산 열 자신은 칩에 없다(자기 참조는 순환)", () => {
    mount({ editing: SALES[4], initial: "[매출]" });
    const group = screen.getByRole("group", { name: /열 이름 칩/ });
    expect(within(group).queryByRole("button", { name: "이익" })).toBeNull();
    expect(within(group).getByRole("button", { name: "매출" })).toBeTruthy();
  });
});

describe("함수·열 자동완성", () => {
  it("함수 이름을 치면 후보가 뜨고 화살표와 Enter로 고른다", async () => {
    mount();
    await screen.findByRole("group", { name: /열 이름 칩/ });
    // D1 함수 목록은 비동기로 도착한다.
    typeExpr("1 + RO");
    const list = await screen.findByRole("listbox", { name: "자동완성 후보" });
    expect(within(list).getAllByRole("option").map((o) => o.querySelector("strong")?.textContent)).toEqual(["ROUND", "ROUNDUP"]);
    expect(screen.getByTestId("suggest-help").textContent).toContain("반올림");
    expect(screen.getByTestId("suggest-help").textContent).toContain("엑셀과 차이: 자릿수는 상수만");
    fireEvent.keyDown(box(), { key: "ArrowDown" });
    expect(within(list).getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
    expect(box().getAttribute("aria-activedescendant")).toBe(within(list).getAllByRole("option")[1].id);
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(box().value).toBe("1 + ROUNDUP(");
    expect(box().selectionStart).toBe(12);
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("[ 후보는 8개를 넘어도 모두 목록에 있고 안내가 나오며 키보드로 끝까지 간다", async () => {
    const many: Column[] = Array.from({ length: 12 }, (_, i) => ({ ...SALES[0], id: 100 + i, display_name: `열${i + 1}`, kind: "raw" }) as Column);
    const fake = makeFormulaFake();
    installFetch({ ...fake.handlers });
    render(<FormulaEditor datasetId={7} columns={many} editing={null} initialExpression="" save={vi.fn(async () => ({ ok: true }) as SaveOutcome)} checkDelayMs={20} previewDelayMs={20} />);
    typeExpr("[");
    const list = await screen.findByRole("listbox", { name: "자동완성 후보" });
    expect(within(list).getAllByRole("option")).toHaveLength(12);
    expect(screen.getByTestId("suggest-more").textContent).toContain("12개");
    for (let i = 0; i < 11; i++) fireEvent.keyDown(box(), { key: "ArrowDown" });
    expect(within(list).getAllByRole("option")[11].getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(box().value).toBe("[열12]");
  });

  it("Tab으로도 넣고, Esc로 닫으면 같은 자리에서는 다시 열리지 않는다", async () => {
    mount();
    typeExpr("SU");
    await screen.findByRole("listbox");
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    typeExpr("SUM");
    await screen.findByRole("listbox");
    fireEvent.keyDown(box(), { key: "Tab" });
    expect(box().value).toBe("SUM(");
  });

  it("↑로 마지막 후보로 돌아가고, 마우스로 눌러도 넣어진다", async () => {
    mount();
    typeExpr("ROU");
    const list = await screen.findByRole("listbox");
    fireEvent.keyDown(box(), { key: "ArrowUp" });
    expect(within(list).getAllByRole("option")[1].getAttribute("aria-selected")).toBe("true");
    fireEvent.click(within(list).getAllByRole("option")[0]);
    expect(box().value).toBe("ROUND(");
  });

  it("[ 를 치면 열 이름 후보가 뜨고 고르면 [이름]이 된다(계산 열 표시)", async () => {
    mount();
    typeExpr("1 + [");
    const list = await screen.findByRole("listbox");
    expect(within(list).getAllByRole("option")).toHaveLength(SALES.length); // 이 시험은 새 계산 열이라 자기 제외 없음
    typeExpr("1 + [비", 6);
    expect(within(await screen.findByRole("listbox")).getAllByRole("option")).toHaveLength(1);
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(box().value).toBe("1 + [비용]");
  });

  it('SUMTAG("  안에서는 열 태그 후보가 뜬다', async () => {
    mount();
    typeExpr('SUMTAG("');
    const list = await screen.findByRole("listbox");
    expect(within(list).getByRole("option").textContent).toContain("수입");
    fireEvent.keyDown(box(), { key: "Enter" });
    expect(box().value).toBe('SUMTAG("수입"');
  });

  it("함수 목록(D1)을 못 읽어도 열 이름 칩과 [ 자동완성은 동작하고 도움말에서 다시 불러온다", async () => {
    let attempts = 0;
    mount({
      handlers: {
        "GET /formulas/functions": () => {
          attempts += 1;
          return attempts === 1 ? apiError(503, "SERVICE_UNAVAILABLE") : json(200, { functions: [{ name: "ROUND", signature: "ROUND(수, 자릿수)", returns: "숫자", help_ko: "반올림", excel_diff: "" }], cell_errors: {} });
        },
      },
    });
    fireEvent.click(screen.getByText("수식 도움말"));
    expect((await screen.findByText(/함수 목록을 불러오지 못했습니다/)).textContent).toContain("열 이름 자동완성과 칩은 쓸 수 있습니다");
    typeExpr("[");
    expect(await screen.findByRole("listbox")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByText("ROUND(수, 자릿수)")).toBeTruthy();
  });

  it("수식 도움말: 빈 칸은 0이 아님 등 규칙 문구와 함수별 엑셀 차이", async () => {
    mount();
    fireEvent.click(screen.getByText("수식 도움말"));
    expect(screen.getByText(/비어 있는 칸은 0이 아닙니다/)).toBeTruthy();
    expect(screen.getByText(/글자 비교는 대문자·소문자를 구별하지 않습니다/)).toBeTruthy();
    expect(await screen.findByText(/엑셀과 차이: 빈 칸이 있으면 결과도 빈 값입니다/)).toBeTruthy();
  });
});

describe("수식 검사(D2)와 오류 위치", () => {
  it("입력이 멈춘 뒤 한 번만 검사한다(디바운스). 새 열이면 column_id를 보내지 않는다", async () => {
    const { calls } = mount();
    typeExpr("1");
    typeExpr("1 +");
    typeExpr("1 + 2");
    await waitFor(() => expect(of(calls, "/formulas/check")).toHaveLength(1));
    expect(of(calls, "/formulas/check")[0].body).toEqual({ expression: "1 + 2" });
    await sleep(120);
    expect(of(calls, "/formulas/check")).toHaveLength(1);
  });

  it("고치는 열이면 column_id를 보낸다", async () => {
    const { calls } = mount({ editing: SALES[4], initial: "[매출]" });
    typeExpr("[매출] - [비용]");
    await waitFor(() => expect(of(calls, "/formulas/check")).toHaveLength(1));
    expect(of(calls, "/formulas/check")[0].body).toEqual({ expression: "[매출] - [비용]", column_id: 5 });
  });

  it("비어 있으면 검사하지 않고 안내만 보인다", async () => {
    const { calls } = mount();
    expect(screen.getByTestId("check-status").textContent).toContain("수식을 입력하면");
    await sleep(80);
    expect(of(calls, "/formulas/check")).toHaveLength(0);
    expect(of(calls, "/formulas/preview")).toHaveLength(0);
  });

  const BAD: CheckResult = {
    ok: false,
    result_type: null,
    refs: [],
    errors: [{ code: "MISSING_OPERAND", message: "'*' 앞에 계산할 값이 필요합니다.", start: 4, end: 5 }],
  };

  it("오류는 쉬운 말 문구와 입력창 안 위치 표시로 보이고 저장은 막힌다", async () => {
    const { calls } = mount({ handlers: { "POST /datasets/7/formulas/check": () => json(200, BAD) } });
    typeExpr("1 + * 2");
    const alert = await screen.findByRole("alert", { name: "수식 오류" });
    expect(alert.textContent).toContain("'*' 앞에 계산할 값이 필요합니다.");
    const marked = within(alert).getByLabelText("오류 위치 표시");
    expect(marked.querySelector("mark")?.textContent).toBe("*");
    expect(marked.textContent).toBe("1 + * 2");
    expect(box().getAttribute("aria-invalid")).toBe("true");
    expect(box().getAttribute("aria-describedby")).toBe(alert.id);
    expect(screen.getByTestId("check-status").textContent).toContain("고칠 곳이 있습니다");
    expect((screen.getByRole("button", { name: "계산 열 추가" }) as HTMLButtonElement).disabled).toBe(true);
    // 오류가 있으면 미리보기를 자동으로 부르지 않는다
    await sleep(100);
    expect(of(calls, "/formulas/preview")).toHaveLength(0);
  });

  it("'위치 보기'는 입력창의 해당 글자를 선택한다", async () => {
    mount({ handlers: { "POST /datasets/7/formulas/check": () => json(200, BAD) } });
    typeExpr("1 + * 2");
    fireEvent.click(await screen.findByRole("button", { name: "위치 보기" }));
    expect([box().selectionStart, box().selectionEnd]).toEqual([4, 5]);
    expect(document.activeElement).toBe(box());
  });

  it("수식을 고치면 이전 오류 표시는 사라지고 새 검사 결과가 나온다", async () => {
    let n = 0;
    mount({ handlers: { "POST /datasets/7/formulas/check": () => json(200, (n += 1) === 1 ? BAD : CHECK_OK) } });
    typeExpr("1 + * 2");
    await screen.findByRole("alert", { name: "수식 오류" });
    typeExpr("1 + 2");
    await waitFor(() => expect(screen.queryByRole("alert", { name: "수식 오류" })).toBeNull());
    await waitFor(() => expect(screen.getByTestId("check-status").textContent).toContain("문제가 없습니다. 결과는 숫자입니다."));
  });

  it("검사 호출이 실패하면 확인하지 못했다는 안내(저장은 막지 않음)", async () => {
    mount({ handlers: { "POST /datasets/7/formulas/check": () => apiError(503, "SERVICE_UNAVAILABLE") } });
    typeExpr("1");
    await waitFor(() => expect(screen.getByTestId("check-status").textContent).toContain("확인하지 못했습니다"));
  });

  it("글자 위치가 수식 밖이어도 깨지지 않는다", async () => {
    mount({
      handlers: { "POST /datasets/7/formulas/check": () => json(200, { ...BAD, errors: [{ code: "X", message: "끝이 비었습니다.", start: 99, end: 99 }] }) },
    });
    typeExpr("1 +");
    const marked = (await screen.findByRole("alert", { name: "수식 오류" })).querySelector("pre") as HTMLElement;
    expect(marked.querySelector("mark")).toBeTruthy();
  });
});

describe("미리보기(D3)", () => {
  it("검사가 통과하면 자동으로 20행 미리보기를 부르고 값·오류·빈 값을 구별해 보인다", async () => {
    const { calls } = mount();
    typeExpr("[매출] / [비용]");
    const table = await screen.findByRole("table", { name: "미리보기 결과" });
    expect(of(calls, "/formulas/preview")[0].body).toEqual({ expression: "[매출] / [비용]" });
    const body = within(table).getAllByRole("row").slice(1);
    const valueCell = within(body[0]).getAllByRole("cell")[2];
    const errorCell = within(body[1]).getAllByRole("cell")[2];
    const emptyCell = within(body[2]).getAllByRole("cell")[2];
    expect(valueCell.textContent).toBe("1,234.5");
    expect(valueCell.className).toBe("preview-value");
    expect(errorCell.className).toBe("preview-error");
    expect(errorCell.textContent).toContain("오류");
    expect(errorCell.textContent).toContain("E1");
    expect(errorCell.textContent).toContain("서버 문구: 0으로 나눌 수 없습니다."); // D1 cell_errors
    expect(emptyCell.className).toBe("preview-empty");
    expect(emptyCell.textContent).toBe("빈 값");
    expect(screen.getByTestId("preview-summary").textContent).toBe("결과: 숫자 · 전체 36행 중 오류 칸 1개 · 빈 값 1개");
  });

  it("숫자 결과는 소수 최대 6자리로 줄여 보이고 줄었을 때만 툴팁에 전체 값이 있다", async () => {
    const rows = [
      { row_id: 1, period: "2026-03-01", value: "1234.5000000", error: null },
      { row_id: 2, period: "2026-02-01", value: "3.141592653589", error: null },
      { row_id: 3, period: "2026-01-01", value: "-0.0000004", error: null },
    ];
    mount({ handlers: { "POST /datasets/7/formulas/preview": () => json(200, { ...PREVIEW_OK, rows, total_rows: 3, error_count: 0, empty_count: 0 }) } });
    typeExpr("1");
    const table = await screen.findByRole("table", { name: "미리보기 결과" });
    const cells = within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[2]);
    expect(cells.map((c) => c.textContent)).toEqual(["1,234.5", "3.141593", "0"]);
    expect(cells.map((c) => c.getAttribute("title"))).toEqual([null, "전체 값: 3.141592653589", "전체 값: -0.0000004"]);
  });

  it("행이 하나도 없으면 안내", async () => {
    mount({ handlers: { "POST /datasets/7/formulas/preview": () => json(200, { ...PREVIEW_OK, rows: [], total_rows: 0, error_count: 0, empty_count: 0 }) } });
    typeExpr("1");
    expect(await screen.findByText(/아직 입력된 행이 없어/)).toBeTruthy();
  });

  it("'미리보기' 버튼으로 바로 계산한다", async () => {
    const { calls } = mount({ handlers: { "POST /datasets/7/formulas/check": () => json(200, { ...CHECK_OK, ok: false, errors: [] }) } });
    typeExpr("2 * 3");
    fireEvent.click(screen.getByRole("button", { name: "미리보기" }));
    await screen.findByRole("table", { name: "미리보기 결과" });
    expect(of(calls, "/formulas/preview")).toHaveLength(1);
  });

  it("수식이 바뀌면 이전 요청은 취소되고 늦게 온 낡은 결과는 무시된다", async () => {
    const pending: ((response: Response) => void)[] = [];
    const { calls, fetchMock } = mount({
      handlers: { "POST /datasets/7/formulas/preview": () => new Promise<Response>((resolve) => pending.push(resolve)) },
    });
    const result = (value: string): PreviewResult => ({ ...PREVIEW_OK, rows: [{ row_id: 1, period: "2026-01-01", value, error: null }], total_rows: 1, error_count: 0, empty_count: 0 });
    typeExpr("1");
    await waitFor(() => expect(pending).toHaveLength(1));
    typeExpr("2");
    await waitFor(() => expect(pending).toHaveLength(2));
    const previewCalls = fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/formulas/preview"));
    expect((previewCalls[0][1] as RequestInit).signal?.aborted).toBe(true); // 이전 요청 취소
    expect((previewCalls[1][1] as RequestInit).signal?.aborted).toBe(false);
    await act(async () => pending[1](json(200, result("22"))));
    await screen.findByRole("table", { name: "미리보기 결과" });
    await act(async () => pending[0](json(200, result("11"))));
    await sleep(30);
    const cells = within(screen.getByRole("table", { name: "미리보기 결과" })).getAllByRole("cell").map((c) => c.textContent);
    expect(cells).toContain("22");
    expect(cells).not.toContain("11");
    expect(of(calls, "/formulas/preview").map((c) => (c.body as { expression: string }).expression)).toEqual(["1", "2"]);
  });

  it("PREVIEW_BUSY(429)는 한 번 자동으로 다시 시도한다", async () => {
    let n = 0;
    const { calls } = mount({
      handlers: { "POST /datasets/7/formulas/preview": () => (n++ === 0 ? apiError(429, "PREVIEW_BUSY", "서버", { retry_after: 1 }) : json(200, PREVIEW_OK)) },
    });
    typeExpr("1");
    expect(await screen.findByText(/잠시 뒤 자동으로 다시 시도합니다/)).toBeTruthy();
    await screen.findByRole("table", { name: "미리보기 결과" });
    expect(of(calls, "/formulas/preview")).toHaveLength(2);
  });

  it("계속 바쁘면 안내와 '다시 시도' 버튼을 보이고, 누르면 다시 계산한다", async () => {
    let n = 0;
    const { calls } = mount({
      handlers: { "POST /datasets/7/formulas/preview": () => (n++ < 2 ? apiError(429, "PREVIEW_BUSY", "서버", { retry_after: 1 }) : json(200, PREVIEW_OK)) },
    });
    typeExpr("1");
    const alert = await screen.findByText(/미리보기를 계산하지 못했습니다/);
    expect(alert.closest("[role=alert]")?.textContent).toContain("잠시 뒤 다시 시도");
    fireEvent.click(within(alert.closest("[role=alert]") as HTMLElement).getByRole("button", { name: "다시 시도" }));
    await screen.findByRole("table", { name: "미리보기 결과" });
    expect(of(calls, "/formulas/preview")).toHaveLength(3);
  });

  it("FORMULA_RUNTIME_ERROR는 계산할 수 없다는 안내와 다시 시도", async () => {
    mount({ handlers: { "POST /datasets/7/formulas/preview": () => apiError(422, "FORMULA_RUNTIME_ERROR") } });
    typeExpr("1");
    expect((await screen.findByText(/수식을 계산할 수 없습니다/)).textContent).toContain("수식을 단순하게");
  });

  it("미리보기가 FORMULA_INVALID(검사보다 먼저)면 오류 위치를 보여 준다", async () => {
    mount({
      handlers: {
        "POST /datasets/7/formulas/check": () => json(200, CHECK_OK),
        "POST /datasets/7/formulas/preview": () =>
          apiError(422, "FORMULA_INVALID", "서버", { errors: [{ code: "X", message: "알 수 없는 열 [가나]입니다.", start: 0, end: 4 }], truncated: true, total: 300 }),
      },
    });
    typeExpr("[가나]");
    const alert = await screen.findByRole("alert", { name: "수식 오류" });
    expect(alert.textContent).toContain("알 수 없는 열 [가나]입니다.");
    expect(alert.querySelector("mark")?.textContent).toBe("[가나]");
  });
});

describe("저장 요청", () => {
  it("새 계산 열: 이름·수식·(숫자면) 태그·위치를 save에 넘긴다", async () => {
    const { save } = mount();
    const button = screen.getByRole("button", { name: "계산 열 추가" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true); // 이름·수식 없음
    fireEvent.change(screen.getByLabelText("계산 열 이름"), { target: { value: " 이익률 " } });
    typeExpr("[매출] / [비용]");
    expect(screen.queryByLabelText(/구분 태그/)).toBeNull(); // 결과 종류를 아직 모름
    fireEvent.change(await screen.findByLabelText(/구분 태그/), { target: { value: "지표" } });
    fireEvent.change(screen.getByLabelText(/위치/), { target: { value: "6" } });
    await waitFor(() => expect(button.disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith({ mode: "create", display_name: "이익률", expression: "[매출] / [비용]", tag: "지표", position: 6 });
  });

  it("열 이름 규칙 위반은 보내기 전에 막는다", () => {
    mount();
    fireEvent.change(screen.getByLabelText("계산 열 이름"), { target: { value: "a[b]" } });
    typeExpr("1");
    expect(screen.getByTestId("formula-name-error").textContent).toContain("쓸 수 없습니다");
    expect((screen.getByRole("button", { name: "계산 열 추가" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("수식 고치기: 시작값과 같으면 저장 불가, 바꾸면 update로 넘기고 이름 입력은 없다", async () => {
    const { save } = mount({ editing: SALES[4], initial: "[매출] - [비용]" });
    expect(box().value).toBe("[매출] - [비용]");
    expect(screen.queryByLabelText("계산 열 이름")).toBeNull();
    const button = screen.getByRole("button", { name: "수식 저장" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    typeExpr("[매출] - [비용] * 2");
    await waitFor(() => expect(button.disabled).toBe(false));
    fireEvent.click(button);
    await waitFor(() => expect(save).toHaveBeenCalledWith({ mode: "update", columnId: 5, expression: "[매출] - [비용] * 2" }));
    // 저장에 성공하면 그 수식이 새 기준이 되어 다시 저장할 수 없다
    await waitFor(() => expect(button.disabled).toBe(true));
  });

  const failWith = (error: unknown) => async () => ({ ok: false, error }) as SaveOutcome;
  const api = (status: number, code: string, details: unknown = null) => new ApiError(status, { code, message: "서버 문구", details, request_id: "req-1" });

  it("FORMULA_INVALID: 입력창 아래에 위치 표시, 잘림 안내", async () => {
    mount({
      save: failWith(api(422, "FORMULA_INVALID", { errors: [{ code: "X", message: "괄호가 닫히지 않았습니다.", start: 4, end: 5 }], truncated: true, total: 450 })),
      handlers: { "POST /datasets/7/formulas/check": () => json(200, { ...CHECK_OK, ok: true }) },
    });
    fireEvent.change(screen.getByLabelText("계산 열 이름"), { target: { value: "새 열" } });
    typeExpr("1 + (2");
    fireEvent.click(screen.getByRole("button", { name: "계산 열 추가" }));
    const alerts = await screen.findAllByRole("alert");
    const errorBox = alerts.find((a) => a.getAttribute("aria-label") === "수식 오류") as HTMLElement;
    expect(errorBox.textContent).toContain("괄호가 닫히지 않았습니다.");
    expect(errorBox.textContent).toContain("일부만 표시됨(전체 450건 중 일부)");
    expect(errorBox.querySelector("mark")?.textContent).toBe("(");
    expect(screen.getByText(/수식에 고칠 곳이 있어 저장하지 않았습니다/)).toBeTruthy();
  });

  it("FORMULA_CIRCULAR: 순환 경로를 열 이름으로 보여 준다", async () => {
    mount({ save: failWith(api(422, "FORMULA_CIRCULAR", { path: ["이익", "비율", "이익"] })) });
    fireEvent.change(screen.getByLabelText("계산 열 이름"), { target: { value: "새 열" } });
    typeExpr("[이익]");
    fireEvent.click(screen.getByRole("button", { name: "계산 열 추가" }));
    expect((await screen.findByText(/순환 경로/)).textContent).toContain("이익 → 비율 → 이익");
  });

  it("FORMULA_RUNTIME_ERROR·DEFINITION_BUSY·DEFINITION_VERSION_MISMATCH·ALREADY_EXISTS는 코드별 문구이고 수식은 남는다", async () => {
    let next: unknown = api(422, "FORMULA_RUNTIME_ERROR");
    mount({ save: async () => ({ ok: false, error: next }) as SaveOutcome });
    fireEvent.change(screen.getByLabelText("계산 열 이름"), { target: { value: "새 열" } });
    typeExpr("[매출] * 2");
    const submit = () => fireEvent.click(screen.getByRole("button", { name: "계산 열 추가" }));
    submit();
    expect((await screen.findByRole("alert")).textContent).toContain("수식을 계산할 수 없습니다");

    next = api(503, "DEFINITION_BUSY", { retry_after: 2 });
    submit();
    await waitFor(() => expect(screen.getByText(/다른 작업이 진행 중입니다/).textContent).toContain("약 2초 뒤"));
    expect(screen.getByText(/잠시 뒤 다시 저장해 주세요/)).toBeTruthy();

    next = api(409, "DEFINITION_VERSION_MISMATCH", { current_version: 9 });
    submit();
    await waitFor(() => expect(screen.getByText(/다른 사람이 먼저 바꿨습니다/)).toBeTruthy());
    expect(screen.getByText(/입력한 수식은 그대로 남아 있습니다. 내용을 확인한 뒤/)).toBeTruthy();
    expect(box().value).toBe("[매출] * 2");

    next = api(409, "ALREADY_EXISTS", { field: "display_name" });
    submit();
    await waitFor(() => expect(screen.getByText("같은 이름의 열이 이미 있습니다.")).toBeTruthy());
  });
});
