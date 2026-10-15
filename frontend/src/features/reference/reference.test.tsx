import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { describeApiError } from "../../errors";
import { ApiError } from "../../api";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";
import { AUDIT_NOTE_TEXT, GUIDE_REF_TEXT, GUIDE_TEXT, IMPACT_TEXT, NAME_RULE_TEXT, READ_ONLY_TEXT, usageFailedText, usageTimeout } from "./ReferencePage";
import { defaultYear, normalizeValue, validateDescription, validateItemName, validateValue, validateYear } from "./rules";
import type { ReferenceItem, ReferenceValue } from "./types";

/**
 * FU-3 S11 기준값 화면 시험. 05 §2-8(R1~R6)대로 답하는 모의 fetch를 쓴다. 실제 백엔드를 부르지 않으므로
 * 서버와의 일치는 이 시험이 보증하지 않는다(통합 시험·스크린샷 단계에서 확인).
 */
const BASE = "/bi-wizard";
const ME_USER = { id: 1, display_name: "관리자 김" };

const item = (id: number, name: string, extra: Partial<ReferenceItem> = {}): ReferenceItem => ({
  id,
  name,
  description: null,
  value_count: 0,
  year_min: null,
  year_max: null,
  created_by: ME_USER,
  created_at: "2026-10-14T09:00:00+09:00",
  ...extra,
});
const value = (id: number, item_id: number, year: number, v: string): ReferenceValue => ({ id, item_id, year, value: v, created_by: ME_USER, created_at: "2026-10-14T09:00:00+09:00" });

const page = <T,>(items: T[]) => json(200, { items, total: items.length, limit: 50, offset: 0 });

interface Fake {
  items: ReferenceItem[];
  values: Record<number, ReferenceValue[]>;
}
const makeFake = (): Fake => ({
  items: [
    item(1, "전기요금_A팀", { description: "A팀 전기요금 단가", value_count: 2, year_min: 2025, year_max: 2026 }),
    item(2, "환율", { value_count: 0 }),
  ],
  values: { 1: [value(11, 1, 2026, "12.50"), value(10, 1, 2025, "11.00")], 2: [] },
});

function handlersFor(fake: Fake, extra: Record<string, Handler> = {}): Record<string, Handler> {
  // 항목 번호 1~9의 값 목록·영향 목록(R3·R6)은 가짜 서버 상태에서 읽는다.
  const perItem: Record<string, Handler> = {};
  for (let id = 1; id <= 9; id += 1) {
    perItem[`GET /reference-items/${id}/values`] = () => page(fake.values[id] ?? []);
    perItem[`GET /reference-items/${id}/usage`] = () => json(200, { items: [], total: 0, truncated: false });
  }
  return {
    ...HEALTH_HANDLERS,
    "GET /me": () => json(200, ADMIN_ME),
    "GET /reference-items": () => page(fake.items),
    ...perItem,
    "POST /reference-items": (call) => {
      const body = call.body as { name: string; description?: string };
      if (fake.items.some((i) => i.name === body.name)) return apiError(409, "ALREADY_EXISTS", "서버 문구", { field: "name" });
      const created = item(fake.items.length + 1, body.name, { description: body.description ?? null });
      fake.items.push(created);
      fake.values[created.id] = [];
      return json(201, created);
    },
    ...extra,
  };
}

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: "" };
  window.sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
  usageTimeout.ms = 5000;
});

function open(fake: Fake, extra: Record<string, Handler> = {}, me: unknown = ADMIN_ME) {
  const installed = installFetch({ ...handlersFor(fake, extra), "GET /me": () => json(200, me) });
  render(<App router={createTestRouter(BASE, `${BASE}/reference-values`)} />);
  return installed;
}
const ready = async () => {
  await screen.findByTestId("screen-S11");
  await screen.findByRole("table", { name: "기준값 항목 목록" });
  await screen.findByRole("table", { name: "전기요금_A팀 연도별 값" });
};
const valueRows = () => within(screen.getByRole("table", { name: "전기요금_A팀 연도별 값" })).getAllByRole("row").slice(1);
const callsOf = (calls: RecordedCall[], method: string, path: string) => calls.filter((c) => c.method === method && c.path === path);
const dialog = () => screen.getByRole("dialog");

