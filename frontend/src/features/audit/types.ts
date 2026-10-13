/** 05 §2-7 F1 응답 형태와 04 부록 A-3 목록. 계약에 없는 필드는 가정하지 않는다. */
export const AUDIT_ACTIONS = [
  "dataset.create",
  "dataset.update",
  "column.add",
  "column.update",
  "formula_column.add",
  "formula_column.update",
  "team.create",
  "team.update",
  "member.set",
  "member.remove",
  "user.create",
  "user.update",
  "user.bootstrap_admin",
  "dashboard.create",
  "dashboard.update",
] as const;

export type AuditAction = (typeof AUDIT_ACTIONS)[number];

/** 행위의 쉬운 한국어 이름(필터 선택과 표의 '행위' 칸). */
export const ACTION_LABELS: Record<AuditAction, string> = {
  "dataset.create": "데이터셋 만들기",
  "dataset.update": "데이터셋 설정 변경",
  "column.add": "열 추가",
  "column.update": "열 수정",
  "formula_column.add": "계산 열 추가",
  "formula_column.update": "계산 열 수식 수정",
  "team.create": "팀 만들기",
  "team.update": "팀 수정",
  "member.set": "소속 지정·변경",
  "member.remove": "소속 해제",
  "user.create": "사용자 등록",
  "user.update": "사용자 수정",
  "user.bootstrap_admin": "최초 관리자 등록",
  "dashboard.create": "대시보드 연결",
  "dashboard.update": "대시보드 수정",
};

export const TARGET_TYPES = ["team", "user", "dataset", "dashboard"] as const;
export type AuditTargetType = (typeof TARGET_TYPES)[number];

export const TARGET_TYPE_LABELS: Record<AuditTargetType, string> = {
  team: "팀",
  user: "사용자",
  dataset: "데이터셋",
  dashboard: "대시보드",
};

export function isAuditAction(value: unknown): value is AuditAction {
  return typeof value === "string" && (AUDIT_ACTIONS as readonly string[]).includes(value);
}

export function isTargetType(value: unknown): value is AuditTargetType {
  return typeof value === "string" && (TARGET_TYPES as readonly string[]).includes(value);
}

export interface AuditItem {
  id: number;
  /** ISO 8601 `+09:00` */
  occurred_at: string;
  /** 서버 명령(cli) 행은 null */
  actor: { id: number; display_name: string } | null;
  actor_source: string;
  action: string;
  target_type: string;
  target_id: number;
  /** 04 §5-1 허용 키만 있다. 화면은 요약 함수(summary.ts)를 거쳐서만 쓴다. */
  details: unknown;
}

export interface AuditPageData {
  items: AuditItem[];
  total: number;
  limit: number;
  offset: number;
}

/** 화면 필터 값(문자열 입력 그대로). 빈 문자열은 "지정 안 함". */
export interface AuditFilters {
  from: string;
  to: string;
  actor: string;
  targetType: string;
  targetId: string;
  action: string;
}

export const EMPTY_FILTERS: AuditFilters = { from: "", to: "", actor: "", targetType: "", targetId: "", action: "" };

export const PAGE_SIZE = 50;
