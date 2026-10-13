import { vi } from "vitest";

export interface RecordedCall {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
}

export type Handler = (call: RecordedCall) => Response | Promise<Response>;

export const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

export const noContent = () => new Response(null, { status: 204 });

export const apiError = (status: number, code: string, message = "서버 문구", details: unknown = null) =>
  json(status, { error: { code, message, details, request_id: "req-test" } });

/**
 * fetch 모의. 핸들러 키는 "METHOD /api 뒤 경로"(쿼리 제외)다. 등록되지 않은 호출은 404 JSON을 돌려주고
 * calls에는 남는다. basePath는 앞에서 떼고 비교한다.
 */
export function installFetch(handlers: Record<string, Handler>, basePath = "/bi-wizard") {
  const calls: RecordedCall[] = [];
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const prefix = `${basePath}/api`;
    if (!url.startsWith(prefix)) throw new Error(`예상하지 못한 주소: ${url}`);
    const rest = url.slice(prefix.length);
    const [path, queryText = ""] = rest.split("?");
    const method = init?.method ?? "GET";
    const call: RecordedCall = {
      method,
      path,
      query: new URLSearchParams(queryText),
      body: typeof init?.body === "string" ? JSON.parse(init.body) : undefined,
    };
    calls.push(call);
    const handler = handlers[`${method} ${path}`];
    if (!handler) return apiError(404, "NOT_FOUND", "없음");
    return handler(call);
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

export const ADMIN_ME = {
  id: 1,
  display_name: "관리자 김",
  is_active: true,
  is_admin: true,
  memberships: [
    { team_id: 10, team_code: "sales", team_name: "영업", team_is_active: true, role: "definer" },
    { team_id: 20, team_code: "ops", team_name: "운영", team_is_active: true, role: "entry" },
  ],
};

export const MEMBER_ME = {
  id: 2,
  display_name: "입력자 박",
  is_active: true,
  is_admin: false,
  memberships: [{ team_id: 20, team_code: "ops", team_name: "운영", team_is_active: true, role: "entry" }],
};

export const HEALTH_HANDLERS: Record<string, Handler> = {
  "GET /health": () => json(200, { status: "ok" }),
  "GET /health/db": () => json(200, { status: "ok" }),
};
