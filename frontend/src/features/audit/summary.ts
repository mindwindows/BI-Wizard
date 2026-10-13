import { ROLE_LABELS, type TeamRole } from "../access/types";
import { COLUMN_TYPE_LABELS, DATE_UNIT_LABELS, type ColumnType, type DateUnit } from "../dataset/types";
import { isAuditAction, type AuditAction } from "./types";

/** 요약을 만들 수 없을 때(알 수 없는 행위, 모양이 다른 details)의 안전한 문구. */
export const OMITTED = "(상세 생략)";
/** 허용 키 밖의 항목이 와서 그 부분만 버렸을 때 덧붙이는 문구. 값은 어디에도 출력하지 않는다. */
export const PARTIAL = "(일부 상세 생략)";

const MAX_TEXT = 40;

type Rec = Record<string, unknown>;
const isRecord = (v: unknown): v is Rec => typeof v === "object" && v !== null && !Array.isArray(v);

/** 이름·글자 값: 한 줄로 만들고 길면 자른다. 글자가 아니면 null. */
function text(v: unknown): string | null {
  if (typeof v !== "string") return null;
  const flat = v.replace(/\s+/g, " ").trim();
  const cut = flat.length > MAX_TEXT ? `${flat.slice(0, MAX_TEXT)}…` : flat;
  return `'${cut}'`;
}
const int = (v: unknown): number | null => (typeof v === "number" && Number.isInteger(v) ? v : null);
const bool = (v: unknown): boolean | null => (typeof v === "boolean" ? v : null);

const own = (obj: object, key: unknown): key is string => typeof key === "string" && Object.prototype.hasOwnProperty.call(obj, key);

const NOTHING = "없음";
/** 값 표기 함수. 모양이 맞지 않으면 null(이 변경은 값 없이 "변경"으로만 적는다). */
type Fmt = (v: unknown) => string | null;
const nameFmt: Fmt = (v) => (v === null ? NOTHING : text(v));
const requiredFmt: Fmt = (v) => (bool(v) === null ? null : v ? "필수" : "선택");
const activeFmt: Fmt = (v) => (bool(v) === null ? null : v ? "사용 중" : "사용 중지");
const dateUnitFmt: Fmt = (v) => (own(DATE_UNIT_LABELS, v) ? DATE_UNIT_LABELS[v as DateUnit] : null);
const columnRefFmt: Fmt = (v) => (v === null ? NOTHING : int(v) === null ? null : `열 번호 ${v as number}`);
const positionFmt: Fmt = (v) => (int(v) === null ? null : String(v));

interface FieldSpec {
  label: string;
  fmt: Fmt;
  /** 값 대신 문구 하나로 풀어 쓰는 경우(예: 연결 해제). 모양이 맞으면 문구, 아니면 null. */
  phrase?: (from: unknown, to: unknown) => string | null;
}

/** `changes`({필드: {from, to}})를 허용 필드만 풀어 쓴다. 허용 필드 밖은 이름도 값도 출력하지 않고 skipped로 알린다. */
function describeChanges(changes: unknown, fields: Record<string, FieldSpec>): { parts: string[]; skipped: boolean } {
  if (changes === undefined) return { parts: [], skipped: false };
  if (!isRecord(changes)) return { parts: [], skipped: true };
  const parts: string[] = [];
  let skipped = false;
  for (const [key, change] of Object.entries(changes)) {
    const spec = own(fields, key) ? fields[key] : undefined;
    if (!spec || !isRecord(change)) {
      skipped = true;
      continue;
    }
    const phrase = spec.phrase?.(change.from, change.to);
    if (phrase) {
      parts.push(phrase);
      continue;
    }
    const from = spec.fmt(change.from);
    const to = spec.fmt(change.to);
    parts.push(from !== null && to !== null ? `${spec.label} ${from}→${to}` : `${spec.label} 변경`);
  }
  return { parts, skipped };
}

type UserName = (id: number) => string | undefined;
interface Built {
  parts: Array<string | null>;
  skipped?: boolean;
}
interface ActionSpec {
  /** target_name 외에 허용되는 details 키(04 §5-1 표). 이 밖의 키는 값을 읽지 않는다. */
  keys: string[];
  build: (d: Rec, userName: UserName) => Built;
}

