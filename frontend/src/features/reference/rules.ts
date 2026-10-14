import { REFERENCE_DESCRIPTION_MAX, REFERENCE_NAME_MAX, YEAR_MAX, YEAR_MIN } from "./types";

// 제어문자(0x00-0x1F, 0x7F)는 항목 이름에 쓸 수 없다(06 §2-2).
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/;

/** 화면 앞단의 가벼운 검사. 최종 판정은 서버(R2 422)이며 서버 오류도 같은 자리에 안내로 보여 준다. 문제가 없으면 null. */
export function validateItemName(name: string): string | null {
  const value = name.normalize("NFC").trim();
  if (value === "") return "이름을 입력해 주세요.";
  if ([...value].length > REFERENCE_NAME_MAX) return `이름은 ${REFERENCE_NAME_MAX}자 이하여야 합니다.`;
  if (/[[\]"]/.test(value) || CONTROL.test(value)) return '이름에는 [ ] " 와 제어문자를 쓸 수 없습니다.';
  return null;
}

export function validateDescription(text: string): string | null {
  return [...text.normalize("NFC").trim()].length > REFERENCE_DESCRIPTION_MAX ? `설명은 ${REFERENCE_DESCRIPTION_MAX}자 이하여야 합니다.` : null;
}

/** 연도: 정수 1900~9999. 빈 값은 입력 전이므로 null이 아니라 안내 문구를 돌려준다. */
export function validateYear(text: string): string | null {
  const value = text.trim();
  if (value === "") return "연도를 입력해 주세요.";
  if (!/^\d{1,4}$/.test(value)) return "연도는 숫자만 입력해 주세요(예: 2026).";
  const year = Number(value);
  if (year < YEAR_MIN || year > YEAR_MAX) return `연도는 ${YEAR_MIN}~${YEAR_MAX} 사이여야 합니다.`;
  return null;
}

const DECIMAL = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

/** 값: 쉼표 없는 십진수. 38자리 초과·숫자 아님은 막는다. 글자 기준값은 없다. */
export function validateValue(text: string): string | null {
  const value = text.trim();
  if (value === "") return "값을 입력해 주세요.";
  if (!DECIMAL.test(value)) return "숫자만 입력해 주세요(예: 12.5, 쉼표·글자 없이).";
  if (value.replace(/[^0-9]/g, "").length > 38) return "값은 숫자 38자리 이하여야 합니다.";
  return null;
}

/** 서버로 보낼 값 문자열(앞의 + 제거, 공백 제거). validateValue를 통과한 값만 넣는다. */
export const normalizeValue = (text: string): string => text.trim().replace(/^\+/, "");

/** 기본 연도 = 가장 큰 연도 + 1(값이 없으면 올해). 범위를 넘으면 빈 글자. */
export function defaultYear(yearMax: number | null | undefined, today: Date = new Date()): string {
  const next = yearMax === null || yearMax === undefined ? today.getFullYear() : yearMax + 1;
  return next >= YEAR_MIN && next <= YEAR_MAX ? String(next) : "";
}
