import { embedDashboard } from "@superset-ui/embedded-sdk";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, MEMBER_ME, apiError, installFetch, json, type Handler } from "../../test-utils";
import { SUPPORTED_CHARTS } from "./AuthorGuide";

vi.mock("@superset-ui/embedded-sdk", () => ({ embedDashboard: vi.fn() }));

/** S7 대시보드 보기, S8 대시보드 연결 관리 시험(단위 1e). 응답은 05 §2-5 계약대로 만든 가짜 서버다. */
const BASE = "/bi-wizard";
const UUID_1 = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
const UUID_2 = "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb";
const TOKEN = "hdr.S7-PAYLOAD.sig";

const DASHBOARDS = [
  { id: 1, name: "매출 현황", embedded_uuid: UUID_1, is_active: true },
  { id: 2, name: "비용 현황", embedded_uuid: UUID_2, is_active: true },
];
const INACTIVE = { id: 3, name: "옛 대시보드", embedded_uuid: "cccccccc-3333-4333-8333-cccccccccccc", is_active: false };

const page = <T,>(items: T[]) => json(200, { items, total: items.length, limit: 200, offset: 0 });

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
  vi.mocked(embedDashboard).mockImplementation(async (params) => {
    await params.fetchGuestToken();
    return { unmount: vi.fn() } as never;
  });
});

afterEach(() => {
  cleanup();
  vi.mocked(embedDashboard).mockReset();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

function open(path: string, handlers: Record<string, Handler>, me: unknown = MEMBER_ME) {
  const installed = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, me), ...handlers }, BASE);
  render(<App router={createTestRouter(BASE, `${BASE}${path}`)} />);
  return installed;
}

const tokenOk: Handler = () => json(200, { token: TOKEN, expires_in: 300 });

