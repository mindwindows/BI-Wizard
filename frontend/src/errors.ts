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
  METHOD_NOT_ALLOWED: "허용되지 않는 요청입니다. 화면을 새로 고친 뒤 다시 시도해 주세요.",
  // 503: 로그아웃(401)과 구분한다. 접근 안내가 아니라 일반 오류 + 다시 시도로 보여 준다.
  SERVICE_UNAVAILABLE: "서버가 일시적으로 응답하지 못합니다. 잠시 뒤 다시 시도하세요.",
  DEFINITION_VERSION_MISMATCH:
    "다른 사람이 먼저 바꿨습니다. 최신 내용을 다시 읽었습니다. 내용을 확인한 뒤 다시 시도해 주세요.",
  CELL_CONFLICT: "다른 사람이 먼저 이 칸을 바꿨습니다. 서버에 있는 값을 보여 드립니다.",
  PASTE_CONFLICT: "붙여넣는 동안 다른 사람이 바꾼 칸이 있어 아무것도 저장하지 않았습니다.",
  PERIOD_CONFLICT: "이미 같은 기간의 행이 있습니다. 기간을 바꾸거나 기존 행을 고쳐 주세요.",
  ROW_NOT_FOUND: "행을 찾을 수 없습니다. 다른 사람이 지웠을 수 있으니 화면을 새로 읽어 주세요.",
  PREVIEW_BUSY: "지금 계산 요청이 많습니다. 잠시 뒤 다시 시도해 주세요.",
  WRITE_BUSY: "다른 작업이 진행 중입니다. 잠시 뒤 다시 시도해 주세요.",
  DEFINITION_BUSY: "다른 작업이 진행 중입니다. 잠시 뒤 다시 시도해 주세요.",
  DATASET_HAS_ROWS: "이미 입력된 행이 있어 날짜 단위와 기준 날짜 열은 바꿀 수 없습니다. 행이 없는 데이터셋에서만 바꿀 수 있습니다.",
  COLUMN_LOCKED: "열의 타입과 종류는 바꿀 수 없습니다. 다른 타입이 필요하면 새 열을 추가해 주세요.",
  FORMULA_CIRCULAR: "이 변경으로 계산 열이 서로를 참조하는 순환이 생깁니다. 구분 태그나 수식을 확인해 주세요.",
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
  team_id: "팀",
  date_unit: "날짜 단위",
  base_date_column_id: "기준 날짜 열",
  type: "타입",
  required: "필수 여부",
  rules: "검증 규칙",
  tag: "구분 태그",
  position: "위치",
  expected_version: "정의 버전",
};

const FIELD_CODE_PHRASES: Record<string, string> = {
  REQUIRED: "꼭 입력해야 합니다",
  TOO_LONG: "너무 깁니다",
  BAD_FORMAT: "형식이 맞지 않습니다",
  RESERVED: "사용할 수 없는 이름입니다",
  OUT_OF_RANGE: "허용 범위를 벗어났습니다",
  NOT_IN_OPTIONS: "선택 목록에 없는 값입니다",
  NOT_PERIOD_START: "기간의 첫날이 아닙니다",
  READ_ONLY: "바꿀 수 없습니다",
};

const EXISTS_BY_FIELD: Record<string, string> = {
  code: "같은 코드의 팀이 이미 있습니다.",
  name: "같은 이름이 이미 있습니다.",
  login_id: "같은 로그인 ID의 사용자가 이미 있습니다.",
  display_name: "같은 이름의 열이 이미 있습니다.",
};

/** 입력 검증 필드 코드(VALIDATION_ERROR details.fields[].code)의 쉬운 말. 모르는 코드는 undefined. */
export const fieldCodePhrase = (code: string | undefined): string | undefined => (code ? FIELD_CODE_PHRASES[code] : undefined);

/** TARGET_INACTIVE(409, A8) details.field별 문구. 05 §3 확정값은 team / user 이며, 모르는 값은 통합 문구를 쓴다. */
const INACTIVE_BY_FIELD: Record<string, string> = {
  team: "비활성 팀에는 소속을 지정할 수 없습니다. 먼저 팀을 다시 사용 상태로 바꿔 주세요.",
  user: "비활성 사용자에게는 소속을 지정할 수 없습니다. 먼저 사용자를 다시 사용 상태로 바꿔 주세요.",
};
const INACTIVE_GENERIC = "비활성 팀이나 사용자에게는 소속을 지정할 수 없습니다. 먼저 다시 사용 상태로 바꿔 주세요.";

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
  if (error.code === "TARGET_INACTIVE") {
    const field = isRecord(error.details) && typeof error.details.field === "string" ? error.details.field : "";
    return INACTIVE_BY_FIELD[field] ?? INACTIVE_GENERIC;
  }
  if (error.code === "DEFINITION_BUSY" || error.code === "WRITE_BUSY") {
    const retry = isRecord(error.details) ? error.details.retry_after : undefined;
    return typeof retry === "number" && retry > 0 ? `${MESSAGES[error.code]} (약 ${Math.ceil(retry)}초 뒤)` : MESSAGES[error.code];
  }
  const known = MESSAGES[error.code];
  if (known) return known;
  // 5xx 등 알 수 없는 코드는 서버 문구를 믿지 않고 일반 문구를 쓴다. 4xx의 서버 문구는 05 §1에 따라 한국어 사용자 문구다.
  if (error.status >= 400 && error.status < 500 && error.message && !error.code.startsWith("HTTP_")) return error.message;
  return GENERIC;
}