const version = (d: Rec): string | null => (int(d.def_version) === null ? null : `정의 버전 ${d.def_version as number}`);
const columnTitle = (d: Rec, prefix = "열"): string | null => {
  const name = text(d.column_name);
  return name === null ? null : `${prefix} ${name}`;
};
const typeLabel = (v: unknown): string | null =>
  own(COLUMN_TYPE_LABELS, v) ? COLUMN_TYPE_LABELS[v as ColumnType] : null;
const roleLabel = (v: unknown): string | null => (own(ROLE_LABELS, v) ? ROLE_LABELS[v as TeamRole] : null);
const who = (id: unknown, userName: UserName): string | null => {
  const n = int(id);
  if (n === null) return null;
  const name = userName(n);
  return name ? `사용자 ${text(name)}` : `사용자 번호 ${n}`;
};

const DATASET_FIELDS: Record<string, FieldSpec> = {
  name: { label: "이름", fmt: nameFmt },
  date_unit: { label: "날짜 단위", fmt: dateUnitFmt },
  base_date_column_id: { label: "기준 날짜 열", fmt: columnRefFmt },
};
const COLUMN_FIELDS: Record<string, FieldSpec> = {
  display_name: { label: "열 이름", fmt: nameFmt },
  required: { label: "필수 여부", fmt: requiredFmt },
  tag: { label: "구분 태그", fmt: nameFmt },
  position: { label: "위치", fmt: positionFmt },
};
const TEAM_FIELDS: Record<string, FieldSpec> = {
  name: { label: "이름", fmt: nameFmt },
  is_active: { label: "사용 상태", fmt: activeFmt },
};
const USER_FIELDS: Record<string, FieldSpec> = {
  is_admin: { label: "관리자 권한", fmt: (v) => (bool(v) === null ? null : v ? "있음" : "없음") },
  is_active: { label: "사용 상태", fmt: activeFmt },
};
const DASHBOARD_FIELDS: Record<string, FieldSpec> = {
  name: { label: "이름", fmt: nameFmt },
  is_active: {
    label: "사용 상태",
    fmt: activeFmt,
    phrase: (from, to) => (from === true && to === false ? "연결 해제" : from === false && to === true ? "다시 연결" : null),
  },
};