describe("S7 대시보드 목록·보기 (E3, E6)", () => {
  it("활성 대시보드 이름 목록을 보이고, 고르면 그 대시보드를 임베드한다(별도 마운트)", async () => {
    const { calls } = open("/dashboards", {
      "GET /dashboards": () => page([...DASHBOARDS, INACTIVE]),
      "POST /dashboards/1/guest-token": tokenOk,
      "POST /dashboards/2/guest-token": tokenOk,
    });
    const list = await screen.findByRole("navigation", { name: "대시보드 목록" });
    expect(within(list).getAllByRole("button").map((b) => b.textContent)).toEqual(["매출 현황", "비용 현황"]);
    expect(screen.getByTestId("pick-dashboard").textContent).toContain("고르세요");
    expect(embedDashboard).not.toHaveBeenCalled();
    const listCall = calls.find((c) => c.path === "/dashboards")!;
    expect(listCall.query.has("include_inactive")).toBe(false);

    fireEvent.click(within(list).getByRole("button", { name: "매출 현황" }));
    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    expect(vi.mocked(embedDashboard).mock.calls[0][0].id).toBe(UUID_1);
    expect(screen.getByRole("heading", { name: "매출 현황" })).toBeTruthy();

    fireEvent.click(within(list).getByRole("button", { name: "비용 현황" }));
    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(2));
    expect(vi.mocked(embedDashboard).mock.calls[1][0].id).toBe(UUID_2);
    // 입장권은 포털 번호로만 요청한다.
    expect(calls.filter((c) => c.method === "POST").map((c) => c.path)).toEqual(["/dashboards/1/guest-token", "/dashboards/2/guest-token"]);
  });

  it("주소의 ?d=<번호>로 선택을 기억한다(uuid나 입장권은 주소에 없다)", async () => {
    open("/dashboards?d=2", { "GET /dashboards": () => page(DASHBOARDS), "POST /dashboards/2/guest-token": tokenOk });
    await waitFor(() => expect(embedDashboard).toHaveBeenCalledTimes(1));
    expect(vi.mocked(embedDashboard).mock.calls[0][0].id).toBe(UUID_2);
    expect(window.location.href).not.toContain(UUID_2);
    expect(window.location.href).not.toContain("PAYLOAD");
  });

  it("목록 응답이 배열이어도 받는다", async () => {
    open("/dashboards", { "GET /dashboards": () => json(200, DASHBOARDS) });
    expect(await screen.findByRole("navigation", { name: "대시보드 목록" })).toBeTruthy();
  });

  it("빈 목록이면 안내한다", async () => {
    open("/dashboards", { "GET /dashboards": () => page([]) });
    expect((await screen.findByTestId("no-dashboards")).textContent).toContain("연결된 대시보드가 없습니다");
  });

  it("목록을 읽는 동안 로딩, 실패하면 쉬운 오류와 다시 불러오기", async () => {
    let fail = true;
    open("/dashboards", { "GET /dashboards": () => (fail ? apiError(503, "SERVICE_UNAVAILABLE") : page(DASHBOARDS)) });
    expect(await screen.findByText(/대시보드 목록을 불러오는 중/)).toBeTruthy();
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("서버가 일시적으로 응답하지 못합니다");
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "다시 불러오기" }));
    expect(await screen.findByRole("navigation", { name: "대시보드 목록" })).toBeTruthy();
  });

  it.each([
    ["SUPERSET_UNAVAILABLE", 503, "대시보드 서비스에 연결할 수 없습니다"],
    ["SUPERSET_REJECTED", 502, "관리자에게 문의"],
  ])("입장권 발급 %s는 쉬운 문구로 안내한다", async (code, status, text) => {
    open("/dashboards?d=1", { "GET /dashboards": () => page(DASHBOARDS), "POST /dashboards/1/guest-token": () => apiError(status, code, "내부 문구") });
    const failed = await screen.findByTestId("embed-failed");
    expect(failed.textContent).toContain(text);
    expect(failed.textContent).not.toContain("내부 문구");
  });

  it("입장권 429는 재시도 안내(Retry-After)를 보인다", async () => {
    open("/dashboards?d=1", {
      "GET /dashboards": () => page(DASHBOARDS),
      "POST /dashboards/1/guest-token": () =>
        json(429, { error: { code: "GUEST_TOKEN_RATE_LIMITED", message: "x", details: { retry_after: 20 }, request_id: "r" } }, { "Retry-After": "20" }),
    });
    const failed = await screen.findByTestId("embed-failed");
    expect(failed.textContent).toContain("요청이 너무 많습니다");
    expect(failed.textContent).toContain("20초");
  });

  it("'차트 만들기' 새 창 링크는 supersetRoot를 가리키고 noopener noreferrer를 가진다", async () => {
    open("/dashboards", { "GET /dashboards": () => page(DASHBOARDS) });
    const link = await screen.findByRole("link", { name: /차트 만들기/ });
    expect(link.getAttribute("href")).toBe(`${BASE}/superset/`);
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("작성자 안내문: 지원 차트 6가지, 시간 필터, 팀 열, 데이터셋 이름 형식", async () => {
    open("/dashboards", { "GET /dashboards": () => page(DASHBOARDS) });
    const guide = await screen.findByTestId("author-guide");
    const text = guide.textContent ?? "";
    expect(SUPPORTED_CHARTS).toHaveLength(6);
    for (const chart of ["선", "막대", "표", "큰 숫자", "원형", "혼합(막대+선)"]) expect(text).toContain(chart);
    expect(text).toContain("시간 필터");
    expect(text).toContain("team");
    expect(text).toContain("[팀] 이름");
    expect(text).not.toMatch(/guest|token|RLS|uuid/i);
  });

  it("작성자 안내문: 차트별 숫자 형식 지정 방법(y_axis_format, number_format, column_config, D3 형식, 자릿수 한계)", async () => {
    open("/dashboards", { "GET /dashboards": () => page(DASHBOARDS) });
    const text = (await screen.findByTestId("number-format-guide")).textContent ?? "";
    for (const word of ["y_axis_format", "number_format", "column_config", ",.2f", ",.6~f", "보조 축", "소수 6자리", "약 16자리"]) expect(text).toContain(word);
  });

  it("supersetRoot가 비어 있으면 임베드·링크 없이 안내만 보인다", async () => {
    window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: "" };
    open("/dashboards?d=1", { "GET /dashboards": () => page(DASHBOARDS) });
    expect((await screen.findByTestId("no-superset-root")).textContent).toContain("설정되지 않아");
    expect(screen.queryByRole("link", { name: /차트 만들기/ })).toBeNull();
    await screen.findByRole("navigation", { name: "대시보드 목록" });
    expect(embedDashboard).not.toHaveBeenCalled();
  });

  it("관리자가 아니어도 볼 수 있고(읽기 권한) 관리 메뉴는 보이지 않는다", async () => {
    open("/dashboards", { "GET /dashboards": () => page(DASHBOARDS) }, MEMBER_ME);
    await screen.findByRole("navigation", { name: "대시보드 목록" });
    expect(screen.queryByRole("navigation", { name: "관리 메뉴" })).toBeNull();
  });
});