describe("S11 목록과 값 표", () => {
  it("항목 목록(이름·설명·값 개수·연도 범위)과 첫 항목의 연도별 값(내림차순)을 보여 준다", async () => {
    open(makeFake());
    await ready();
    const rows = within(screen.getByRole("table", { name: "기준값 항목 목록" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").map((c) => c.textContent))).toEqual([
      ["전기요금_A팀", "A팀 전기요금 단가", "2", "2025~2026년"],
      ["환율", "-", "0", "값 없음"],
    ]);
    expect(valueRows().map((r) => within(r).getAllByRole("cell").slice(0, 2).map((c) => c.textContent))).toEqual([
      ["2026년", "12.50"],
      ["2025년", "11.00"],
    ]);
    expect(screen.getByText(/REF\("전기요금_A팀"\)/)).toBeTruthy();
  });

  it("R1·R3를 limit/offset과 함께 부른다", async () => {
    const { calls } = open(makeFake());
    await ready();
    expect(Object.fromEntries(callsOf(calls, "GET", "/reference-items")[0].query.entries())).toEqual({ limit: "50", offset: "0" });
    expect(Object.fromEntries(callsOf(calls, "GET", "/reference-items/1/values")[0].query.entries())).toEqual({ limit: "50", offset: "0" });
  });

  it("항목을 누르면 그 항목의 값 표로 바뀌고 값이 없으면 안내(E4)를 보인다", async () => {
    open(makeFake());
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "환율" }));
    expect((await screen.findByTestId("no-reference-values")).textContent).toContain("E4");
  });

  it("안내문: 숫자만·연도 일괄 적용·시기 선택은 기준 날짜와 대시보드 기간 필터, 글자 기준값 없음, E4", async () => {
    open(makeFake());
    await ready();
    const guide = screen.getByTestId("reference-guide").textContent ?? "";
    expect(guide).toContain(GUIDE_TEXT);
    expect(guide).toContain(GUIDE_REF_TEXT);
    expect(GUIDE_TEXT).toContain("숫자만");
    expect(GUIDE_TEXT).toContain("글자 기준값");
    expect(GUIDE_TEXT).toContain("기준 날짜와 대시보드 기간 필터가 맡습니다");
    expect(GUIDE_REF_TEXT).toContain("E4");
  });

  it("항목이 없으면 안내를 보이고(관리자는 추가 안내), 목록 503이면 오류와 다시 시도를 보인다", async () => {
    const fake = makeFake();
    fake.items = [];
    open(fake);
    expect((await screen.findByTestId("no-reference-items")).textContent).toContain("추가");
    cleanup();
    vi.unstubAllGlobals();
    let fail = true;
    open(makeFake(), { "GET /reference-items": () => (fail ? apiError(503, "SERVICE_UNAVAILABLE") : page(makeFake().items)) });
    expect((await screen.findByRole("alert")).textContent).toContain("잠시 뒤 다시 시도");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await screen.findByRole("table", { name: "기준값 항목 목록" });
  });
});

describe("권한별 노출", () => {
  it("관리자: 항목 추가·연도 값 추가 폼과 행마다 정정 버튼이 있다", async () => {
    open(makeFake());
    await ready();
    expect(screen.getByRole("form", { name: "기준값 항목 추가" })).toBeTruthy();
    expect(screen.getByRole("form", { name: "연도 값 추가" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "2026년 값 정정" })).toBeTruthy();
    expect(screen.queryByTestId("reference-readonly")).toBeNull();
  });

  it("비관리자: 목록과 값은 보이고 추가·정정 UI는 없으며 R6(관리자 전용)을 부르지 않는다", async () => {
    const { calls } = open(makeFake(), {}, MEMBER_ME);
    await ready();
    expect(screen.getByTestId("reference-readonly").textContent).toBe(READ_ONLY_TEXT);
    expect(screen.queryByRole("form", { name: "기준값 항목 추가" })).toBeNull();
    expect(screen.queryByRole("form", { name: "연도 값 추가" })).toBeNull();
    expect(screen.queryByRole("button", { name: /정정/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /항목 추가|값 추가/ })).toBeNull();
    expect(valueRows()).toHaveLength(2);
    expect(calls.filter((c) => c.method !== "GET" && c.path !== "/me")).toHaveLength(0);
    expect(callsOf(calls, "GET", "/reference-items/1/usage")).toHaveLength(0);
  });

  it("상단 메뉴 '기준값'은 비관리자에게도 보인다", async () => {
    open(makeFake(), {}, MEMBER_ME);
    await ready();
    const link = within(screen.getByRole("navigation", { name: "주 메뉴" })).getByRole("link", { name: "기준값" });
    expect(link.getAttribute("href")).toBe(`${BASE}/reference-values`);
  });
});

