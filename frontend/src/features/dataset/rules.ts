import { COLUMN_NAME_MAX, TAG_MAX, type ColumnRules, type ColumnType } from "./types";

/** 06 §3-3·04 부록 A: 열 표시 이름 예약어. */
export const RESERVED_COLUMN_NAMES = ["team", "팀", "row_id", "행 번호"] as const;

// 제어문자: C0, DEL, C1
function hasControl(text: string): boolean {
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0;
    if (code <= 0x1f || (code >= 0x7f && code <= 0x9f)) return true;
  }
  return false;
}

export const RESERVED_HINT = '예약어: "team", "팀", "row_id", "행 번호"는 포털이 쓰는 이름이라 열 이름으로 쓸 수 없습니다.';
export const FORBIDDEN_HINT = '열 이름에는 [ ] " 와 줄바꿈 같은 제어 문자를 쓸 수 없습니다.';

/** 열 이름 즉시 검사. 통과하면 null, 아니면 쉬운 한국어 문구. 서버 검사가 최종이다(VALIDATION_ERROR). */
export function validateColumnName(raw: string): string | null {
  const name = raw.normalize("NFC").trim();
  if (name === "") return "열 이름을 입력해 주세요.";
  if (/[[\]"]/.test(name) || hasControl(name)) return FORBIDDEN_HINT;
  // 서버는 대소문자를 무시하고 비교한다(Team, ROW_ID 도 예약어). toLowerCase는 casefold의 근사다.
  if ((RESERVED_COLUMN_NAMES as readonly string[]).includes(name.toLowerCase())) return RESERVED_HINT;
  if (name.length > COLUMN_NAME_MAX) return `열 이름은 ${COLUMN_NAME_MAX}자 이하로 입력해 주세요.`;
  return null;
}

/** 열 구분 태그(숫자 열): 50자, 큰따옴표·제어문자 금지(06 §3-3). 비어 있으면 태그 없음. */
export function validateTag(raw: string): string | null {
  const tag = raw.normalize("NFC").trim();
  if (tag === "") return null;
  if (tag.length > TAG_MAX) return `구분 태그는 ${TAG_MAX}자 이하로 입력해 주세요.`;
  if (tag.includes('"') || hasControl(tag)) return '구분 태그에는 " 와 줄바꿈 같은 제어 문자를 쓸 수 없습니다.';
  return null;
}

const DECIMAL = /^-?\d+(\.\d+)?$/;

interface Parsed {
  negative: boolean;
  int: string;
  frac: string;
}

function parseDecimal(text: string): Parsed {
  const negative = text.startsWith("-");
  const [int, frac = ""] = (negative ? text.slice(1) : text).split(".");
  return { negative, int, frac };
}

/** 십진 문자열 비교(부동소수점 없음, 05 §1). a<b이면 음수. */
export function compareDecimal(a: string, b: string): number {
  const x = parseDecimal(a);
  const y = parseDecimal(b);
  const scale = Math.max(x.frac.length, y.frac.length);
  const scaled = (p: Parsed) => {
    const value = BigInt(p.int + p.frac.padEnd(scale, "0"));
    return p.negative ? -value : value;
  };
  const left = scaled(x);
  const right = scaled(y);
  return left < right ? -1 : left > right ? 1 : 0;
}

/** 규칙 입력칸(모두 문자열). 타입마다 쓰는 칸만 의미가 있다. */
export interface RulesDraft {
  min: string;
  max: string;
  decimals: string;
  maxLength: string;
  dateMin: string;
  dateMax: string;
  options: string;
}

export const emptyDraft = (): RulesDraft => ({
  min: "",
  max: "",
  decimals: "",
  maxLength: "",
  dateMin: "",
  dateMax: "",
  options: "",
});

const text = (value: unknown): string => (typeof value === "string" || typeof value === "number" ? String(value) : "");

/** 서버의 rules를 입력칸으로. number의 min·max는 문자열이든 숫자든 문자열로 보여 준다. */
export function draftFromRules(type: ColumnType, rules: ColumnRules | null): RulesDraft {
  const draft = emptyDraft();
  if (!rules) return draft;
  switch (type) {
    case "number":
      draft.min = text(rules.min);
      draft.max = text(rules.max);
      draft.decimals = text(rules.decimals);
      break;
    case "text":
      draft.maxLength = text(rules.max_length);
      break;
    case "date":
      draft.dateMin = text(rules.min);
      draft.dateMax = text(rules.max);
      break;
    case "choice":
      draft.options = Array.isArray(rules.options) ? rules.options.map((o) => text(o)).join("\n") : "";
      break;
    case "boolean":
      break;
  }
  return draft;
}

export type RulesResult = { ok: true; rules: ColumnRules } | { ok: false; errors: Record<string, string> };

function validDate(value: string): boolean {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

/**
 * 입력칸을 요청의 rules로 바꾼다. 비운 항목은 키를 보내지 않는다.
 * number 값(min·max)은 05 §1의 십진 문자열로, decimals·max_length는 정수로 보낸다.
 */
export function rulesFromDraft(type: ColumnType, draft: RulesDraft): RulesResult {
  const errors: Record<string, string> = {};
  const rules: ColumnRules = {};
  if (type === "number") {
    const min = draft.min.trim();
    const max = draft.max.trim();
    const decimals = draft.decimals.trim();
    if (min !== "") {
      if (DECIMAL.test(min)) rules.min = min;
      else errors.min = "최솟값은 숫자로 입력해 주세요(예: 0, -5, 12.5).";
    }
    if (max !== "") {
      if (DECIMAL.test(max)) rules.max = max;
      else errors.max = "최댓값은 숫자로 입력해 주세요(예: 100, 99.5).";
    }
    if (rules.min !== undefined && rules.max !== undefined && compareDecimal(String(rules.min), String(rules.max)) > 0) {
      errors.max = "최댓값은 최솟값보다 작을 수 없습니다.";
    }
    if (decimals !== "") {
      if (/^\d+$/.test(decimals)) rules.decimals = Number(decimals);
      else errors.decimals = "소수 자릿수는 0 이상의 정수로 입력해 주세요.";
    }
  } else if (type === "text") {
    const maxLength = draft.maxLength.trim();
    if (maxLength !== "") {
      if (/^\d+$/.test(maxLength) && Number(maxLength) >= 1) rules.max_length = Number(maxLength);
      else errors.maxLength = "최대 글자 수는 1 이상의 정수로 입력해 주세요.";
    }
  } else if (type === "date") {
    const min = draft.dateMin.trim();
    const max = draft.dateMax.trim();
    if (min !== "") {
      if (validDate(min)) rules.min = min;
      else errors.dateMin = "날짜는 2026-01-31 형식으로 입력해 주세요.";
    }
    if (max !== "") {
      if (validDate(max)) rules.max = max;
      else errors.dateMax = "날짜는 2026-01-31 형식으로 입력해 주세요.";
    }
    if (typeof rules.min === "string" && typeof rules.max === "string" && rules.min > rules.max) {
      errors.dateMax = "가장 늦은 날짜는 가장 이른 날짜보다 앞설 수 없습니다.";
    }
  } else if (type === "choice") {
    const options = draft.options
      .split(/\r?\n/)
      .map((line) => line.normalize("NFC").trim())
      .filter((line) => line !== "");
    if (options.length === 0) errors.options = "선택 항목을 하나 이상 입력해 주세요(한 줄에 하나).";
    else if (new Set(options).size !== options.length) errors.options = "같은 항목이 두 번 들어 있습니다.";
    else rules.options = options;
  }
  return Object.keys(errors).length > 0 ? { ok: false, errors } : { ok: true, rules };
}
