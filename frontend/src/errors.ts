import { ApiError } from "./api";

/** 05 §3 오류 코드별 쉬운 한국어 문구. 화면은 error.code로 분기하고, 모르는 코드만 서버 message를 쓴다. */
const MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: "로그인 정보를 확인하지 못했습니다. 다시 접속해 주세요.",
  USER_NOT_REGISTERED: "포털에 등록되지 않은 사용자입니다. 관리자에게 등록을 요청해 주세요.",
  USER_INACTIVE: "사용이 중지된 계정입니다. 관리자에게 문의해 주세요.",
  FORBIDDEN: "이 작업을 할 권한이 없습니다.",
  NOT_FOUND: "대상을 찾을 수 없습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.",
  VALIDATION_ERROR: "입력한 내용을 확인해 주세요.",
  ALREADY_EXISTS: "이미 같은 값이 있습니다.",
  LAST_ADMIN: "마지막 관리자는 관리자 권한을 해제하거나 사용 중지할 수 없습니다. 먼저 다른 관리자를 지정해 주세요.",
  DEFINITION_VERSION_MISMATCH: "다른 사람이 먼저 바꿨습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.",
  WRITE_BUSY: "다른 작업이 진행 중입니다. 잠시 뒤 다시 시도해 주세요.",
  DEFINITION_BUSY: "다른 작업이 진행 중입니다. 잠시 뒤 다시 시도해 주세요.",
  PAYLOAD_TOO_LARGE: "보내는 데이터가 너무 큽니다. 줄여서 다시 시도해 주세요.",
  SUPERSET_REJECTED: "대시보드 서버가 요청을 거부했습니다. 관리자에게 문의해 주세요.",
  SUPERSET_UNAVAILABLE: "대시보드 서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
  NETWORK_ERROR: "서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  INTERNAL_ERROR: "예기치 않은 오류가 발생했습니다. 문의할 때 아래 문의 번호를 알려 주세요.",
};

const GENERIC = "요청을 처리하지 못했습니다.";

const FIELD_LABELS: Record<string, string> = {
  code: "팀 코드",
  name: "이름",
  display_name: "표시 이름",
  login_id: "로그인 ID",
  role: "역할",
};

const FIELD_CODE_PHRASES: Record<string, string> = {
  REQUIRED: "꼭 입력해야 합니다",
  TOO_LONG: "너무 깁니다",
  BAD_FORMAT: "형식이 맞지 않습니다",
  RESERVED: "사용할 수 없는 이름입니다",
  OUT_OF_RANGE: "허용 범위를 벗어났습니다",
};

const EXISTS_BY_FIELD: Record<string, string> = {
  code: "같은 코드의 팀이 이미 있습니다.",
  name: "같은 이름이 이미 있습니다.",
  login_id: "같은 로그인 ID의 사용자가 이미 있습니다.",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function validationText(details: unknown): string {
  if (!isRecord(details) || !Array.isArray(details.fields)) return MESSAGES.VALIDATION_ERROR;
  const parts: string[] = [];
  for (const item of details.fields) {
    if (!isRecord(item)) continue;
    const field = typeof item.field === "string" ? item.field : "";
    const label = FIELD_LABELS[field] ?? field;
    const phrase = typeof item.code === "string" ? FIELD_CODE_PHRASES[item.code] : undefined;
    if (label && phrase) parts.push(`${label}: ${phrase}`);
    else if (label) parts.push(label);
  }
  return parts.length > 0 ? `${MESSAGES.VALIDATION_ERROR} (${parts.join(", ")})` : MESSAGES.VALIDATION_ERROR;
}

/** ApiError를 사용자에게 보여 줄 한국어 문구로 바꾼다. */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) return "화면을 표시하는 중 오류가 발생했습니다.";
  if (error.code === "VALIDATION_ERROR") return validationText(error.details);
  if (error.code === "ALREADY_EXISTS") {
    const field = isRecord(error.details) && typeof error.details.field === "string" ? error.details.field : "";
    return EXISTS_BY_FIELD[field] ?? MESSAGES.ALREADY_EXISTS;
  }
  const known = MESSAGES[error.code];
  if (known) return known;
  // 5xx 등 알 수 없는 코드는 서버 문구를 믿지 않고 일반 문구를 쓴다. 4xx의 서버 문구는 05 §1에 따라 한국어 사용자 문구다.
  if (error.status >= 400 && error.status < 500 && error.message && !error.code.startsWith("HTTP_")) return error.message;
  return GENERIC;
}