describe("항목 추가(R2)", () => {
  it("이름 규칙 안내와 예시, 설명 칸 안내가 보이고 이름·설명을 POST한다", async () => {
    const fake = makeFake();
    const { calls } = open(fake);
    await ready();
    expect(screen.getByTestId("name-rule").textContent).toBe(NAME_RULE_TEXT);
    expect(NAME_RULE_TEXT).toContain("전기요금_A팀");
    expect(screen.getByText(/설명 \(선택/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "  가스요금_B팀 " } });
    fireEvent.change(screen.getByLabelText(/^설명/), { target: { value: "B팀 가스 단가" } });
    fireEvent.click(screen.getByRole("button", { name: "항목 추가" }));
    expect((await screen.findByTestId("item-created")).textContent).toContain("가스요금_B팀");
    expect(callsOf(calls, "POST", "/reference-items")[0].body).toEqual({ name: "가스요금_B팀", description: "B팀 가스 단가" });
    // 새 항목이 목록에 생기고 선택된다
    await screen.findByTestId("no-reference-values");
    expect(within(screen.getByTestId("reference-detail")).getByRole("heading", { name: /가스요금_B팀/ })).toBeTruthy();
  });

  it("설명이 비면 description을 보내지 않는다", async () => {
    const fake = makeFake();
    const { calls } = open(fake);
    await ready();
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "유가" } });
    fireEvent.click(screen.getByRole("button", { name: "항목 추가" }));
    await screen.findByTestId("item-created");
    expect(callsOf(calls, "POST", "/reference-items")[0].body).toEqual({ name: "유가" });
  });

  it("앞단 검사: 빈 이름·[ ] \" 는 보내지 않는다", async () => {
    const { calls } = open(makeFake());
    await ready();
    const submit = screen.getByRole("button", { name: "항목 추가" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "a[1]" } });
    expect(submit.disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("쓸 수 없습니다");
    expect(callsOf(calls, "POST", "/reference-items")).toHaveLength(0);
  });

  it("409 ALREADY_EXISTS(name)는 이름 칸 아래에 같은 이름 안내를 보인다", async () => {
    open(makeFake());
    await ready();
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "환율" } });
    fireEvent.click(screen.getByRole("button", { name: "항목 추가" }));
    await waitFor(() => expect(screen.getByRole("form", { name: "기준값 항목 추가" }).textContent).toContain("같은 이름이 이미 있습니다"));
  });

  it("422(서버 이름 규칙)·403·503 WRITE_BUSY를 쉬운 말로 보인다", async () => {
    let next: Response = apiError(422, "VALIDATION_ERROR", "x", { fields: [{ field: "name", code: "BAD_FORMAT", message: "x" }] });
    open(makeFake(), { "POST /reference-items": () => next });
    await ready();
    const form = () => screen.getByRole("form", { name: "기준값 항목 추가" });
    const submit = () => fireEvent.click(screen.getByRole("button", { name: "항목 추가" }));
    fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "유가" } });
    submit();
    await waitFor(() => expect(form().textContent).toContain("쓸 수 없는 글자"));
    next = apiError(403, "FORBIDDEN");
    submit();
    await waitFor(() => expect(form().textContent).toContain("관리자만 할 수 있습니다."));
    next = apiError(503, "WRITE_BUSY", "x", { retry_after: 2 });
    submit();
    await waitFor(() => expect(form().textContent).toContain("잠시 뒤 다시 시도해 주세요. (약 2초 뒤)"));
  });
});