const SPECS: Record<AuditAction, ActionSpec> = {
  "dataset.create": {
    keys: ["team_id", "date_unit", "def_version"],
    build: (d) => ({
      parts: [int(d.team_id) === null ? null : `팀 번호 ${d.team_id as number}`, dateUnitFmt(d.date_unit) === null ? null : `날짜 단위 ${dateUnitFmt(d.date_unit)}`, version(d)],
    }),
  },
  "dataset.update": {
    keys: ["team_id", "changes", "def_version"],
    build: (d) => {
      const c = describeChanges(d.changes, DATASET_FIELDS);
      return { parts: [...c.parts, version(d)], skipped: c.skipped };
    },
  },
  "column.add": {
    keys: ["column_id", "column_name", "column_type", "required", "def_version"],
    build: (d) => {
      const traits = [typeLabel(d.column_type), bool(d.required) === null ? null : d.required ? "필수" : "선택"].filter((t): t is string => t !== null);
      const title = columnTitle(d, "열");
      return { parts: [title === null ? null : `${title} 추가${traits.length > 0 ? ` (${traits.join(", ")})` : ""}`, version(d)] };
    },
  },
  "column.update": {
    keys: ["column_id", "column_name", "changes", "rules_changed", "def_version"],
    build: (d) => {
      const c = describeChanges(d.changes, COLUMN_FIELDS);
      return { parts: [columnTitle(d), ...c.parts, d.rules_changed === true ? "검증 규칙 변경" : null, version(d)], skipped: c.skipped };
    },
  },
  "formula_column.add": {
    keys: ["column_id", "column_name", "result_type", "ast_hash", "def_version"],
    build: (d) => {
      const title = columnTitle(d, "계산 열");
      const type = typeLabel(d.result_type);
      return { parts: [title === null ? null : `${title} 추가${type ? ` (결과 ${type})` : ""}`, version(d)] };
    },
  },
  "formula_column.update": {
    keys: ["column_id", "column_name", "result_type", "result_type_changed", "ast_hash_from", "ast_hash", "def_version"],
    build: (d) => {
      const title = columnTitle(d, "계산 열");
      const type = typeLabel(d.result_type);
      const changed = d.result_type_changed === true ? `결과 타입이 바뀜${type ? ` (${type})` : ""}` : null;
      return { parts: [title === null ? null : `${title} 수식 수정`, changed, version(d)] };
    },
  },
  "team.create": { keys: ["code"], build: (d) => ({ parts: [typeof d.code === "string" ? `팀 코드 ${d.code.slice(0, 32)}` : null] }) },
  "team.update": {
    keys: ["changes"],
    build: (d) => {
      const c = describeChanges(d.changes, TEAM_FIELDS);
      return { parts: c.parts, skipped: c.skipped };
    },
  },
  "member.set": {
    keys: ["user_id", "role", "role_from"],
    build: (d, userName) => {
      const role = roleLabel(d.role);
      const from = d.role_from === null ? null : roleLabel(d.role_from);
      const roleText = role === null ? null : d.role_from === null ? `새 소속, 역할 ${role}` : from === null ? `역할 ${role}` : `역할 ${from}→${role}`;
      return { parts: [who(d.user_id, userName), roleText] };
    },
  },
  "member.remove": {
    keys: ["user_id", "role_from"],
    build: (d, userName) => {
      const user = who(d.user_id, userName);
      const from = roleLabel(d.role_from);
      return { parts: [user === null ? null : `${user} 소속 해제`, from === null ? null : `이전 역할 ${from}`] };
    },
  },
  "user.create": {
    keys: ["is_admin"],
    build: (d) => ({ parts: [bool(d.is_admin) === null ? null : `관리자 권한 ${d.is_admin ? "있음" : "없음"}으로 등록`] }),
  },
  "user.update": {
    keys: ["changes", "display_name_changed"],
    build: (d) => {
      const c = describeChanges(d.changes, USER_FIELDS);
      return { parts: [...c.parts, d.display_name_changed === true ? "표시 이름 변경" : null], skipped: c.skipped };
    },
  },
  "user.bootstrap_admin": { keys: ["is_admin"], build: () => ({ parts: ["서버 명령으로 최초 관리자 등록"] }) },
  "dashboard.create": {
    keys: ["embedded_uuid"],
    build: (d) => ({ parts: [typeof d.embedded_uuid === "string" ? `임베드 번호 ${d.embedded_uuid.slice(0, 40)}` : null] }),
  },
  "dashboard.update": {
    keys: ["changes"],
    build: (d) => {
      const c = describeChanges(d.changes, DASHBOARD_FIELDS);
      return { parts: c.parts, skipped: c.skipped };
    },
  },
};

/**
 * 감사 기록 한 행의 `details`를 쉬운 말로 풀어 쓴다(순수 함수).
 * - 04 §5-1의 행위별 허용 키만 읽는다. 허용 키 밖의 키·필드는 이름도 값도 출력하지 않고 "(일부 상세 생략)"만 덧붙인다.
 * - 알 수 없는 행위, details가 객체가 아니거나 읽을 수 있는 항목이 하나도 없으면 "(상세 생략)"이다.
 * - 수식 원문·행 값·토큰은 서버가 details에 넣지 않으며, 설령 허용 키 자리에 와도 모양(글자·정수·불리언)이 맞는
 *   항목만 짧게 자른 값으로 쓴다. 대상 이름(target_name)은 표의 '대상' 칸이 보여 주므로 요약에 넣지 않는다.
 * @param userName 사용자 번호 → 표시 이름(소속 행위 요약용, 없으면 "사용자 번호 N")
 */
export function summarize(action: unknown, details: unknown, userName: UserName = () => undefined): string {
  if (!isAuditAction(action) || !isRecord(details)) return OMITTED;
  const spec = SPECS[action];
  const allowed = new Set([...spec.keys, "target_name"]);
  const outside = Object.keys(details).some((key) => !allowed.has(key));
  const built = spec.build(details, userName);
  const parts = built.parts.filter((part): part is string => part !== null && part !== "");
  if (parts.length === 0) return OMITTED;
  const base = parts.join(", ");
  return outside || built.skipped ? `${base} ${PARTIAL}` : base;
}
