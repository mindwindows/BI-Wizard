import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import { COL } from "../dataset/test-server";
import type { Column, DatasetDetail } from "../dataset/types";
import { resetCatalogCache } from "./catalog";
import { makeFormulaFake, salesDetail, type FormulaFake } from "./test-server";

/**
 * 계산 열 이름 변경·위/아래 이동·구분 태그 편집(B6) 화면 시험. B6가 계산 열에 대해 하는 일(이름 중복 409, 숫자 열 아닌 열의 태그 422,
 * 낡은 버전 409)을 가짜 서버가 흉내 낸다. 실제 백엔드는 부르지 않는다.
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

/** 기준일1 매출2 비용3 메모4 + 계산 열 이익5(첫째, 위치 0) 비율6(숫자, 마지막) 문구7(글자 결과, 마지막 앞). */
function detail(patch: Partial<DatasetDetail> = {}): DatasetDetail {
  const base = salesDetail(patch);
  const columns: Column[] = base.columns.map((c) => (c.id === 5 ? { ...c, position: 0 } : c));
  columns.push(COL(7, "문구", "text", { kind: "formula", position: 8 }));
  columns.push(COL(6, "비율", "number", { kind: "formula", position: 9, tag: "비율군" }));
  return { ...base, columns };
}

function patchHandler(fake: FormulaFake, log: RecordedCall[]): Handler {
  return (call) => {
    log.push(call);
    const body = call.body as Record<string, unknown> & { expected_version: number };
    if (body.expected_version !== fake.state.def_version) {
      return apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: fake.state.def_version });
    }
    const column = fake.state.columns.find((c) => c.id === Number(call.path.split("/").at(-1)));
    if (!column) return apiError(404, "NOT_FOUND");
    if (typeof body.display_name === "string" && fake.state.columns.some((c) => c.id !== column.id && c.display_name === body.display_name)) {
      return apiError(409, "ALREADY_EXISTS", "서버 문구", { field: "display_name" });
    }
    if (typeof body.tag === "string" && column.type !== "number") {
      return apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ field: "tag", code: "BAD_FORMAT" }] });
    }
    const { expected_version: _v, ...changes } = body;
    void _v;
    Object.assign(column, changes);
    fake.state.def_version += 1;
    return json(200, { column, def_version: fake.state.def_version });
  };
}

/** override가 Response를 돌려주면 그 응답을, null이면 가짜 B6 규칙을 쓴다(n은 1부터 센 PATCH 호출 순번). */
type Override = (call: RecordedCall, n: number) => Response | null;

async function open(opts: { detail?: DatasetDetail; override?: Override } = {}) {
  const d = opts.detail ?? detail();
  const fake = makeFormulaFake(d, []);
  const patches: RecordedCall[] = [];
  const normal = patchHandler(fake, patches);
  const handlers: Record<string, Handler> = {};
  for (let n = 1; n <= 30; n += 1) {
    handlers[`PATCH /datasets/${d.id}/columns/${n}`] = (call) => {
      const forced = opts.override?.(call, patches.length + 1) ?? null;
      if (forced) {
        patches.push(call);
        return forced;
      }
      return normal(call);
    };
  }
  const { calls } = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), ...fake.handlers, ...handlers });
  render(<App router={createTestRouter(BASE, `${BASE}/datasets/${d.id}`)} />);
  await screen.findByRole("region", { name: "데이터셋 정보" });
  return { fake, calls, patches };
}

const inspector = () => screen.getByRole("complementary", { name: "Inspector" });
const list = () => screen.getByRole("region", { name: "열 목록" });
const select = (name: RegExp) => fireEvent.click(within(list()).getByRole("button", { name }));
const order = () => within(list()).getAllByRole("button").map((b) => b.textContent?.split(" ")[0]).filter((t) => t && !["열", "계산"].includes(t));
const settings = () => within(inspector()).getByRole("region", { name: "계산 열 관리" });
const nameForm = () => within(settings()).getByRole("form", { name: "계산 열 이름·태그" });
const btn = (name: string) => within(settings()).getByRole("button", { name }) as HTMLButtonElement;

