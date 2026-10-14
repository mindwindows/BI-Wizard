import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler, type RecordedCall } from "../../test-utils";

/**
 * S5 점검(D7·D8)과 S9의 '뷰 재생성' 구역(D9·D10) 시험(단위 1d). 응답은 05 §2-4 계약대로 만든 가짜 서버다.
 * 실제 백엔드와 같다는 보증이 아니다. 목록 응답이 `{items,total}`이든 배열이든 받는지도 함께 본다.
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

const SUMMARIES = [
  { dataset_id: 7, dataset_name: "월별 매출", team_name: "영업", column_id: 5, column_name: "이익률", error_count: 12 },
  { dataset_id: 9, dataset_name: "재고", team_name: "운영", column_id: 11, column_name: "회전율", error_count: 1200 },
];

const CELLS = [
  { row_id: 2, period: "2026-02-01", column_id: 5, error: "E1", message: "0으로 나누어 계산할 수 없습니다." },
  { row_id: 5, period: null, column_id: 5, error: "E3", message: "날짜 범위를 벗어났습니다." },
];

async function open(path: string, handlers: Record<string, Handler>, me = ADMIN_ME): Promise<RecordedCall[]> {
  // S9에는 1e의 'Superset 동기' 구역도 있다. 이 파일은 뷰 재생성 구역을 보므로 동기 목록은 빈 목록으로 둔다.
  const { calls } = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, me), "GET /superset/datasets": () => json(200, { items: [], total: 0, limit: 200, offset: 0 }), ...handlers });
  render(<App router={createTestRouter(BASE, `${BASE}${path}`)} />);
  return calls;
}

describe("S5 점검", () => {
  it("오류 칸이 있는 열 목록(데이터셋·팀·열·오류 칸 수)과 작업공간 링크", async () => {
    await open("/checks", { "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }) });
    const table = await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getAllByRole("cell").slice(0, 4).map((c) => c.textContent)).toEqual(["월별 매출", "영업", "이익률", "12"]);
    expect(within(rows[1]).getAllByRole("cell")[3].textContent).toBe("1,200");
    expect(within(rows[0]).getByRole("link", { name: "작업공간 열기" }).getAttribute("href")).toBe(`${BASE}/datasets/7`);
    expect(within(rows[0]).getByRole("link", { name: "월별 매출" }).getAttribute("href")).toBe(`${BASE}/datasets/7`);
  });

  it("E4(기준값 없음) 칸은 이유와 기준값 화면 링크를 보이고, 화면 머리에 E4 안내가 있다 (FU-3)", async () => {
    await open("/checks?dataset=7&column=5", {
      "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }),
      "GET /datasets/7/formula-errors": () =>
        json(200, { items: [{ row_id: 9, period: "2027-01-01", column_id: 5, error: "E4", message: "이 행의 기준 날짜가 속한 연도의 기준값이 등록되어 있지 않아 계산하지 못했습니다." }, ...CELLS], total: 3, limit: 50, offset: 0 }),
    });
    const detail = await screen.findByRole("table", { name: "이익률 오류 칸 목록" });
    const rows = within(detail).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByRole("cell").slice(0, 3).map((c) => c.textContent)).toEqual(["2027-01-01", "#9", "E4"]);
    expect(within(rows[0]).getByRole("link", { name: "기준값 화면 열기" }).getAttribute("href")).toBe(`${BASE}/reference-values`);
    expect(within(rows[1]).queryByRole("link", { name: "기준값 화면 열기" })).toBeNull(); // E1에는 없다
    expect(screen.getByTestId("checks-e4-help").textContent).toContain("E4(기준값 없음)");
  });

  it("E4 이유 문구가 서버에서 비어 있으면 기본 E4 문구를 쓴다", async () => {
    await open("/checks?dataset=7&column=5", {
      "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }),
      "GET /datasets/7/formula-errors": () => json(200, { items: [{ row_id: 9, period: null, column_id: 5, error: "E4", message: "" }], total: 1, limit: 50, offset: 0 }),
    });
    const detail = await screen.findByRole("table", { name: "이익률 오류 칸 목록" });
    expect(within(detail).getAllByRole("row")[1].textContent).toContain("기준값이 등록되어 있지 않아");
  });

  it("목록 응답이 배열이어도 받는다", async () => {
    await open("/checks", { "GET /checks/formula-errors": () => json(200, SUMMARIES) });
    expect(await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" })).toBeTruthy();
  });

  it("'오류 칸 보기'를 누르면 해당 데이터셋·열의 오류 칸(기간·행·코드·이유)을 column_id 필터로 읽어 보여 준다", async () => {
    const calls = await open("/checks", {
      "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }),
      "GET /datasets/7/formula-errors": () => json(200, { items: CELLS, total: 2, limit: 50, offset: 0 }),
    });
    await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" });
    fireEvent.click(screen.getAllByRole("button", { name: "오류 칸 보기" })[0]);
    const detail = await screen.findByRole("table", { name: "이익률 오류 칸 목록" });
    const request = calls.find((c) => c.path === "/datasets/7/formula-errors");
    expect(request?.query.get("column_id")).toBe("5");
    const rows = within(detail).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2026-02-01", "#2", "E1", "0으로 나누어 계산할 수 없습니다."]);
    expect(within(rows[1]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["", "#5", "E3", "날짜 범위를 벗어났습니다."]);
    // 다시 누르면 닫힌다
    fireEvent.click(screen.getByRole("button", { name: "오류 칸 닫기" }));
    expect(screen.queryByRole("table", { name: "이익률 오류 칸 목록" })).toBeNull();
  });

  it("?dataset=&column= 주소는 그 열을 처음부터 펼친다(수식 보기의 '점검 화면에서 보기')", async () => {
    await open("/checks?dataset=7&column=5", {
      "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }),
      "GET /datasets/7/formula-errors": () => json(200, { items: CELLS, total: 2, limit: 50, offset: 0 }),
    });
    expect(await screen.findByRole("table", { name: "이익률 오류 칸 목록" })).toBeTruthy();
    expect(screen.queryByRole("table", { name: "회전율 오류 칸 목록" })).toBeNull();
  });

  it("오류 칸이 없으면 정상 안내", async () => {
    await open("/checks", { "GET /checks/formula-errors": () => json(200, { items: [], total: 0, limit: 50, offset: 0 }) });
    expect((await screen.findByTestId("no-formula-errors")).textContent).toContain("계산 오류 칸이 없습니다");
  });

  it("429 PREVIEW_BUSY는 쉬운 문구와 다시 시도로 복구", async () => {
    let n = 0;
    await open("/checks", {
      "GET /checks/formula-errors": () => (n++ === 0 ? apiError(429, "PREVIEW_BUSY", "서버", { retry_after: 2 }) : json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 })),
    });
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("지금 계산 요청이 많습니다");
    expect(alert.textContent).toContain("약 2초 뒤");
    fireEvent.click(within(alert).getByRole("button", { name: "다시 시도" }));
    expect(await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" })).toBeTruthy();
  });

  it("오류 칸 목록(D8)이 바쁘면 그 구역에서만 안내하고 목록은 유지", async () => {
    await open("/checks", {
      "GET /checks/formula-errors": () => json(200, { items: SUMMARIES, total: 2, limit: 50, offset: 0 }),
      "GET /datasets/7/formula-errors": () => apiError(429, "PREVIEW_BUSY"),
    });
    await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" });
    fireEvent.click(screen.getAllByRole("button", { name: "오류 칸 보기" })[0]);
    const group = await screen.findByRole("group", { name: "이익률 오류 칸" });
    expect((await within(group).findByRole("alert")).textContent).toContain("지금 계산 요청이 많습니다");
    expect(screen.getByRole("table", { name: "계산 오류 칸이 있는 열" })).toBeTruthy();
  });

  it("쪽 이동: 50개를 넘으면 다음 쪽을 offset으로 읽는다", async () => {
    const many = Array.from({ length: 50 }, (_, i) => ({ ...SUMMARIES[0], column_id: 100 + i, column_name: `열${i}` }));
    const calls = await open("/checks", { "GET /checks/formula-errors": (call) => json(200, { items: call.query.get("offset") === "50" ? SUMMARIES : many, total: 52, limit: 50, offset: Number(call.query.get("offset")) }) });
    await screen.findByRole("table", { name: "계산 오류 칸이 있는 열" });
    fireEvent.click(screen.getByRole("button", { name: "다음" }));
    await waitFor(() => expect(calls.some((c) => c.query.get("offset") === "50")).toBe(true));
    expect(await screen.findByText("회전율")).toBeTruthy();
  });
});

describe("S9 뷰 재생성 구역(D9·D10, 관리자)", () => {
  const FAILED = {
    views: 8,
    views_failed_count: 2,
    failed: [
      { dataset_id: 7, dataset_name: "월별 매출", reason: "VIEW_CREATE_FAILED", since: "2026-10-12T09:30:00+09:00" },
      { dataset_id: 9, dataset_name: "재고", reason: "LOCK_TIMEOUT", since: "2026-10-12T10:05:00+09:00" },
    ],
  };

  it("확인한 개수·실패 목록(사유·시각)을 보여 준다", async () => {
    await open("/admin/status", { "GET /checks/views": () => json(200, FAILED) });
    expect((await screen.findByTestId("views-summary")).textContent).toBe("확인한 데이터셋 8개 중 실패 2개");
    const table = screen.getByRole("table", { name: "뷰 재생성 실패 목록" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(within(rows[0]).getAllByRole("cell").slice(0, 3).map((c) => c.textContent)).toEqual(["월별 매출", "VIEW_CREATE_FAILED", "2026-10-12 09:30"]);
    expect(within(rows[0]).getByRole("link", { name: "월별 매출" }).getAttribute("href")).toBe(`${BASE}/datasets/7`);
  });

  it("실패가 없으면 안내만", async () => {
    await open("/admin/status", { "GET /checks/views": () => json(200, { views: 5, views_failed_count: 0, failed: [] }) });
    expect((await screen.findByTestId("no-failed-views")).textContent).toContain("없습니다");
    expect(screen.queryByRole("button", { name: /다시 시도/ })).toBeNull();
  });

  it("'전부 다시 시도'는 dataset_ids 없이 보내고 결과(만든 개수·남은 실패)를 보인 뒤 현황을 다시 읽는다", async () => {
    let status = FAILED;
    const calls = await open("/admin/status", {
      "GET /checks/views": () => json(200, status),
      "POST /checks/views/retry": () => {
        status = { views: 8, views_failed_count: 0, failed: [] };
        return json(200, { rebuilt: 2, views_failed_count: 0 });
      },
    });
    await screen.findByRole("table", { name: "뷰 재생성 실패 목록" });
    fireEvent.click(screen.getByRole("button", { name: "실패한 항목 전부 다시 시도" }));
    expect((await screen.findByTestId("views-retry-result")).textContent).toContain("2개를 다시 만들었습니다.");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({});
    expect((await screen.findByTestId("no-failed-views")).textContent).toContain("없습니다");
  });

  it("한 데이터셋만 다시 시도하면 dataset_ids에 그 번호를 보내고, 아직 실패가 남으면 알린다", async () => {
    const calls = await open("/admin/status", {
      "GET /checks/views": () => json(200, FAILED),
      "POST /checks/views/retry": () => json(200, { rebuilt: 0, views_failed_count: 2 }),
    });
    await screen.findByRole("table", { name: "뷰 재생성 실패 목록" });
    fireEvent.click(screen.getAllByRole("button", { name: "이 데이터셋 다시 시도" })[1]);
    const result = await screen.findByTestId("views-retry-result");
    expect(calls.find((c) => c.method === "POST")?.body).toEqual({ dataset_ids: [9] });
    expect(result.textContent).toContain("아직 2개가 실패 상태입니다");
  });

  it("DEFINITION_BUSY(503)는 안내하고 다시 시도할 수 있다", async () => {
    await open("/admin/status", {
      "GET /checks/views": () => json(200, FAILED),
      "POST /checks/views/retry": () => apiError(503, "DEFINITION_BUSY", "서버", { retry_after: 1 }),
    });
    await screen.findByRole("table", { name: "뷰 재생성 실패 목록" });
    fireEvent.click(screen.getByRole("button", { name: "실패한 항목 전부 다시 시도" }));
    expect((await screen.findByText(/다른 작업이 진행 중입니다/)).textContent).toContain("약 1초 뒤");
  });

  it("현황을 못 읽으면 쉬운 문구와 다시 불러오기", async () => {
    await open("/admin/status", { "GET /checks/views": () => apiError(500, "INTERNAL_ERROR") });
    expect((await screen.findByRole("alert")).textContent).toContain("예기치 않은 오류");
    expect(screen.getByRole("button", { name: "다시 불러오기" })).toBeTruthy();
  });

  it("관리자가 아니면 화면을 쓸 수 없고 D9를 부르지 않는다", async () => {
    const calls = await open("/admin/status", { "GET /checks/views": () => json(200, FAILED) }, MEMBER_ME);
    expect((await screen.findByRole("alert")).textContent).toContain("관리자만");
    expect(calls.some((c) => c.path === "/checks/views")).toBe(false);
  });
});