const ADMIN_HANDLERS = (state: { items: typeof DASHBOARDS }, extra: Record<string, Handler> = {}): Record<string, Handler> => ({
  "GET /dashboards": () => page(state.items),
  ...extra,
});

describe("S8 대시보드 연결 관리 (E3 include_inactive, E4, E5)", () => {
  it("관리자가 아니면 막는다(목록도 부르지 않는다)", async () => {
    const { calls } = open("/admin/dashboards", { "GET /dashboards": () => page(DASHBOARDS) }, MEMBER_ME);
    const screenNode = await screen.findByTestId("screen-S8");
    expect(screenNode.textContent).toContain("관리자만 사용할 수 있는 화면입니다");
    expect(calls.some((c) => c.path === "/dashboards")).toBe(false);
  });

  it("목록은 include_inactive=true로 읽고 해제된 항목도 상태와 함께 보인다", async () => {
    const { calls } = open("/admin/dashboards", ADMIN_HANDLERS({ items: [...DASHBOARDS, INACTIVE] }), ADMIN_ME);
    const table = await screen.findByRole("table", { name: "대시보드 연결 목록" });
    expect(calls.find((c) => c.path === "/dashboards")!.query.get("include_inactive")).toBe("true");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell").slice(0, 3).map((c) => c.textContent))).toEqual([
      ["매출 현황", UUID_1, "연결됨"],
      ["비용 현황", UUID_2, "연결됨"],
      ["옛 대시보드", INACTIVE.embedded_uuid, "해제됨"],
    ]);
    expect(within(rows[2]).getByRole("button", { name: "다시 연결" })).toBeTruthy();
    expect(within(rows[0]).getByRole("button", { name: "연결 해제" })).toBeTruthy();
  });

  it("안내문: Superset에서 임베드를 켜고 받은 번호를 등록, 다른 DB 연결 추가 금지, 허용 도메인", async () => {
    open("/admin/dashboards", ADMIN_HANDLERS({ items: [] }), ADMIN_ME);
    const help = await screen.findByTestId("admin-help");
    expect(help.textContent).toContain("임베드를 켭니다");
    expect(help.textContent).toContain("번호");
    expect(help.textContent).toContain(window.location.origin);
    expect(screen.getByTestId("admin-warning").textContent).toBe("운영 주의: Superset에 다른 DB 연결을 추가하지 마세요.");
    expect(await screen.findByTestId("no-dashboards")).toBeTruthy();
  });

  it("이름 입력 maxLength는 서버 상한 100에 맞춘다(등록 폼과 이름 변경 모두)", async () => {
    open("/admin/dashboards", ADMIN_HANDLERS({ items: [{ id: 1, name: "a", embedded_uuid: UUID_1, is_active: true }] }), ADMIN_ME);
    expect((await screen.findByLabelText(/^이름/) as HTMLInputElement).maxLength).toBe(100);
    fireEvent.click(await screen.findByRole("button", { name: "이름 변경" }));
    expect((screen.getByLabelText("새 이름") as HTMLInputElement).maxLength).toBe(100);
  });

  describe("등록", () => {
    const fill = async (name: string, uuid: string) => {
      await screen.findByRole("form", { name: "대시보드 연결 등록" });
      fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: name } });
      fireEvent.change(screen.getByLabelText(/^임베드 번호/), { target: { value: uuid } });
    };
    const submitButton = () => screen.getByRole("button", { name: "연결 등록" }) as HTMLButtonElement;

    it("형식이 틀리면 즉시 안내하고 등록할 수 없다", async () => {
      open("/admin/dashboards", ADMIN_HANDLERS({ items: [] }), ADMIN_ME);
      await fill("새 대시보드", "not-a-uuid");
      expect(screen.getByTestId("uuid-format-error").textContent).toContain("하이픈이 있는 36자");
      expect(submitButton().disabled).toBe(true);
      for (const bad of ["aaaaaaaa1111 4111 8111 aaaaaaaaaaaa", UUID_1.replace(/-/g, ""), `{${UUID_1}}`, UUID_1.slice(1), `${UUID_1}0`, UUID_1.replace(/-/g, "_")]) {
        fireEvent.change(screen.getByLabelText(/^임베드 번호/), { target: { value: bad } });
        expect(submitButton().disabled).toBe(true);
      }
    });

    it("이름이 비었거나 100자를 넘으면 등록할 수 없다", async () => {
      open("/admin/dashboards", ADMIN_HANDLERS({ items: [] }), ADMIN_ME);
      await fill("   ", UUID_1);
      expect(submitButton().disabled).toBe(true);
      fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "가".repeat(101) } });
      expect(submitButton().disabled).toBe(true);
      expect(screen.getByText("이름은 100자 이하여야 합니다.")).toBeTruthy();
      fireEvent.change(screen.getByLabelText(/^이름/), { target: { value: "가".repeat(100) } });
      expect(submitButton().disabled).toBe(false);
    });

    it("붙여넣은 대문자 uuid는 앞뒤 공백을 지우고 소문자로 정규화해 보낸다", async () => {
      const state = { items: [] as typeof DASHBOARDS };
      const { calls } = open(
        "/admin/dashboards",
        ADMIN_HANDLERS(state, {
          "POST /dashboards": (call) => {
            const body = call.body as { name: string; embedded_uuid: string };
            const created = { id: 9, name: body.name, embedded_uuid: body.embedded_uuid, is_active: true };
            state.items = [created];
            return json(201, created);
          },
        }),
        ADMIN_ME,
      );
      await fill("  새 대시보드 ", `  ${UUID_1.toUpperCase()}\n`);
      expect(screen.getByTestId("uuid-normalized").textContent).toContain(UUID_1);
      expect(screen.queryByTestId("uuid-format-error")).toBeNull();
      fireEvent.click(submitButton());
      expect((await screen.findByTestId("register-done")).textContent).toContain("새 대시보드");
      const post = calls.find((c) => c.method === "POST" && c.path === "/dashboards")!;
      expect(post.body).toEqual({ name: "새 대시보드", embedded_uuid: UUID_1 });
      // 등록 뒤 목록을 다시 읽고 입력 칸을 비운다.
      await screen.findByRole("table", { name: "대시보드 연결 목록" });
      expect((screen.getByLabelText(/^임베드 번호/) as HTMLInputElement).value).toBe("");
    });

    it("이미 등록된 번호(409 ALREADY_EXISTS)는 쉬운 문구로 안내한다", async () => {
      open("/admin/dashboards", ADMIN_HANDLERS({ items: DASHBOARDS }, { "POST /dashboards": () => apiError(409, "ALREADY_EXISTS", "서버 문구", { field: "embedded_uuid" }) }), ADMIN_ME);
      await fill("중복", UUID_1);
      fireEvent.click(submitButton());
      const alert = await screen.findByText(/이미 연결된 임베드 번호입니다/);
      expect(alert.textContent).toContain("다시 연결");
      expect(alert.textContent).not.toContain("서버 문구");
    });

    it("서버가 형식 오류(422)를 돌려주면 필드 이름과 함께 안내한다", async () => {
      open(
        "/admin/dashboards",
        ADMIN_HANDLERS({ items: [] }, { "POST /dashboards": () => apiError(422, "VALIDATION_ERROR", "x", { fields: [{ field: "embedded_uuid", code: "BAD_FORMAT", message: "x" }] }) }),
        ADMIN_ME,
      );
      await fill("이름", UUID_1);
      fireEvent.click(submitButton());
      expect((await screen.findByRole("alert", {})).textContent).toContain("임베드 번호: 형식이 맞지 않습니다");
    });

    it("권한이 없으면(403) 권한 문구를 보인다", async () => {
      open("/admin/dashboards", ADMIN_HANDLERS({ items: [] }, { "POST /dashboards": () => apiError(403, "FORBIDDEN") }), ADMIN_ME);
      await fill("이름", UUID_1);
      fireEvent.click(submitButton());
      expect((await screen.findByText(/권한이 없습니다/)).textContent).toContain("이 작업을 할 권한이 없습니다");
    });
  });

  describe("해제·재사용·이름 변경 (E5)", () => {
    it("연결 해제는 is_active=false만, 다시 연결은 true만 보낸다", async () => {
      const state = { items: [...DASHBOARDS] as Array<(typeof DASHBOARDS)[number]> };
      const { calls } = open(
        "/admin/dashboards",
        ADMIN_HANDLERS(state, {
          "PATCH /dashboards/1": (call) => {
            const body = call.body as { is_active?: boolean };
            state.items = state.items.map((i) => (i.id === 1 ? { ...i, is_active: body.is_active ?? i.is_active } : i));
            return json(200, state.items[0]);
          },
        }),
        ADMIN_ME,
      );
      const table = await screen.findByRole("table", { name: "대시보드 연결 목록" });
      fireEvent.click(within(table).getAllByRole("button", { name: "연결 해제" })[0]);
      await screen.findByRole("button", { name: "다시 연결" });
      fireEvent.click(screen.getByRole("button", { name: "다시 연결" }));
      await waitFor(() => expect(screen.queryByRole("button", { name: "다시 연결" })).toBeNull());
      const patches = calls.filter((c) => c.method === "PATCH");
      expect(patches.map((c) => c.body)).toEqual([{ is_active: false }, { is_active: true }]);
    });

    it("이름 변경은 name만 보내고, 같은 이름이거나 비면 저장할 수 없다", async () => {
      const state = { items: [...DASHBOARDS] as Array<(typeof DASHBOARDS)[number]> };
      const { calls } = open(
        "/admin/dashboards",
        ADMIN_HANDLERS(state, {
          "PATCH /dashboards/2": (call) => {
            state.items = state.items.map((i) => (i.id === 2 ? { ...i, name: (call.body as { name: string }).name } : i));
            return json(200, state.items[1]);
          },
        }),
        ADMIN_ME,
      );
      const table = await screen.findByRole("table", { name: "대시보드 연결 목록" });
      fireEvent.click(within(table).getAllByRole("button", { name: "이름 변경" })[1]);
      const save = screen.getByRole("button", { name: "저장" }) as HTMLButtonElement;
      expect(save.disabled).toBe(true);
      fireEvent.change(screen.getByLabelText("새 이름"), { target: { value: " " } });
      expect(save.disabled).toBe(true);
      fireEvent.change(screen.getByLabelText("새 이름"), { target: { value: "  비용 요약 " } });
      fireEvent.click(save);
      await screen.findByText("비용 요약");
      expect(calls.filter((c) => c.method === "PATCH").map((c) => c.body)).toEqual([{ name: "비용 요약" }]);
    });

    it("없는 대시보드(404)는 쉬운 오류를 보인다", async () => {
      open("/admin/dashboards", ADMIN_HANDLERS({ items: DASHBOARDS }, { "PATCH /dashboards/1": () => apiError(404, "NOT_FOUND") }), ADMIN_ME);
      const table = await screen.findByRole("table", { name: "대시보드 연결 목록" });
      fireEvent.click(within(table).getAllByRole("button", { name: "연결 해제" })[0]);
      expect((await screen.findByRole("alert")).textContent).toContain("대상을 찾을 수 없습니다");
    });
  });

  it("목록 읽기 실패는 오류와 다시 불러오기, 로딩 표시", async () => {
    open("/admin/dashboards", { "GET /dashboards": () => apiError(500, "INTERNAL_ERROR") }, ADMIN_ME);
    expect(await screen.findByRole("button", { name: "다시 불러오기" })).toBeTruthy();
  });
});