describe("계산 열 이름 변경", () => {
  it("이름을 고쳐 저장하면 바뀐 필드만 B6로 보내고 목록과 정의 버전이 갱신되며 수식 보기를 다시 읽는다", async () => {
    const { calls, patches, fake } = await open();
    select(/^이익/);
    await within(inspector()).findByTestId("formula-text");
    expect(within(nameForm()).getByTestId("rename-hint").textContent).toContain("열 번호로 저장");
    expect(btn("이름·태그 저장").disabled).toBe(true);
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: " 순이익 " } });
    fireEvent.click(btn("이름·태그 저장"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].path).toBe("/datasets/7/columns/5");
    expect(patches[0].body).toEqual({ expected_version: 3, display_name: "순이익" });
    expect((await within(inspector()).findByRole("status")).textContent).toBe("열을 저장했습니다.");
    expect(within(list()).getByRole("button", { name: /^순이익/ })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "데이터셋 정보" })).getByText("4")).toBeTruthy();
    // 새 정의 버전에서 수식 보기를 다시 읽는다
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path.endsWith("/formulas/5")).length).toBeGreaterThanOrEqual(2));
    expect(fake.state.columns.find((c) => c.id === 5)?.display_name).toBe("순이익");
  });

  it("같은 이름의 열이 있으면 409 ALREADY_EXISTS를 쉬운 말로 보여 준다", async () => {
    const { patches } = await open();
    select(/^이익/);
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: "매출" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("같은 이름의 열이 이미 있습니다.");
    expect(patches).toHaveLength(1);
  });

  it("예약 이름·금지 문자·빈 이름은 보내기 전에 막고 이유를 보여 준다", async () => {
    const { patches } = await open();
    select(/^이익/);
    const input = within(nameForm()).getByLabelText("열 이름");
    fireEvent.change(input, { target: { value: "Team" } });
    expect(within(nameForm()).getByTestId("name-error").textContent).toContain("예약어");
    expect(btn("이름·태그 저장").disabled).toBe(true);
    fireEvent.change(input, { target: { value: "a[b]" } });
    expect(within(nameForm()).getByTestId("name-error").textContent).toContain("쓸 수 없습니다");
    fireEvent.change(input, { target: { value: "  " } });
    expect(within(nameForm()).getByTestId("name-error").textContent).toContain("입력해 주세요");
    expect(btn("이름·태그 저장").disabled).toBe(true);
    expect(patches).toHaveLength(0);
  });

  it("서버의 이름 규칙 422는 항목과 이유를 쉬운 말로 보여 준다", async () => {
    await open({ override: () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ field: "display_name", code: "RESERVED" }] }) });
    select(/^이익/);
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: "새 이름" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("표시 이름: 사용할 수 없는 이름입니다");
  });

  it("낡은 정의 버전(409)이면 안내하고 최신 정의를 다시 읽는다", async () => {
    const { calls } = await open({ override: () => apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: 9 }) });
    select(/^이익/);
    const before = calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length;
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: "새 이름" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("다른 사람이 먼저");
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length).toBe(before + 1));
  });

  it("503 DEFINITION_BUSY는 잠시 뒤 다시 시도하라고 안내한다", async () => {
    await open({ override: () => apiError(503, "DEFINITION_BUSY", "서버 문구", { retry_after: 2 }) });
    select(/^이익/);
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: "새 이름" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toMatch(/잠시 뒤|다시 시도/);
  });
});

