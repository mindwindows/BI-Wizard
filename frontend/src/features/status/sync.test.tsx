import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler } from "../../test-utils";
import { MAX_POLLS, POLL_INTERVAL_MS } from "./SupersetSyncSection";

/**
 * S9 'Superset 동기' 구역(E1 목록, E2 다시 동기)과 S2 목록의 '동기 상태' 열 시험(단위 1e).
 * 응답은 05 §2-5 계약대로 만든 가짜 서버다.
 */
const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const row = (dataset_id: number, sync_status: string, extra: Record<string, unknown> = {}) => ({
  dataset_id,
  superset_name: `[영업] 데이터셋${dataset_id}`,
  sync_status,
  synced_at: sync_status === "registered" ? "2026-10-12T09:30:00+09:00" : null,
  last_error: null,
  ...extra,
});

const page = <T,>(items: T[], total = items.length, offset = 0) => json(200, { items, total, limit: 200, offset });

function open(path: string, handlers: Record<string, Handler>, me: unknown = ADMIN_ME) {
  const installed = installFetch(
    {
      ...HEALTH_HANDLERS,
      "GET /me": () => json(200, me),
      "GET /checks/views": () => json(200, { views: 3, views_failed_count: 0, failed: [] }),
      "GET /teams": () => page([{ id: 10, code: "sales", name: "영업", is_active: true }]),
      ...handlers,
    },
    BASE,
  );
  render(<App router={createTestRouter(BASE, `${BASE}${path}`)} />);
  return installed;
}

const section = async () => within(await screen.findByTestId("sync-section"));