describe("연도 값 추가(R4)", () => {
  it("기본 연도는 가장 큰 연도 + 1이고 year는 정수, value는 문자열로 POST한다", async () => {
    const fake = makeFake();
    const { calls } = open(fake, {
      "POST /reference-items/1/values": (call) => {
        const body = call.body as { year: number; value: string };
        const created = value(12, 1, body.year, body.value);
        fake.values[1] = [created, ...fake.values[1]];
        fake.items[0] = { ...fake.items[0], value_count: 3, year_max: body.year };
        return json(201, created);
      },
    });
    await ready();
    const year = screen.getByLabelText(/^연도 \(/) as HTMLInputElement;
    expect(year.value).toBe("2027");
    fireEvent.change(screen.getByLabelText(/^값 \(/), { target: { value: " 13.25 " } });
    fireEvent.click(screen.getByRole("button", { name: "값 추가" }));
    await waitFor(() => expect(screen.getByTestId("reference-notice").textContent).toContain("2027년 값 13.25"));
    const body = callsOf(calls, "POST", "/reference-items/1/values")[0].body as { year: unknown; value: unknown };
    expect(body).toEqual({ year: 2027, value: "13.25" });
    expect(typeof body.year).toBe("number");
    expect(typeof body.value).toBe("string");
    // 새로 읽은 값 표가 맨 위에 2027년을 보인다
    await waitFor(() => expect(valueRows()[0].textContent).toContain("2027년"));
    expect((screen.getByLabelText(/^연도 \(/) as HTMLInputElement).value).toBe("2028");
  });

  it("숫자가 아닌 값·범위 밖 연도는 보내지 않는다", async () => {
    const { calls } = open(makeFake());
    await ready();
    const submit = screen.getByRole("button", { name: "값 추가" }) as HTMLButtonElement;
    fireEvent.change(screen.getByLabelText(/^값 \(/), { target: { value: "1,000" } });
    expect(submit.disabled).toBe(true);
    expect(screen.getByRole("form", { name: "연도 값 추가" }).textContent).toContain("숫자만 입력해 주세요");
    fireEvent.change(screen.getByLabelText(/^값 \(/), { target: { value: "5" } });
    expect(submit.disabled).toBe(false);
    fireEvent.change(screen.getByLabelText(/^연도 \(/), { target: { value: "1800" } });
    expect(submit.disabled).toBe(true);
    expect(screen.getByRole("form", { name: "연도 값 추가" }).textContent).toContain("1900~9999");
    expect(callsOf(calls, "POST", "/reference-items/1/values")).toHaveLength(0);
  });

  it("409 같은 연도는 연도 칸 아래에 '값을 바꾸려면 정정을 쓰세요'를 보인다", async () => {
    open(makeFake(), { "POST /reference-items/1/values": () => apiError(409, "ALREADY_EXISTS", "서버", { field: "year" }) });
    await ready();
    fireEvent.change(screen.getByLabelText(/^연도 \(/), { target: { value: "2026" } });
    fireEvent.change(screen.getByLabelText(/^값 \(/), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "값 추가" }));
    const conflict = await screen.findByTestId("year-conflict");
    expect(conflict.textContent).toBe("2026년 값이 이미 있습니다. 값을 바꾸려면 정정을 쓰세요.");
  });

  it("422 서버 필드 오류(연도 범위·값 형식)와 404·503을 안내한다", async () => {
    let next: Response = apiError(422, "VALIDATION_ERROR", "x", {
      fields: [
        { field: "year", code: "OUT_OF_RANGE", message: "x" },
        { field: "value", code: "BAD_FORMAT", message: "x" },
      ],
    });
    open(makeFake(), { "POST /reference-items/1/values": () => next });
    await ready();
    fireEvent.change(screen.getByLabelText(/^값 \(/), { target: { value: "5" } });
    const form = () => screen.getByRole("form", { name: "연도 값 추가" });
    fireEvent.click(screen.getByRole("button", { name: "값 추가" }));
    await waitFor(() => expect(form().textContent).toContain("허용 범위를 벗어났습니다(1900~9999)"));
    expect(form().textContent).toContain("숫자만 입력해 주세요(쉼표·글자 없이)");
    next = apiError(503, "SERVICE_UNAVAILABLE");
    fireEvent.click(screen.getByRole("button", { name: "값 추가" }));
    await waitFor(() => expect(form().textContent).toContain("서버가 일시적으로 응답하지 못합니다"));
    next = apiError(404, "NOT_FOUND");
    fireEvent.click(screen.getByRole("button", { name: "값 추가" }));
    await waitFor(() => expect(form().textContent).toContain("대상을 찾을 수 없습니다"));
  });
});

describe("정정(R5)과 확인창(R6)", () => {
  const startCorrection = async (next = "13.00") => {
    fireEvent.click(screen.getByRole("button", { name: "2026년 값 정정" }));
    fireEvent.change(screen.getByLabelText("2026년 새 값"), { target: { value: next } });
    fireEvent.click(screen.getByRole("button", { name: "정정 확인" }));
    return screen.findByRole("dialog");
  };
  const usageOk = {
    items: [
      { dataset_id: 5, dataset_name: "월별 전력", team_id: 10, team_name: "영업", status: "active", column_count: 2 },
      { dataset_id: 6, dataset_name: "작년 전력", team_id: 20, team_name: "운영", status: "archived", column_count: 1 },
    ],
    total: 2,
    truncated: false,
  };

  it("확인창은 이전 값→새 값, '이 연도의 결과와 차트가 바뀝니다', R6 영향 데이터셋 목록, 감사 안내를 보인다", async () => {
    const { calls } = open(makeFake(), { "GET /reference-items/1/usage": () => json(200, usageOk) });
    await ready();
    expect(callsOf(calls, "GET", "/reference-items/1/usage")).toHaveLength(0); // 확인창을 열기 전에는 부르지 않는다
    await startCorrection();
    const text = screen.getByTestId("correction-text").textContent ?? "";
    expect(text).toContain("'전기요금_A팀'의 2026년 값을 12.50에서 13.00(으)로 바꿉니다");
    expect(text).toContain(IMPACT_TEXT);
    expect(IMPACT_TEXT).toBe("이 연도의 결과와 차트가 바뀝니다");
    expect(text).toContain("Superset 차트");
    await waitFor(() => expect(screen.getByTestId("correction-usage").textContent).toContain("월별 전력"));
    const usage = screen.getByTestId("correction-usage").textContent ?? "";
    expect(usage).toContain("작년 전력");
    expect(usage).toContain("보관됨");
    expect(dialog().textContent).toContain(AUDIT_NOTE_TEXT);
    expect(callsOf(calls, "GET", "/reference-items/1/usage")).toHaveLength(1);
    // 아직 정정하지 않았다
    expect(callsOf(calls, "PATCH", "/reference-items/1/values/11")).toHaveLength(0);
  });

  it("쓰는 데이터셋이 없으면 영향 줄을 생략하고 경고는 그대로 보인다", async () => {
    open(makeFake());
    await ready();
    await startCorrection();
    await waitFor(() => expect(screen.getByTestId("correction-usage").textContent).toBe(""));
    expect(screen.getByTestId("correction-text").textContent).toContain(IMPACT_TEXT);
  });

  it("R6가 실패하면 일반 경고로 바꾸고 정정은 막지 않는다", async () => {
    const { calls } = open(makeFake(), {
      "GET /reference-items/1/usage": () => apiError(503, "SERVICE_UNAVAILABLE"),
      "PATCH /reference-items/1/values/11": () => json(200, { value: value(11, 1, 2026, "13.00"), previous_value: "12.50", changed: true }),
    });
    await ready();
    await startCorrection();
    await waitFor(() => expect(screen.getByTestId("correction-usage").textContent).toBe(usageFailedText(2026)));
    expect(usageFailedText(2026)).toContain("모든 데이터셋의 2026년 결과가 바뀝니다");
    const confirm = screen.getByRole("button", { name: "정정하기" }) as HTMLButtonElement;
    expect(confirm.disabled).toBe(false);
    fireEvent.click(confirm);
    await waitFor(() => expect(callsOf(calls, "PATCH", "/reference-items/1/values/11")).toHaveLength(1));
  });

  it("R6가 오래 걸리면(시간 초과) 일반 경고로 바꾸고 기다리는 동안에도 정정할 수 있다", async () => {
    // 실제 시간에 기대지 않는다: 시간 초과용 setTimeout(표식 지연값)만 가로채 두었다가 시험이 직접 실행한다.
    const SENTINEL = 123457;
    usageTimeout.ms = SENTINEL;
    const realSetTimeout = globalThis.setTimeout;
    let fireTimeout: (() => void) | undefined;
    const spy = vi.spyOn(globalThis, "setTimeout").mockImplementation(((fn: TimerHandler, ms?: number, ...rest: unknown[]) => {
      if (ms === SENTINEL) {
        fireTimeout = fn as () => void;
        return 0 as unknown as ReturnType<typeof setTimeout>;
      }
      return realSetTimeout(fn as () => void, ms, ...rest);
    }) as typeof setTimeout);
    try {
      open(makeFake(), { "GET /reference-items/1/usage": () => new Promise<Response>(() => undefined) });
      await ready();
      await startCorrection();
      expect(fireTimeout).toBeDefined();
      expect(screen.getByTestId("correction-usage").textContent).toContain("확인하는 중");
      expect((screen.getByRole("button", { name: "정정하기" }) as HTMLButtonElement).disabled).toBe(false);
      act(() => fireTimeout?.());
    } finally {
      spy.mockRestore();
    }
    await waitFor(() => expect(screen.getByTestId("correction-usage").textContent).toBe(usageFailedText(2026)));
  });

  it("확인하면 PATCH {value}만 보내고(year·item_id 없음) 이전→새 값 안내를 보이며 표가 새 값이 된다", async () => {
    const fake = makeFake();
    const { calls } = open(fake, {
      "PATCH /reference-items/1/values/11": () => {
        fake.values[1][0] = value(11, 1, 2026, "13.00");
        return json(200, { value: fake.values[1][0], previous_value: "12.50", changed: true });
      },
    });
    await ready();
    await startCorrection("+13.00");
    fireEvent.click(screen.getByRole("button", { name: "정정하기" }));
    await waitFor(() => expect(screen.getByTestId("reference-notice").textContent).toContain("12.50 → 13.00"));
    expect(callsOf(calls, "PATCH", "/reference-items/1/values/11")[0].body).toEqual({ value: "13.00" });
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(valueRows()[0].textContent).toContain("13.00"));
  });

  it("취소하면 아무것도 보내지 않고 창이 닫힌다(Esc도 같다)", async () => {
    const { calls } = open(makeFake());
    await ready();
    await startCorrection();
    fireEvent.click(within(dialog()).getByRole("button", { name: "취소" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
    await startCorrection().catch(() => undefined);
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(calls.filter((c) => c.method === "PATCH")).toHaveLength(0);
  });

  it("같은 값이면 정정 확인 버튼이 꺼져 있고, 서버가 changed=false를 주면 '바꾸지 않았습니다'를 보인다", async () => {
    open(makeFake(), { "PATCH /reference-items/1/values/11": () => json(200, { value: value(11, 1, 2026, "12.50"), previous_value: "12.50", changed: false }) });
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "2026년 값 정정" }));
    expect((screen.getByRole("button", { name: "정정 확인" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("2026년 새 값"), { target: { value: "12.5" } }); // 숫자로는 같지만 글자는 다르다
    fireEvent.click(screen.getByRole("button", { name: "정정 확인" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "정정하기" }));
    await waitFor(() => expect(screen.getByTestId("reference-notice").textContent).toContain("바꾸지 않았습니다"));
    expect(screen.getByTestId("reference-notice").textContent).toContain("감사 기록 없음");
  });

  it("숫자가 아닌 새 값은 확인창을 열 수 없다", async () => {
    open(makeFake());
    await ready();
    fireEvent.click(screen.getByRole("button", { name: "2026년 값 정정" }));
    fireEvent.change(screen.getByLabelText("2026년 새 값"), { target: { value: "열두" } });
    expect((screen.getByRole("button", { name: "정정 확인" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("422는 창 안에 값 오류를 보이고 다시 시도할 수 있다. 403은 관리자 안내, 503은 다시 시도 안내", async () => {
    let next: Response = apiError(422, "VALIDATION_ERROR", "x", { fields: [{ field: "value", code: "OUT_OF_RANGE", message: "x" }] });
    open(makeFake(), { "PATCH /reference-items/1/values/11": () => next });
    await ready();
    await startCorrection();
    fireEvent.click(screen.getByRole("button", { name: "정정하기" }));
    await waitFor(() => expect(screen.getByTestId("correction-error").textContent).toContain("허용 범위를 벗어났습니다"));
    expect(screen.getByRole("button", { name: "다시 시도" })).toBeTruthy();
    next = apiError(403, "FORBIDDEN");
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.getByTestId("correction-error").textContent).toBe("관리자만 할 수 있습니다."));
    next = apiError(503, "WRITE_BUSY", "x", { retry_after: 3 });
    fireEvent.click(screen.getByRole("button", { name: "다시 시도" }));
    await waitFor(() => expect(screen.getByTestId("correction-error").textContent).toContain("잠시 뒤 다시 시도해 주세요. (약 3초 뒤)"));
    expect(screen.getByRole("dialog")).toBeTruthy(); // 실패해도 창은 닫히지 않는다
  });

  it("404(항목·값이 사라짐)는 창을 닫고 안내와 함께 목록을 다시 읽는다", async () => {
    const { calls } = open(makeFake(), { "PATCH /reference-items/1/values/11": () => apiError(404, "NOT_FOUND") });
    await ready();
    const before = callsOf(calls, "GET", "/reference-items").length;
    await startCorrection();
    fireEvent.click(screen.getByRole("button", { name: "정정하기" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect((await screen.findByTestId("reference-row-error")).textContent).toContain("대상을 찾을 수 없습니다");
    await waitFor(() => expect(callsOf(calls, "GET", "/reference-items").length).toBeGreaterThan(before));
  });

  it("R6 목록이 잘리면(truncated) 일부만 표시됨을 알린다", async () => {
    open(makeFake(), { "GET /reference-items/1/usage": () => json(200, { ...usageOk, total: 350, truncated: true }) });
    await ready();
    await startCorrection();
    await waitFor(() => expect(screen.getByTestId("correction-usage").textContent).toContain("일부만 표시됨(전체 350개 중 2개)"));
  });
});

describe("규칙·오류 문구", () => {
  it("이름: 빈 값·50자 초과·금지 글자", () => {
    expect(validateItemName("")).toBeTruthy();
    expect(validateItemName("가".repeat(50))).toBeNull();
    expect(validateItemName("가".repeat(51))).toContain("50자");
    expect(validateItemName("a]")).toBeTruthy();
    expect(validateItemName('a"b')).toBeTruthy();
    expect(validateItemName("a\nb")).toBeTruthy();
    expect(validateItemName("전기요금_A팀")).toBeNull();
    expect(validateDescription("x".repeat(201))).toContain("200자");
    expect(validateDescription("x".repeat(200))).toBeNull();
  });

  it("연도·값 검사와 값 정규화", () => {
    expect(validateYear("2026")).toBeNull();
    expect(validateYear("1899")).toContain("1900~9999");
    expect(validateYear("20.5")).toBeTruthy();
    expect(validateYear("")).toBeTruthy();
    for (const ok of ["12", "-3.5", "0.25", "+7", ".5", "1."]) expect(validateValue(ok)).toBeNull();
    for (const bad of ["", "abc", "1,000", "1e5", "NaN", "Infinity", "1.2.3", "٣"]) expect(validateValue(bad)).toBeTruthy();
    expect(validateValue("1".repeat(38))).toBeNull();
    expect(validateValue("1".repeat(39))).toContain("38자리");
    expect(normalizeValue(" +13.00 ")).toBe("13.00");
    expect(defaultYear(2026)).toBe("2027");
    expect(defaultYear(null, new Date(2030, 0, 1))).toBe("2030");
    expect(defaultYear(9999)).toBe("");
  });

  it("BASE_DATE_IN_USE·ALREADY_EXISTS(year)·기준값 필드 이름의 한국어 문구", () => {
    const inUse = new ApiError(422, { code: "BASE_DATE_IN_USE", message: "서버", details: { column: { column_id: 9, display_name: "전기료" } }, request_id: null });
    expect(describeApiError(inUse)).toBe("REF를 쓰는 수식이 있어 기준 날짜 열을 해제할 수 없습니다. 먼저 그 수식을 고치거나 다른 날짜 열로 바꾸세요. (REF를 쓰는 열: '전기료')");
    expect(describeApiError(new ApiError(422, { code: "BASE_DATE_IN_USE", message: "서버", details: null, request_id: null }))).toBe(
      "REF를 쓰는 수식이 있어 기준 날짜 열을 해제할 수 없습니다. 먼저 그 수식을 고치거나 다른 날짜 열로 바꾸세요.",
    );
    expect(describeApiError(new ApiError(409, { code: "ALREADY_EXISTS", message: "서버", details: { field: "year" }, request_id: null }))).toBe("이 연도의 값이 이미 있습니다. 값을 바꾸려면 정정을 쓰세요.");
    const fields = new ApiError(422, {
      code: "VALIDATION_ERROR",
      message: "서버",
      details: { fields: [{ field: "year", code: "OUT_OF_RANGE" }, { field: "value", code: "BAD_FORMAT" }, { field: "description", code: "TOO_LONG" }] },
      request_id: null,
    });
    expect(describeApiError(fields)).toBe("입력한 내용을 확인해 주세요. (연도: 허용 범위를 벗어났습니다, 값: 형식이 맞지 않습니다, 설명: 너무 깁니다)");
  });
});