describe("계산 열 구분 태그", () => {
  it("숫자 결과 열은 태그를 넣거나 비울 수 있다(비우면 null)", async () => {
    const { patches } = await open();
    select(/^비율/);
    const input = within(nameForm()).getByLabelText("구분 태그") as HTMLInputElement;
    expect(input.value).toBe("비율군");
    fireEvent.change(input, { target: { value: "수익" } });
    fireEvent.click(btn("이름·태그 저장"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].body).toEqual({ expected_version: 3, tag: "수익" });
    await within(inspector()).findByRole("status");
    fireEvent.change(within(nameForm()).getByLabelText("구분 태그"), { target: { value: "" } });
    fireEvent.click(btn("이름·태그 저장"));
    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches[1].body).toEqual({ expected_version: 4, tag: null });
  });

  it("글자 결과 계산 열은 태그 입력칸이 없고 이유를 안내한다", async () => {
    await open();
    select(/^문구/);
    expect(within(nameForm()).queryByLabelText("구분 태그")).toBeNull();
    expect(within(nameForm()).getByTestId("tag-number-only").textContent).toContain("숫자");
  });

  it("너무 긴 태그·큰따옴표는 보내기 전에 막는다", async () => {
    const { patches } = await open();
    select(/^비율/);
    fireEvent.change(within(nameForm()).getByLabelText("구분 태그"), { target: { value: 'a"b' } });
    expect(within(nameForm()).getByText(/구분 태그에는/)).toBeTruthy();
    expect(btn("이름·태그 저장").disabled).toBe(true);
    expect(patches).toHaveLength(0);
  });

  it("태그 때문에 순환이 생기면(422 FORMULA_CIRCULAR) 순환 경로를 보여 준다", async () => {
    await open({ override: () => apiError(422, "FORMULA_CIRCULAR", "서버 문구", { path: ["비율", "이익", "비율"] }) });
    select(/^비율/);
    fireEvent.change(within(nameForm()).getByLabelText("구분 태그"), { target: { value: "수입" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("비율 → 이익 → 비율");
  });
});

describe("계산 열 위/아래 이동", () => {
  it("한 칸 위로: 이웃한 두 열의 위치 번호를 B6로 서로 바꾸고(2회, 버전이 이어짐) 열 순서가 바뀐다", async () => {
    const { patches } = await open();
    select(/^비율/);
    expect(order()).toEqual(["이익", "기준일", "매출", "비용", "메모", "문구", "비율"]);
    expect(within(settings()).getByTestId("column-position").textContent).toContain("7번째 / 전체 7개");
    fireEvent.click(btn("위로 이동"));
    await waitFor(() => expect(patches).toHaveLength(2));
    expect(patches.map((p) => [p.path.split("/").at(-1), p.body])).toEqual([
      ["6", { expected_version: 3, position: 8 }],
      ["7", { expected_version: 4, position: 9 }],
    ]);
    expect((await within(inspector()).findByRole("status")).textContent).toBe("열 순서를 바꿨습니다.");
    expect(order()).toEqual(["이익", "기준일", "매출", "비용", "메모", "비율", "문구"]);
    expect(within(settings()).getByTestId("column-position").textContent).toContain("6번째 / 전체 7개");
  });

  it("한 칸 아래로", async () => {
    const { patches } = await open();
    select(/^이익/);
    fireEvent.click(btn("아래로 이동"));
    await waitFor(() => expect(patches).toHaveLength(2));
    await within(inspector()).findByRole("status");
    expect(order().slice(0, 2)).toEqual(["기준일", "이익"]);
  });

  it("맨 앞 열은 '위로', 맨 뒤 열은 '아래로'가 비활성이다", async () => {
    await open();
    select(/^이익/);
    expect(btn("위로 이동").disabled).toBe(true);
    expect(btn("아래로 이동").disabled).toBe(false);
    select(/^비율/);
    expect(btn("아래로 이동").disabled).toBe(true);
    expect(btn("위로 이동").disabled).toBe(false);
  });

  it("위치 번호가 겹쳐 있으면 0부터 차례로 다시 매긴다", async () => {
    const d = detail();
    for (const c of d.columns) c.position = 0; // 모두 같은 번호: id 순
    const { patches } = await open({ detail: d });
    select(/^이익/); // id 5 → 순서: 1 2 3 4 5 6 7 중 5번째
    fireEvent.click(btn("위로 이동"));
    await waitFor(() => expect(patches).toHaveLength(6));
    await within(inspector()).findByRole("status");
    // 모두 0이던 7열을 0..6으로 재매김: 첫 열(0)은 그대로, 나머지 6열이 달라진다. 5번째와 4번째가 바뀐 순서.
    expect(patches.map((p) => (p.body as { position: number }).position)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(order().slice(0, 5)).toEqual(["기준일", "매출", "비용", "이익", "메모"]);
  });

  it("위치 번호가 모두 다르면 정확히 2회만 부른다", async () => {
    const { patches } = await open();
    select(/^이익/);
    fireEvent.click(btn("아래로 이동"));
    await waitFor(() => expect(patches).toHaveLength(2));
    await within(inspector()).findByRole("status");
    expect(patches).toHaveLength(2);
  });

  it("같은 번호 3열이면 달라지는 열마다 한 번씩(2회) 0,1,2로 다시 매긴다", async () => {
    const d = detail();
    d.columns = d.columns.slice(0, 3);
    for (const c of d.columns) c.position = 5;
    const { patches } = await open({ detail: d });
    select(/^기준일/);
    fireEvent.click(btn("아래로 이동"));
    await waitFor(() => expect(patches).toHaveLength(2));
    await within(inspector()).findByRole("status");
    expect(patches).toHaveLength(2);
    expect(patches.map((p) => p.body)).toEqual([
      { expected_version: 3, position: 1 },
      { expected_version: 4, position: 2 },
    ]);
  });

  it("첫 호출이 409로 실패하면 아무것도 바꾸지 않고 안내하며 최신 정의를 다시 읽는다", async () => {
    const { patches, calls } = await open({ override: () => apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: 9 }) });
    select(/^비율/);
    const before = calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length;
    fireEvent.click(btn("위로 이동"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("다른 사람이 먼저");
    expect(patches).toHaveLength(1);
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length).toBe(before + 1));
    expect(order().slice(-2)).toEqual(["문구", "비율"]);
  });

  it("두 번째 호출이 503이면 오류를 보이고 실제 순서를 다시 읽는다", async () => {
    const { patches, calls } = await open({ override: (_call, n) => (n === 2 ? apiError(503, "DEFINITION_BUSY", "서버 문구", { retry_after: 2 }) : null) });
    select(/^비율/);
    const before = calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length;
    fireEvent.click(btn("위로 이동"));
    const alert = await within(inspector()).findByRole("alert");
    expect(alert.textContent).toMatch(/잠시 뒤|다시 시도/);
    expect(within(alert).getByTestId("feedback-note").textContent).toBe("순서를 다시 확인해 주세요");
    expect(patches).toHaveLength(2);
    await waitFor(() => expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7").length).toBe(before + 1));
  });

  it("두 번째 호출이 409로 실패해도 '순서를 다시 확인해 주세요'를 안내하고, 첫 호출 실패에는 붙이지 않는다", async () => {
    await open({ override: (_call, n) => (n === 2 ? apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: 9 }) : null) });
    select(/^비율/);
    fireEvent.click(btn("위로 이동"));
    expect((await within(inspector()).findByTestId("feedback-note")).textContent).toBe("순서를 다시 확인해 주세요");
    cleanup();
    await open({ override: () => apiError(503, "DEFINITION_BUSY", "서버 문구", { retry_after: 2 }) });
    select(/^비율/);
    fireEvent.click(btn("위로 이동"));
    await within(inspector()).findByRole("alert");
    expect(within(inspector()).queryByTestId("feedback-note")).toBeNull();
  });

  it("422(순서 변경이 거부됨)도 쉬운 말로 보여 준다", async () => {
    await open({ override: () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ field: "position", code: "OUT_OF_RANGE" }] }) });
    select(/^비율/);
    fireEvent.click(btn("위로 이동"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("위치: 허용 범위를 벗어났습니다");
  });
});

