import { apiUrl } from "./config";

/** 05 §1 오류 형식: {"error": {code, message, details, request_id}} */
export interface ApiErrorBody {
  code: string;
  message: string;
  details: unknown;
  request_id: string | null;
}

/** 서버 문구가 없을 때(JSON이 아닌 응답, 연결 실패) 쓰는 한국어 기본 문구. */
const FALLBACK_MESSAGES = {
  PAYLOAD_TOO_LARGE: "보내는 데이터가 너무 큽니다. 줄여서 다시 시도해 주세요.",
  NETWORK_ERROR: "서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  INTERNAL_ERROR: "예기치 않은 오류가 발생했습니다.",
  UNKNOWN: "요청을 처리하지 못했습니다.",
} as const;

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * 오류 응답을 ApiError로 바꾼다.
 * - 05 §1 형식의 JSON이면 서버가 준 code/message/details/request_id를 쓴다.
 * - JSON이 아니거나 형식이 다르면(예: nginx의 HTML 413) 상태 코드로 code를 정한다.
 *   413 -> PAYLOAD_TOO_LARGE, 5xx -> INTERNAL_ERROR, 그 밖 -> HTTP_<상태>.
 */
export async function parseErrorResponse(response: Response): Promise<ApiError> {
  const headerRequestId = response.headers.get("X-Request-ID");
  let parsed: unknown;
  try {
    parsed = await response.json();
  } catch {
    parsed = undefined;
  }
  const body = isRecord(parsed) ? parsed.error : undefined;
  if (isRecord(body) && typeof body.code === "string" && typeof body.message === "string") {
    return new ApiError(response.status, {
      code: body.code,
      message: body.message,
      details: body.details ?? null,
      request_id: typeof body.request_id === "string" ? body.request_id : headerRequestId,
    });
  }
  let code: string;
  let message: string;
  if (response.status === 413) {
    code = "PAYLOAD_TOO_LARGE";
    message = FALLBACK_MESSAGES.PAYLOAD_TOO_LARGE;
  } else if (response.status >= 500) {
    code = "INTERNAL_ERROR";
    message = FALLBACK_MESSAGES.INTERNAL_ERROR;
  } else {
    code = `HTTP_${response.status}`;
    message = FALLBACK_MESSAGES.UNKNOWN;
  }
  return new ApiError(response.status, { code, message, details: null, request_id: headerRequestId });
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  /** JSON으로 직렬화해 보낼 본문 */
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * FastAPI 호출 공용 함수. 경로는 `/api` 뒤만 쓴다(예: "/me"). 주소는 apiUrl()이 조립한다.
 * 성공 시 JSON을 돌려주고(204는 undefined), 실패 시 ApiError를 던진다.
 */
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const init: RequestInit = { method: options.method ?? "GET", headers, signal: options.signal };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(options.body);
  }
  let response: Response;
  try {
    response = await fetch(apiUrl(path), init);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(0, {
      code: "NETWORK_ERROR",
      message: FALLBACK_MESSAGES.NETWORK_ERROR,
      details: null,
      request_id: null,
    });
  }
  if (!response.ok) throw await parseErrorResponse(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export interface HealthResult {
  ok: boolean;
  detail: string;
}

async function check(path: string): Promise<HealthResult> {
  try {
    const response = await fetch(apiUrl(path), { headers: { Accept: "application/json" } });
    return { ok: response.ok, detail: `HTTP ${response.status}` };
  } catch {
    return { ok: false, detail: "연결 실패" };
  }
}

export const checkApi = (): Promise<HealthResult> => check("/health");
export const checkDatabase = (): Promise<HealthResult> => check("/health/db");
