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
  DATASET_ARCHIVED: "보관된 데이터셋은 고칠 수 없습니다. 복구한 뒤 다시 시도하세요.",
  COLUMN_LOCKED: "열의 타입과 종류는 바꿀 수 없습니다. 다른 타입이 필요하면 새 열을 추가해 주세요.",
  FORMULA_CIRCULAR: "이 변경으로 계산 열이 서로를 참조하는 순환이 생깁니다. 구분 태그나 수식을 확인해 주세요.",
  FORMULA_INVALID: "수식에 고칠 곳이 있어 저장하지 않았습니다. 표시된 위치의 안내를 확인해 주세요.",
  FORMULA_RUNTIME_ERROR: "수식을 계산할 수 없습니다. 수식을 확인하고 미리보기로 결과를 살펴봐 주세요.",
  PAYLOAD_TOO_LARGE: "보내는 데이터가 너무 큽니다. 줄여서 다시 시도해 주세요.",
  GUEST_TOKEN_RATE_LIMITED: "요청이 너무 많습니다. 잠시 뒤 다시 시도해 주세요.",
  SUPERSET_REJECTED: "대시보드 서버가 요청을 거부했습니다. 관리자에게 문의해 주세요.",
  SUPERSET_UNAVAILABLE: "대시보드 서버에 연결할 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
  NETWORK_ERROR: "서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  INTERNAL_ERROR: "예기치 않은 오류가 발생했습니다. 문의할 때 아래 문의 번호를 알려 주세요.",
};

const ARCHIVED_NAME_MARK = "보관된 데이터셋과 같은 이름";

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
  embedded_uuid: "임베드 번호",
  from: "시작일",
  to: "종료일",
  actor_user_id: "행위자",
  target_type: "대상 종류",
  target_id: "대상 번호",
  action: "행위",
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
  embedded_uuid: "이미 연결된 임베드 번호입니다. 목록에서 해제된 항목이 있으면 '다시 연결'을 쓰세요.",
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

/** B2 데이터셋 생성 전용: 비활성 팀(TARGET_INACTIVE, field=team)은 소속 지정 문구가 아니라 생성 불가 문구를 쓴다. */
export const DATASET_TEAM_INACTIVE_TEXT = "비활성 팀에는 데이터셋을 만들 수 없습니다.";

/** 05 §1 잘림 표시: details.truncated가 true일 때만 전체 건수(없으면 0)를 돌려준다. 안 잘렸으면 null. */
export function truncationOf(error: unknown): { total: number } | null {
  if (!(error instanceof ApiError) || !isRecord(error.details) || error.details.truncated !== true) return null;
  const total = error.details.total;
  return { total: typeof total === "number" && Number.isFinite(total) ? total : 0 };
}

/** 서버가 목록을 자른 경우의 안내 문구. 잘리지 않았으면 빈 문자열. */
export function truncationText(error: unknown): string {
  const cut = truncationOf(error);
  if (!cut) return "";
  return cut.total > 0 ? `일부만 표시됨(전체 ${cut.total.toLocaleString("en-US")}건 중 일부)` : "일부만 표시됨";
}

/** ApiError를 사용자에게 보여 줄 한국어 문구로 바꾼다. */
export function describeApiError(error: unknown): string {
  if (!(error instanceof ApiError)) return "화면을 표시하는 중 오류가 발생했습니다.";
  if (error.code === "VALIDATION_ERROR") {
    const cut = truncationText(error);
    return cut ? `${validationText(error.details)} — ${cut}` : validationText(error.details);
  }
  if (error.code === "ALREADY_EXISTS") {
    const field = isRecord(error.details) && typeof error.details.field === "string" ? error.details.field : "";
    // FU-2b: 충돌 상대가 보관된 데이터셋이면 서버가 메시지에 "보관된 데이터셋과 같은 이름"을 덧붙인다(05 §2-2 B2). 그대로 보여 준다.
    if (field === "name" && error.message.includes(ARCHIVED_NAME_MARK)) return error.message;
    return EXISTS_BY_FIELD[field] ?? MESSAGES.ALREADY_EXISTS;
  }
  if (error.code === "TARGET_INACTIVE") {
    const field = isRecord(error.details) && typeof error.details.field === "string" ? error.details.field : "";
    return INACTIVE_BY_FIELD[field] ?? INACTIVE_GENERIC;
  }
  if (error.code === "FORMULA_CIRCULAR") {
    // 05 §3 details.path: 열 이름 경로 (예: ["A", "B", "A"] -> "A → B → A")
    const path = isRecord(error.details) && Array.isArray(error.details.path) ? error.details.path.filter((n): n is string => typeof n === "string") : [];
    return path.length > 0 ? `${MESSAGES.FORMULA_CIRCULAR} (순환 경로: ${path.join(" → ")})` : MESSAGES.FORMULA_CIRCULAR;
  }
  if (error.code === "DEFINITION_BUSY" || error.code === "WRITE_BUSY" || error.code === "PREVIEW_BUSY" || error.code === "GUEST_TOKEN_RATE_LIMITED") {
    const retry = isRecord(error.details) ? error.details.retry_after : undefined;
    return typeof retry === "number" && retry > 0 ? `${MESSAGES[error.code]} (약 ${Math.ceil(retry)}초 뒤)` : MESSAGES[error.code];
  }
  const known = MESSAGES[error.code];
  if (known) return known;
  // 5xx 등 알 수 없는 코드는 서버 문구를 믿지 않고 일반 문구를 쓴다. 4xx의 서버 문구는 05 §1에 따라 한국어 사용자 문구다.
  if (error.status >= 400 && error.status < 500 && error.message && !error.code.startsWith("HTTP_")) return error.message;
  return GENERIC;
}