const formatForm = () => within(settings()).getByRole("form", { name: "표시 형식" });

describe("계산 열 표시 형식(rules: display_decimals·display_thousands)", () => {
  /** 가짜 B6: 계산 열 rules 허용 키만 받는다(전체 대체, {}는 지움). */
  const rulesOverride: Override = (call) => {
    const rules = (call.body as { rules?: Record<string, unknown> }).rules;
    if (rules === undefined) return null;
    for (const [key, value] of Object.entries(rules)) {
      if (key === "display_decimals" ? !Number.isInteger(value) || (value as number) < 0 || (value as number) > 10 : key !== "display_thousands" || typeof value !== "boolean") {
        return apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ field: "rules", code: key === "display_decimals" ? "OUT_OF_RANGE" : "BAD_FORMAT" }] });
      }
    }
    return null;
  };

  it("자릿수·쉼표를 정해 저장하면 rules 전체를 B6로 보내고 입력칸이 저장값으로 돌아온다", async () => {
    const { patches } = await open({ override: rulesOverride });
    select(/^비율/);
    expect(within(formatForm()).getByTestId("format-hint").textContent).toMatch(/표시 전용.*ROUND\*.*Superset 차트와 SQL Lab에는 적용되지 않습니다.*YEAR.*쉼표를 끄십시오/);
    expect(btn("표시 형식 저장").disabled).toBe(true);
    fireEvent.change(within(formatForm()).getByLabelText(/소수 자릿수/), { target: { value: "2" } });
    fireEvent.click(within(formatForm()).getByLabelText("천 단위 쉼표"));
    fireEvent.click(btn("표시 형식 저장"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].body).toEqual({ expected_version: 3, rules: { display_decimals: 2, display_thousands: false } });
    expect((await within(inspector()).findByRole("status")).textContent).toBe("열을 저장했습니다.");
    expect((within(formatForm()).getByLabelText(/소수 자릿수/) as HTMLInputElement).value).toBe("2");
    expect((within(formatForm()).getByLabelText("천 단위 쉼표") as HTMLInputElement).checked).toBe(false);
  });

  it("'기본'(빈 칸)으로 되돌리면 자릿수 키를 빼고, 표시 형식 두 키만 보낸다(다른 키는 보내지 않는다)", async () => {
    const d = detail();
    d.columns = d.columns.map((c) => (c.id === 6 ? { ...c, rules: { display_decimals: 1, display_thousands: false, future_key: "x" } } : c));
    const { patches } = await open({ detail: d, override: rulesOverride });
    select(/^비율/);
    fireEvent.change(within(formatForm()).getByLabelText(/소수 자릿수/), { target: { value: "" } });
    fireEvent.click(btn("표시 형식 저장"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].body).toEqual({ expected_version: 3, rules: { display_thousands: false } });
    expect(Object.keys((patches[0].body as { rules: object }).rules)).toEqual(["display_thousands"]);
  });

  it("전부 기본으로 되돌리면 {}(설정 지움)를 보낸다", async () => {
    const d = detail();
    d.columns = d.columns.map((c) => (c.id === 6 ? { ...c, rules: { display_decimals: 0 } } : c));
    const { patches } = await open({ detail: d });
    select(/^비율/);
    fireEvent.change(within(formatForm()).getByLabelText(/소수 자릿수/), { target: { value: "" } });
    fireEvent.click(btn("표시 형식 저장"));
    await waitFor(() => expect(patches).toHaveLength(1));
    expect(patches[0].body).toEqual({ expected_version: 3, rules: {} });
  });

  it("범위 밖·정수 아닌 자릿수는 보내기 전에 막는다", async () => {
    const { patches } = await open();
    select(/^비율/);
    const input = within(formatForm()).getByLabelText(/소수 자릿수/);
    for (const bad of ["11", "1.5", "-1", "abc"]) {
      fireEvent.change(input, { target: { value: bad } });
      expect(within(formatForm()).getByTestId("format-error").textContent).toContain("0부터 10까지");
      expect(btn("표시 형식 저장").disabled).toBe(true);
    }
    fireEvent.change(input, { target: { value: "10" } });
    expect(within(formatForm()).queryByTestId("format-error")).toBeNull();
    expect(btn("표시 형식 저장").disabled).toBe(false);
    expect(patches).toHaveLength(0);
  });

  it("서버 422(rules)·409 버전 충돌은 기존 방식으로 안내한다", async () => {
    await open({ override: () => apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: [{ field: "rules", code: "OUT_OF_RANGE" }] }) });
    select(/^비율/);
    fireEvent.change(within(formatForm()).getByLabelText(/소수 자릿수/), { target: { value: "3" } });
    fireEvent.click(btn("표시 형식 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("허용 범위를 벗어났습니다");
    cleanup();
    await open({ override: () => apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: 9 }) });
    select(/^비율/);
    fireEvent.change(within(formatForm()).getByLabelText(/소수 자릿수/), { target: { value: "3" } });
    fireEvent.click(btn("표시 형식 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("다른 사람이 먼저");
  });

  it("글자 결과 계산 열은 입력칸 없이 안내만 보인다", async () => {
    await open();
    select(/^문구/);
    expect(within(formatForm()).queryByLabelText(/소수 자릿수/)).toBeNull();
    expect(within(formatForm()).queryByRole("button")).toBeNull();
    expect(within(formatForm()).getByTestId("format-number-only").textContent).toContain("숫자");
  });

  it("읽기 전용(정의 담당자 아님)·보관 시 입력칸이 비활성이고 저장 버튼이 없거나 비활성이다", async () => {
    await open({ detail: detail({ permissions: { define: false, enter: true } }) });
    select(/^비율/);
    expect((within(formatForm()).getByLabelText(/소수 자릿수/) as HTMLInputElement).disabled).toBe(true);
    expect((within(formatForm()).getByLabelText("천 단위 쉼표") as HTMLInputElement).disabled).toBe(true);
    expect(within(formatForm()).queryByRole("button")).toBeNull();
    cleanup();
    await open({ detail: detail({ status: "archived" }) });
    select(/^비율/);
    expect((within(formatForm()).getByLabelText(/소수 자릿수/) as HTMLInputElement).disabled).toBe(true);
    expect(btn("표시 형식 저장").disabled).toBe(true);
  });
});