describe("S9 Superset 동기 구역", () => {
  it("뷰 재생성 구역과 함께 보이고, 상태별 건수와 목록(배지, 최근 등록 시각, 실패 사유)을 보여 준다", async () => {
    open("/admin/status", {
      "GET /superset/datasets": () =>
        page([row(1, "registered"), row(2, "pending"), row(3, "failed", { last_error: "SUPERSET_UNAVAILABLE: 연결 실패" }), row(4, "registered")]),
    });
    const sync = await section();
    expect((await sync.findByTestId("sync-summary")).textContent).toBe("전체 4개 중 등록됨 2개, 등록 대기 1개, 등록 실패 1개");
    expect(screen.getByRole("region", { name: "뷰 재생성" })).toBeTruthy();
    const rows = within(sync.getByRole("table", { name: "Superset 동기 목록" })).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").slice(0, 4).map((c) => c.textContent))).toEqual([
      ["[영업] 데이터셋1", "등록됨", "2026-10-12 09:30", ""],
      ["[영업] 데이터셋2", "등록 대기", "", ""],
      ["[영업] 데이터셋3", "등록 실패", "", "SUPERSET_UNAVAILABLE: 연결 실패"],
      ["[영업] 데이터셋4", "등록됨", "2026-10-12 09:30", ""],
    ]);
    // 줄바꿈 방지 CSS가 걸리는 훅(표는 가로 스크롤 영역 안, 이름·사유 칸만 줄바꿈 허용)
    const table = sync.getByRole("table", { name: "Superset 동기 목록" });
    expect(table.classList.contains("sync-table")).toBe(true);
    expect(table.closest(".table-scroll")).not.toBeNull();
    expect(rows[2].querySelector("td.sync-error")?.textContent).toBe("SUPERSET_UNAVAILABLE: 연결 실패");
    expect(rows[2].querySelector("td.sync-name")).not.toBeNull();
    expect(within(rows[2]).getByRole("link", { name: "[영업] 데이터셋3" }).getAttribute("href")).toBe(`${BASE}/datasets/3`);
    // 다시 동기 버튼은 등록되지 않은 항목에만 있다.
    expect(within(rows[0]).queryByRole("button")).toBeNull();
    expect(within(rows[1]).getByRole("button", { name: "다시 동기" })).toBeTruthy();
  });

  it("관리자가 아니면 막고 E1도 부르지 않는다", async () => {
    const { calls } = open("/admin/status", { "GET /superset/datasets": () => page([row(1, "registered")]) }, MEMBER_ME);
    expect((await screen.findByTestId("screen-S9")).textContent).toContain("관리자만 사용할 수 있는 화면입니다");
    expect(calls.some((c) => c.path === "/superset/datasets")).toBe(false);
  });

  it("상태 필터는 화면에서 걸러 건수와 쪽 이동에 반영한다", async () => {
    open("/admin/status", { "GET /superset/datasets": () => page([row(1, "registered"), row(2, "pending"), row(3, "failed")]) });
    const sync = await section();
    await sync.findByRole("table", { name: "Superset 동기 목록" });
    fireEvent.change(sync.getByLabelText("상태 필터"), { target: { value: "failed" } });
    const rows = within(sync.getByRole("table", { name: "Superset 동기 목록" })).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(1);
    expect(rows[0].textContent).toContain("데이터셋3");
    fireEvent.change(sync.getByLabelText("상태 필터"), { target: { value: "pending" } });
    expect(within(sync.getByRole("table", { name: "Superset 동기 목록" })).getAllByRole("row")).toHaveLength(2);
  });

  it("이 상태의 항목이 없으면 안내하고, 데이터셋이 하나도 없으면 다른 안내를 한다", async () => {
    open("/admin/status", { "GET /superset/datasets": () => page([row(1, "registered")]) });
    const sync = await section();
    await sync.findByRole("table", { name: "Superset 동기 목록" });
    fireEvent.change(sync.getByLabelText("상태 필터"), { target: { value: "failed" } });
    expect(sync.getByTestId("no-sync-items").textContent).toBe("이 상태의 데이터셋이 없습니다.");
    cleanup();
    open("/admin/status", { "GET /superset/datasets": () => page([]) });
    expect((await (await section()).findByTestId("no-sync-items")).textContent).toBe("등록할 데이터셋이 없습니다.");
  });

  it("50개씩 쪽으로 나누어 보여 준다", async () => {
    const many = Array.from({ length: 120 }, (_, i) => row(i + 1, "registered"));
    open("/admin/status", { "GET /superset/datasets": () => page(many) });
    const sync = await section();
    const table = await sync.findByRole("table", { name: "Superset 동기 목록" });
    expect(within(table).getAllByRole("row")).toHaveLength(51);
    expect(sync.getByText("120개 중 1–50")).toBeTruthy();
    fireEvent.click(sync.getByRole("button", { name: "다음" }));
    expect(sync.getByText("120개 중 51–100")).toBeTruthy();
    fireEvent.click(sync.getByRole("button", { name: "다음" }));
    expect(sync.getByText("120개 중 101–120")).toBeTruthy();
    expect((sync.getByRole("button", { name: "다음" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("서버가 200개씩 주면 total에 닿을 때까지 이어서 읽는다", async () => {
    const all = Array.from({ length: 250 }, (_, i) => row(i + 1, "registered"));
    const { calls } = open("/admin/status", {
      "GET /superset/datasets": (call) => {
        const offset = Number(call.query.get("offset") ?? 0);
        return page(all.slice(offset, offset + 200), 250, offset);
      },
    });
    const sync = await section();
    expect((await sync.findByTestId("sync-summary")).textContent).toContain("전체 250개");
    expect(calls.filter((c) => c.path === "/superset/datasets").map((c) => c.query.get("offset"))).toEqual(["0", "200"]);
  });

  it("E1 응답이 배열이어도 받는다", async () => {
    open("/admin/status", { "GET /superset/datasets": () => json(200, [row(1, "failed")]) });
    expect((await (await section()).findByTestId("sync-summary")).textContent).toContain("등록 실패 1개");
  });

  it("목록을 못 읽으면 오류와 다시 불러오기를 보이고 뷰 재생성 구역은 그대로 쓴다", async () => {
    open("/admin/status", { "GET /superset/datasets": () => apiError(503, "SERVICE_UNAVAILABLE") });
    const sync = await section();
    expect((await sync.findByRole("alert")).textContent).toContain("서버가 일시적으로 응답하지 못합니다");
    expect(sync.getByRole("button", { name: "다시 불러오기" })).toBeTruthy();
    expect(await screen.findByTestId("views-summary")).toBeTruthy();
  });

  describe("다시 동기 (E2)", () => {
    const states = () => {
      const state = { statuses: { 2: "pending", 3: "failed" } as Record<number, string> };
      const handlers: Record<string, Handler> = {
        "GET /superset/datasets": () => page([row(1, "registered"), row(2, state.statuses[2]), row(3, state.statuses[3])]),
        "POST /superset/sync": (call) => {
          const ids = (call.body as { dataset_ids?: number[] }).dataset_ids ?? [2, 3];
          return json(202, { accepted: ids });
        },
      };
      return { state, handlers };
    };

    it("전부 다시 동기: 본문에 dataset_ids 없이 202를 받고 목록을 다시 읽는다", async () => {
      const { handlers } = states();
      const { calls } = open("/admin/status", handlers);
      const sync = await section();
      await sync.findByRole("table", { name: "Superset 동기 목록" });
      const before = calls.filter((c) => c.path === "/superset/datasets").length;
      fireEvent.click(sync.getByRole("button", { name: "대기·실패 전부 다시 동기 (2개)" }));
      expect((await sync.findByTestId("sync-accepted")).textContent).toContain("2개를 다시 등록하도록 접수했습니다");
      const post = calls.find((c) => c.method === "POST" && c.path === "/superset/sync")!;
      expect(post.body).toEqual({});
      await waitFor(() => expect(calls.filter((c) => c.path === "/superset/datasets").length).toBeGreaterThan(before));
    });

    it("데이터셋별 다시 동기는 그 번호만 보낸다", async () => {
      const { handlers } = states();
      const { calls } = open("/admin/status", handlers);
      const sync = await section();
      const table = await sync.findByRole("table", { name: "Superset 동기 목록" });
      fireEvent.click(within(within(table).getAllByRole("row")[3]).getByRole("button", { name: "다시 동기" }));
      await sync.findByTestId("sync-accepted");
      expect(calls.find((c) => c.method === "POST" && c.path === "/superset/sync")!.body).toEqual({ dataset_ids: [3] });
    });

    it("대기·실패가 없으면 전부 다시 동기 버튼은 비활성이다", async () => {
      open("/admin/status", { "GET /superset/datasets": () => page([row(1, "registered")]) });
      const sync = await section();
      await sync.findByRole("table", { name: "Superset 동기 목록" });
      expect((sync.getByRole("button", { name: /전부 다시 동기/ }) as HTMLButtonElement).disabled).toBe(true);
    });

    it("접수 실패(404, 권한 없음 403)는 쉬운 오류로 보인다", async () => {
      const { handlers } = states();
      open("/admin/status", { ...handlers, "POST /superset/sync": () => apiError(403, "FORBIDDEN") });
      const sync = await section();
      await sync.findByRole("table", { name: "Superset 동기 목록" });
      fireEvent.click(sync.getByRole("button", { name: /전부 다시 동기/ }));
      expect((await sync.findByRole("alert")).textContent).toContain("이 작업을 할 권한이 없습니다");
    });
  });

  describe("대기 항목 자동 다시 읽기", () => {
    it("대기 항목이 있으면 5초마다 다시 읽고, 모두 끝나면 멈춘다", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      let reads = 0;
      const { calls } = open("/admin/status", {
        "GET /superset/datasets": () => {
          reads += 1;
          return page([row(1, reads >= 3 ? "registered" : "pending")]);
        },
      });
      const tick = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
      await tick(0);
      await tick(0);
      const count = () => calls.filter((c) => c.path === "/superset/datasets").length;
      expect(count()).toBe(1);
      await tick(POLL_INTERVAL_MS - 100);
      expect(count()).toBe(1);
      await tick(200);
      expect(count()).toBe(2);
      await tick(POLL_INTERVAL_MS);
      expect(count()).toBe(3);
      expect(screen.getByTestId("sync-summary").textContent).toContain("등록됨 1개");
      await tick(POLL_INTERVAL_MS * 5);
      expect(count()).toBe(3);
    });

    it("대기가 계속되면 최대 횟수에서 멈추고 안내한다", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      const { calls } = open("/admin/status", { "GET /superset/datasets": () => page([row(1, "pending")]) });
      const tick = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
      await tick(0);
      for (let i = 0; i < MAX_POLLS + 3; i += 1) await tick(POLL_INTERVAL_MS);
      expect(calls.filter((c) => c.path === "/superset/datasets")).toHaveLength(MAX_POLLS + 1);
      expect(screen.getByTestId("sync-poll-stopped").textContent).toContain("자동으로 다시 읽기를 멈췄습니다");
    });

    it("화면을 떠나면 타이머가 정리된다", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      const { calls } = open("/admin/status", { "GET /superset/datasets": () => page([row(1, "pending")]) });
      const tick = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
      await tick(0);
      cleanup();
      const after = calls.length;
      await tick(POLL_INTERVAL_MS * 5);
      expect(calls).toHaveLength(after);
      expect(vi.getTimerCount()).toBe(0);
    });

    it("대기가 없으면 처음부터 다시 읽지 않는다", async () => {
      vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
      const { calls } = open("/admin/status", { "GET /superset/datasets": () => page([row(1, "registered"), row(2, "failed")]) });
      const tick = (ms: number) => act(async () => void (await vi.advanceTimersByTimeAsync(ms)));
      await tick(0);
      await tick(POLL_INTERVAL_MS * 4);
      expect(calls.filter((c) => c.path === "/superset/datasets")).toHaveLength(1);
    });
  });
});

describe("S2 데이터셋 목록의 동기 상태 열", () => {
  const DATASETS = [
    { id: 7, team_id: 10, name: "월별 매출", date_unit: "month", base_date_column_id: null, status: "active", def_version: 3, created_by: { id: 1, display_name: "관리자 김" }, created_at: "2026-10-12T09:30:00+09:00" },
    { id: 8, team_id: 10, name: "일별 가동", date_unit: "day", base_date_column_id: null, status: "active", def_version: 1, created_by: { id: 2, display_name: "입력자 박" }, created_at: "2026-09-01T00:10:00+09:00" },
    { id: 9, team_id: 10, name: "재고", date_unit: "day", base_date_column_id: null, status: "active", def_version: 1, created_by: { id: 2, display_name: "입력자 박" }, created_at: "2026-09-02T00:10:00+09:00" },
  ];

  const handlers = (e1: Handler): Record<string, Handler> => ({
    "GET /datasets": () => page(DATASETS),
    "GET /superset/datasets": e1,
  });

  it("표시된 데이터셋 번호로 E1을 한 번 부르고 상태 배지를 보인다", async () => {
    const { calls } = open(
      "/datasets",
      handlers(() => page([row(7, "registered"), row(8, "pending"), row(9, "failed", { last_error: "연결 실패" })])),
      MEMBER_ME,
    );
    const table = await screen.findByRole("table", { name: "데이터셋 목록" });
    expect(within(table).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["이름", "팀", "날짜 단위", "생성자", "생성일", "동기 상태"]);
    await waitFor(() => expect(screen.getByTestId("sync-7").textContent).toBe("등록됨"));
    expect(screen.getByTestId("sync-8").textContent).toBe("등록 대기");
    expect(screen.getByTestId("sync-9").textContent).toBe("등록 실패");
    const e1 = calls.filter((c) => c.path === "/superset/datasets");
    expect(e1).toHaveLength(1);
    expect(e1[0].query.get("dataset_ids")).toBe("7,8,9");
    expect(e1[0].query.get("limit")).toBe("200");
  });

  it("실패 사유(last_error)는 서버가 준 경우에만 툴팁이고 일반 사용자는 null이라 없다", async () => {
    open("/datasets", handlers(() => page([row(7, "registered"), row(8, "pending"), row(9, "failed", { last_error: null })])), MEMBER_ME);
    await waitFor(() => expect(screen.getByTestId("sync-9").textContent).toBe("등록 실패"));
    expect(screen.getByTestId("sync-9").querySelector("[title]")).toBeNull();
    expect(document.body.textContent).not.toContain("연결 실패");
  });

  it("관리자에게는 사유가 툴팁으로 붙는다", async () => {
    open("/datasets", handlers(() => page([row(9, "failed", { last_error: "연결 실패" })])), ADMIN_ME);
    await waitFor(() => expect(screen.getByTestId("sync-9").textContent).toBe("등록 실패"));
    expect(screen.getByTestId("sync-9").querySelector("[title]")?.getAttribute("title")).toBe("연결 실패");
  });

  it("E1이 실패해도 목록은 그대로 보이고 열에는 '확인 못함'을 둔다", async () => {
    open("/datasets", handlers(() => apiError(503, "SERVICE_UNAVAILABLE")), MEMBER_ME);
    await screen.findByRole("table", { name: "데이터셋 목록" });
    await waitFor(() => expect(screen.getByTestId("sync-7").textContent).toBe("확인 못함"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("서버가 일부 번호의 상태를 주지 않으면 그 칸만 '확인 못함'이다", async () => {
    open("/datasets", handlers(() => page([row(7, "registered")])), MEMBER_ME);
    await waitFor(() => expect(screen.getByTestId("sync-7").textContent).toBe("등록됨"));
    expect(screen.getByTestId("sync-8").textContent).toBe("확인 못함");
  });

  it("상태를 읽는 동안에는 '확인 중'을 보인다", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => (release = resolve));
    open("/datasets", handlers(async () => (await gate, page([row(7, "registered")]))), MEMBER_ME);
    await screen.findByRole("table", { name: "데이터셋 목록" });
    expect(screen.getByTestId("sync-7").textContent).toBe("확인 중…");
    release();
    await waitFor(() => expect(screen.getByTestId("sync-7").textContent).toBe("등록됨"));
  });
});
