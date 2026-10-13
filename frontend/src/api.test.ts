import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest, parseErrorResponse } from "./api";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

const jsonResponse = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });

describe("parseErrorResponse", () => {
  it("05 §1 오류 형식을 읽는다", async () => {
    const error = await parseErrorResponse(
      jsonResponse(409, {
        error: {
          code: "DEFINITION_VERSION_MISMATCH",
          message: "다른 사람이 먼저 바꿨습니다.",
          details: { current_version: 7 },
          request_id: "req-1",
        },
      }),
    );
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.code).toBe("DEFINITION_VERSION_MISMATCH");
    expect(error.message).toBe("다른 사람이 먼저 바꿨습니다.");
    expect(error.details).toEqual({ current_version: 7 });
    expect(error.requestId).toBe("req-1");
  });

  it("검증 오류의 details.fields를 보존한다", async () => {
    const error = await parseErrorResponse(
      jsonResponse(422, {
        error: {
          code: "VALIDATION_ERROR",
          message: "입력을 확인해 주세요.",
          details: { fields: [{ field: "name", code: "TOO_LONG", message: "너무 깁니다." }] },
          request_id: null,
        },
      }),
    );
    expect(error.code).toBe("VALIDATION_ERROR");
    expect(error.details).toEqual({ fields: [{ field: "name", code: "TOO_LONG", message: "너무 깁니다." }] });
  });

  it("request_id가 본문에 없으면 X-Request-ID 헤더를 쓴다", async () => {
    const error = await parseErrorResponse(
      jsonResponse(
        403,
        { error: { code: "FORBIDDEN", message: "권한이 없습니다.", details: null, request_id: null } },
        { "X-Request-ID": "hdr-9" },
      ),
    );
    expect(error.requestId).toBe("hdr-9");
  });

  it("JSON이 아닌 413(nginx HTML)은 PAYLOAD_TOO_LARGE로 처리한다", async () => {
    const error = await parseErrorResponse(
      new Response("<html><body>413 Request Entity Too Large</body></html>", {
        status: 413,
        headers: { "Content-Type": "text/html" },
      }),
    );
    expect(error.status).toBe(413);
    expect(error.code).toBe("PAYLOAD_TOO_LARGE");
    expect(error.message).not.toContain("<html>");
  });

  it("JSON이 아닌 502는 INTERNAL_ERROR, 그 밖은 HTTP_상태", async () => {
    expect((await parseErrorResponse(new Response("bad gateway", { status: 502 }))).code).toBe("INTERNAL_ERROR");
    expect((await parseErrorResponse(new Response("nope", { status: 404 }))).code).toBe("HTTP_404");
  });

  it("형식이 다른 JSON도 안전하게 처리한다", async () => {
    const error = await parseErrorResponse(jsonResponse(500, { detail: "x" }));
    expect(error.code).toBe("INTERNAL_ERROR");
  });
});

describe("apiRequest", () => {
  it("apiUrl로 조립한 하위 경로 상대경로를 호출한다", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, { ok: 1 })));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest<{ ok: number }>("/me")).resolves.toEqual({ ok: 1 });
    expect(fetchMock.mock.calls[0]).toEqual(["/bi-wizard/api/me", expect.objectContaining({ method: "GET" })]);
  });

  it("본문은 JSON으로 보낸다", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(jsonResponse(200, {})));
    vi.stubGlobal("fetch", fetchMock);
    await apiRequest("/teams", { method: "POST", body: { name: "a" } });
    const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(init.body).toBe('{"name":"a"}');
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
  });

  it("실패 응답은 ApiError를 던진다", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          jsonResponse(401, { error: { code: "UNAUTHENTICATED", message: "로그인이 필요합니다.", details: null, request_id: "r" } }),
        ),
      ),
    );
    await expect(apiRequest("/me")).rejects.toMatchObject({ code: "UNAUTHENTICATED", status: 401 });
  });

  it("연결 실패는 NETWORK_ERROR", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("failed"))));
    await expect(apiRequest("/me")).rejects.toMatchObject({ code: "NETWORK_ERROR", status: 0 });
  });

  it("204는 undefined", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(null, { status: 204 }))));
    await expect(apiRequest("/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
