import type { Column } from "../dataset/types";
import type { CellValue } from "./types";

/** 05 §1: number는 십진 문자열. 부동소수점으로 바꾸지 않고 문자열 그대로 다룬다. */
const DECIMAL = /^-?\d+(\.\d+)?$/;
const DATE = /^(\d{4})-(\d{2})-(\d{2})$/;

export const BOOL_TRUE = "예";
export const BOOL_FALSE = "아니오";

export const isBlank = (value: CellValue | undefined): boolean => value === null || value === undefined;

/** 열 규칙에서 소수 자릿수(없으면 undefined). */
export function decimalsOf(column: Column): number | undefined {
  const value = column.rules?.decimals;
  return typeof value === "number" && Number.isInteger(value) && value >= 0 ? value : undefined;
}

/**
 * 숫자 십진 문자열의 표시 서식(ko-KR): 정수부 3자리 쉼표, 소수점 '.'.
 * 문자열만 쪼개고 붙이므로 큰 수도 정밀도를 잃지 않는다. 소수 자릿수 규칙(decimals)이 있으면 그 자릿수까지
 * 끝자리 0을 채워 보여 주고(깎지는 않음), 없으면 서버가 준 자릿수를 그대로 둔다.
 * 십진 형식이 아니면 받은 글자를 그대로 돌려준다(화면이 값을 추측해 고치지 않는다).
 */
export function formatNumber(raw: string, decimals?: number): string {
  if (!DECIMAL.test(raw)) return raw;
  const negative = raw.startsWith("-");
  const [int, frac = ""] = (negative ? raw.slice(1) : raw).split(".");
  const grouped = int.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const padded = decimals !== undefined && frac.length < decimals ? frac.padEnd(decimals, "0") : frac;
  return `${negative ? "-" : ""}${grouped}${padded ? `.${padded}` : ""}`;
}

function asBool(value: CellValue): boolean | null {
  if (value === true || value === "true") return true;
  if (value === false || value === "false") return false;
  return null;
}

/** 칸에 보이는 글자. 미입력(null)은 빈 글자이고 값 0은 "0"이라 구별된다. */
export function displayText(column: Column, value: CellValue | undefined, errorCode?: string): string {
  if (errorCode) return "오류";
  if (isBlank(value)) return "";
  switch (column.type) {
    case "number":
      return formatNumber(String(value), decimalsOf(column));
    case "boolean": {
      const flag = asBool(value as CellValue);
      return flag === null ? String(value) : flag ? BOOL_TRUE : BOOL_FALSE;
    }
    default:
      return String(value);
  }
}

/** 편집기에 처음 넣는 글자(서식 없는 원래 값). */
export function editorText(column: Column, value: CellValue | undefined): string {
  if (isBlank(value)) return "";
  if (column.type === "boolean") {
    const flag = asBool(value as CellValue);
    return flag === null ? "" : flag ? BOOL_TRUE : BOOL_FALSE;
  }
  return String(value);
}

export function validDate(text: string): boolean {
  const match = DATE.exec(text);
  if (!match) return false;
  const [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

export type ParsedInput = { ok: true; value: CellValue } | { ok: false; message: string };

/** 칸 편집 입력 -> 서버에 보낼 값. 빈 글자는 null(미입력). 형식이 분명히 틀리면 서버 호출 전에 쉬운 문구를 돌려준다. */
export function parseEditInput(column: Column, text: string): ParsedInput {
  if (text === "") return { ok: true, value: null };
  switch (column.type) {
    case "number": {
      const trimmed = text.trim();
      if (trimmed === "") return { ok: true, value: null };
      if (!DECIMAL.test(trimmed)) return { ok: false, message: "숫자만 입력해 주세요(예: 1234.5, -3). 쉼표나 단위 글자는 뺍니다." };
      return { ok: true, value: trimmed };
    }
    case "date": {
      const trimmed = text.trim();
      if (!validDate(trimmed)) return { ok: false, message: "날짜는 2026-01-31 형식으로 입력해 주세요." };
      return { ok: true, value: trimmed };
    }
    case "boolean":
      if (text === BOOL_TRUE) return { ok: true, value: true };
      if (text === BOOL_FALSE) return { ok: true, value: false };
      return { ok: false, message: `"${BOOL_TRUE}" 또는 "${BOOL_FALSE}"를 골라 주세요.` };
    default:
      return { ok: true, value: text };
  }
}

/** 붙여넣기 칸 -> 서버에 보낼 문자열|null. 해석은 서버가 하고, 화면은 모호한 값만 막는다(07 §9 규칙 ⑥). */
export function pasteCellValue(column: Column, text: string): { ok: true; value: string | null } | { ok: false; message: string } {
  if (text === "") return { ok: true, value: null };
  if (column.type === "number" && !DECIMAL.test(text)) {
    return { ok: false, message: `숫자로 읽을 수 없습니다("${clip(text)}"). 쉼표·단위·퍼센트를 뺀 값(예: 1234.5)으로 붙여 주세요.` };
  }
  if (column.type === "date" && !validDate(text)) {
    return { ok: false, message: `날짜로 읽을 수 없습니다("${clip(text)}"). 2026-01-31 형식으로 붙여 주세요.` };
  }
  return { ok: true, value: text };
}

function clip(text: string): string {
  const flat = text.replace(/[\r\n\t]/g, " ");
  return flat.length > 20 ? `${flat.slice(0, 20)}…` : flat;
}

/** 같은 값인가(미입력끼리 같음, 숫자는 십진 문자열 그대로 비교). */
export function sameValue(a: CellValue | undefined, b: CellValue | undefined): boolean {
  if (isBlank(a) || isBlank(b)) return isBlank(a) && isBlank(b);
  return String(a) === String(b);
}
