import { parseErrorResponse } from "../../api";
import { apiUrl } from "../../config";
import type { TokenProblem, TokenProblemKind } from "./types";

/**
 * E6 입장권 요청이 실패했을 때 던지는 오류. 상태 코드·error.code·요청 번호·재시도 초만 가진다.
 * 서버 응답 본문과 입장권(token)은 어디에도 담지 않으며, message는 고정 문구다.
 */
export class GuestTokenError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly retryAfter: number | null;

  constructor(status: number, code: string, requestId: string | null, retryAfter: number | null) {
    super("대시보드 접속 허가를 받지 못했습니다.");
    this.name = "GuestTokenError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.retryAfter = retryAfter;
  }
}

function positiveNumber(value: unknown): number | null {
  const number = typeof value === "string" && value.trim() !== "" ? Number(value) : value;
  return typeof number === "number" && Number.isFinite(number) && number > 0 ? Math.ceil(number) : null;
}

/**
 * E6 POST /dashboards/{id}/guest-token (본문 없음). 성공하면 token 문자열만 돌려준다.
 * 응답 객체는 이 함수 안에서만 쓰고 보관하지 않는다. 입장권은 호출한 쪽(SDK 콜백)의 지역 변수로만 흐른다.
 */
export async function requestGuestToken(dashboardId: number): Promise<string> {
  let response: Response;
  try {
    response = await fetch(apiUrl(`/dashboards/${dashboardId}/guest-token`), {
      method: "POST",
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
  } catch {
    throw new GuestTokenError(0, "NETWORK_ERROR", null, null);
  }
  if (!response.ok) {
    const parsed = await parseErrorResponse(response);
    const headerRetry = positiveNumber(response.headers.get("Retry-After"));
    const details = parsed.details;
    const bodyRetry =
      typeof details === "object" && details !== null && !Array.isArray(details)
        ? positiveNumber((details as Record<string, unknown>).retry_after)
        : null;
    throw new GuestTokenError(response.status, parsed.code, parsed.requestId, headerRetry ?? bodyRetry);
  }
  let token: unknown;
  try {
    const body: unknown = await response.json();
    token = typeof body === "object" && body !== null ? (body as Record<string, unknown>).token : undefined;
  } catch {
    token = undefined;
  }
  if (typeof token !== "string" || token === "") throw new GuestTokenError(response.status, "BAD_RESPONSE", response.headers.get("X-Request-ID"), null);
  return token;
}

const KIND_BY_CODE: Record<string, TokenProblemKind> = {
  GUEST_TOKEN_RATE_LIMITED: "RATE",
  SUPERSET_UNAVAILABLE: "UNAVAILABLE",
  SUPERSET_REJECTED: "REJECTED",
  UNAUTHENTICATED: "LOGGED_OUT",
  NOT_FOUND: "GONE",
};

/** 던져진 값을 화면 상태용 분류로 바꾼다. GuestTokenError가 아니면 OTHER. */
export function tokenProblemOf(error: unknown): TokenProblem {
  if (!(error instanceof GuestTokenError)) return { kind: "OTHER", retryAfter: null, requestId: null };
  const byStatus: TokenProblemKind | undefined = error.status === 401 ? "LOGGED_OUT" : error.status === 429 ? "RATE" : undefined;
  return { kind: KIND_BY_CODE[error.code] ?? byStatus ?? "OTHER", retryAfter: error.retryAfter, requestId: error.requestId };
}

/** 사용자에게 보이는 쉬운 한국어 문구. */
export function tokenProblemText(problem: TokenProblem): string {
  switch (problem.kind) {
    case "RATE":
      return problem.retryAfter
        ? `요청이 너무 많습니다. 약 ${problem.retryAfter}초 뒤에 다시 시도해 주세요.`
        : "요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요.";
    case "UNAVAILABLE":
      return "대시보드 서비스에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.";
    case "REJECTED":
      return "대시보드 서비스가 요청을 받아들이지 않았습니다. 관리자에게 문의해 주세요.";
    case "LOGGED_OUT":
      return "로그인 정보가 만료되었습니다. 화면을 새로 고쳐 다시 접속해 주세요.";
    case "GONE":
      return "이 대시보드는 연결이 해제되었거나 없습니다. 목록을 새로 고쳐 주세요.";
    default:
      return "대시보드 접속 허가를 받지 못했습니다. 잠시 뒤 다시 시도해 주세요.";
  }
}