describe("권한과 보관", () => {
  it("정의 담당자가 아니면 입력칸이 읽기 전용이고 저장·이동 버튼이 없다", async () => {
    const { patches } = await open({ detail: detail({ permissions: { define: false, enter: true } }) });
    select(/^비율/);
    expect((within(nameForm()).getByLabelText("열 이름") as HTMLInputElement).disabled).toBe(true);
    expect((within(nameForm()).getByLabelText("구분 태그") as HTMLInputElement).disabled).toBe(true);
    expect(within(settings()).queryByRole("button")).toBeNull();
    expect(within(inspector()).getByTestId("readonly-notice")).toBeTruthy();
    expect(patches).toHaveLength(0);
  });

  it("보관된 데이터셋에서는 입력칸과 버튼이 비활성이고 안내 배너가 있다", async () => {
    const { patches } = await open({ detail: detail({ status: "archived" }) });
    select(/^비율/);
    expect((within(nameForm()).getByLabelText("열 이름") as HTMLInputElement).disabled).toBe(true);
    expect(btn("이름·태그 저장").disabled).toBe(true);
    expect(btn("위로 이동").disabled).toBe(true);
    expect(btn("아래로 이동").disabled).toBe(true);
    expect(screen.getByTestId("archived-banner")).toBeTruthy();
    expect(patches).toHaveLength(0);
  });

  it("다른 사람이 방금 보관해 409 DATASET_ARCHIVED가 오면 안내하고 읽기 전용으로 바뀐다", async () => {
    const ref: { fake?: FormulaFake } = {};
    ref.fake = (
      await open({
        override: () => {
          ref.fake!.state.status = "archived"; // 다른 사람이 방금 보관했다
          return apiError(409, "DATASET_ARCHIVED", "서버 문구", { status: "archived" });
        },
      })
    ).fake;
    select(/^비율/);
    fireEvent.change(within(nameForm()).getByLabelText("열 이름"), { target: { value: "새 이름" } });
    fireEvent.click(btn("이름·태그 저장"));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("보관된 데이터셋은 고칠 수 없습니다");
    await screen.findByTestId("archived-banner");
  });
});
