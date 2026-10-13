import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiError, installFetch, json } from "../../test-utils";
import { GuestTokenError, requestGuestToken, tokenProblemOf, tokenProblemText } from "./guestToken";

const BASE = "/bi-wizard";
const TOKEN = "header.PAYLOAD-SECRET.signature";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
});

afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

async function failure(promise: Promise<unknown>): Promise<GuestTokenError> {
  try {
    await promise;
  } catch (error) {
    expect(error).toBeInstanceOf(GuestTokenError);
    return error as GuestTokenError;
  }
  throw new Error("실패해야 합니다");
}

/** 오류를 가능한 모든 방식으로 문자열로 만든다(메시지, 스택, 직렬화, 속성 전부). */
function dump(error: Error): string {
  return [String(error), error.message, error.stack ?? "", JSON.stringify(error, Object.getOwnPropertyNames(error)), Object.keys(error).join(",")].join("\n");
}

describe("requestGuestToken (E6)", () => {
  it("본문 없이 POST하고 no-store로 요청하며 token 문자열만 돌려준다", async () => {
    const { calls, fetchMock } = installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: TOKEN, expires_in: 300 }) });
    await expect(requestGuestToken(5)).resolves.toBe(TOKEN);
    expect(calls).toHaveLength(1);
    expect(calls[0].body).toBeUndefined();
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe(`${BASE}/api/dashboards/5/guest-token`);
    expect(init.method).toBe("POST");
    expect(init.cache).toBe("no-store");
    expect(init.body).toBeUndefined();
  });

  it("token이 없거나 문자열이 아니면 BAD_RESPONSE(응답 내용은 담지 않음)", async () => {
    installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: 12345, other: "BODY-LEAK" }) });
    const error = await failure(requestGuestToken(5));
    expect(error.code).toBe("BAD_RESPONSE");
    expect(dump(error)).not.toContain("BODY-LEAK");
    installFetch({ "POST /dashboards/5/guest-token": () => json(200, { expires_in: 300 }) });
    expect((await failure(requestGuestToken(5))).code).toBe("BAD_RESPONSE");
    installFetch({ "POST /dashboards/5/guest-token": () => json(200, { token: "" }) });
    expect((await failure(requestGuestToken(5))).code).toBe("BAD_RESPONSE");
  });

  it("실패 오류에는 상태 코드·error.code·요청 번호만 있고 서버 본문·토큰 문자열은 없다", async () => {
    installFetch({
      "POST /dashboards/5/guest-token": () =>
        apiError(502, "SUPERSET_REJECTED", `서버가 보낸 문구 ${TOKEN}`, { leaked: TOKEN, body: "RESPONSE-BODY" }),
    });
    const error = await failure(requestGuestToken(5));
    expect(error.status).toBe(502);
    expect(error.code).toBe("SUPERSET_REJECTED");
    expect(error.requestId).toBe("req-test");
    const text = dump(error);
    expect(text).not.toContain(TOKEN);
    expect(text).not.toContain("PAYLOAD-SECRET");
    expect(text).not.toContain("RESPONSE-BODY");
    expect(text).not.toContain("서버가 보낸 문구");
  });

  it("429는 Retry-After 헤더(없으면 details.retry_after)를 초로 보관한다", async () => {
    installFetch({
      "POST /dashboards/5/guest-token": () =>
        json(429, { error: { code: "GUEST_TOKEN_RATE_LIMITED", message: "x", details: { retry_after: 12 }, request_id: "r1" } }, { "Retry-After": "30" }),
    });
    let error = await failure(requestGuestToken(5));
    expect(error.retryAfter).toBe(30);
    installFetch({
      "POST /dashboards/5/guest-token": () => json(429, { error: { code: "GUEST_TOKEN_RATE_LIMITED", message: "x", details: { retry_after: 12 }, request_id: "r1" } }),
    });
    error = await failure(requestGuestToken(5));
    expect(error.retryAfter).toBe(12);
  });

  it("연결 실패와 JSON이 아닌 오류 응답도 GuestTokenError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError(`failed ${TOKEN}`))));
    const network = await failure(requestGuestToken(5));
    expect(network.code).toBe("NETWORK_ERROR");
    expect(dump(network)).not.toContain(TOKEN);
    vi.stubGlobal("fetch", vi.fn(async () => new Response(`<html>${TOKEN}</html>`, { status: 502 })));
    const html = await failure(requestGuestToken(5));
    expect(html.status).toBe(502);
    expect(dump(html)).not.toContain(TOKEN);
  });
});

describe("tokenProblemOf / tokenProblemText", () => {
  const make = (status: number, code: string, retry: number | null = null) => new GuestTokenError(status, code, "req-1", retry);

  it("코드와 상태로 분류한다", () => {
    expect(tokenProblemOf(make(429, "GUEST_TOKEN_RATE_LIMITED", 20))).toEqual({ kind: "RATE", retryAfter: 20, requestId: "req-1" });
    expect(tokenProblemOf(make(503, "SUPERSET_UNAVAILABLE")).kind).toBe("UNAVAILABLE");
    expect(tokenProblemOf(make(502, "SUPERSET_REJECTED")).kind).toBe("REJECTED");
    expect(tokenProblemOf(make(401, "UNAUTHENTICATED")).kind).toBe("LOGGED_OUT");
    expect(tokenProblemOf(make(401, "HTTP_401")).kind).toBe("LOGGED_OUT");
    expect(tokenProblemOf(make(429, "HTTP_429")).kind).toBe("RATE");
    expect(tokenProblemOf(make(404, "NOT_FOUND")).kind).toBe("GONE");
    expect(tokenProblemOf(make(500, "INTERNAL_ERROR")).kind).toBe("OTHER");
    expect(tokenProblemOf(new Error("x")).kind).toBe("OTHER");
  });

  it("문구는 쉬운 한국어이며 429는 재시도 초를 안내한다", () => {
    expect(tokenProblemText({ kind: "RATE", retryAfter: 20, requestId: null })).toContain("20초");
    expect(tokenProblemText({ kind: "RATE", retryAfter: null, requestId: null })).toContain("잠시 뒤");
    expect(tokenProblemText({ kind: "UNAVAILABLE", retryAfter: null, requestId: null })).toContain("연결할 수 없습니다");
    expect(tokenProblemText({ kind: "REJECTED", retryAfter: null, requestId: null })).toContain("관리자에게 문의");
    expect(tokenProblemText({ kind: "LOGGED_OUT", retryAfter: null, requestId: null })).toContain("새로 고쳐");
    for (const kind of ["RATE", "UNAVAILABLE", "REJECTED", "LOGGED_OUT", "GONE", "OTHER"] as const) {
      expect(tokenProblemText({ kind, retryAfter: null, requestId: null })).not.toMatch(/superset|token|guest|JWT|HTTP/i);
    }
  });
});
