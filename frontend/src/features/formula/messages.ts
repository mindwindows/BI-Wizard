import { ApiError } from "../../api";
import type { Column } from "../dataset/types";
import { COLUMN_TYPE_LABELS } from "../dataset/types";
import { displayText } from "../entry/values";
import { asErrorItems } from "./api";
import type { FormulaErrorItem, PreviewRow } from "./types";

/** 07 §3 수식 도움말 문구(제안 문구 그대로). 함수별 설명과 엑셀 차이는 D1 응답(help_ko·excel_diff)에서 온다. */
export const FORMULA_RULES: { title: string; text: string }[] = [
  {
    title: "빈 칸",
    text: "비어 있는 칸은 0이 아닙니다. 계산에 쓴 칸 중 하나라도 비어 있으면 결과도 빈 값입니다. (엑셀은 빈 칸을 0으로 계산합니다.)",
  },
  {
    title: "계산할 수 없는 칸",
    text: "0으로 나누는 것처럼 계산할 수 없는 칸은 빈 값이 되고 점검 화면에 표시됩니다. 다른 값을 쓰려면 IFERROR를 쓰세요.",
  },
  { title: "글자 비교", text: "글자 비교는 대문자·소문자를 구별하지 않습니다." },
  { title: "자동 변환 없음", text: "숫자·글자·날짜는 서로 자동으로 바뀌지 않습니다. 종류가 다르면 오류 안내가 나옵니다." },
  { title: "쓰는 법", text: "열은 [열 이름]으로, 글자는 \"큰따옴표\"로 씁니다. 같은 태그의 숫자 열을 모두 더하려면 SUMTAG(\"태그\")를 씁니다." },
];

/** D1을 받지 못했을 때의 셀 오류 문구(05 §3). 받으면 서버 문구를 우선한다. */
export const DEFAULT_CELL_ERRORS: Record<string, string> = {
  E1: "0으로 나누어 계산할 수 없습니다.",
  E2: "글자 길이 범위를 벗어났습니다.",
  E3: "날짜 범위를 벗어났습니다.",
};

export function cellErrorText(code: string, catalog: Record<string, string> | undefined): string {
  return catalog?.[code] ?? DEFAULT_CELL_ERRORS[code] ?? "계산할 수 없는 값입니다.";
}

export function isCode(error: unknown, code: string): boolean {
  return error instanceof ApiError && error.code === code;
}

/** 422 FORMULA_INVALID의 details.errors[] (D2와 같은 모양) */
export function invalidErrorsOf(error: unknown): FormulaErrorItem[] {
  if (!(error instanceof ApiError) || !isCode(error, "FORMULA_INVALID")) return [];
  const details = error.details;
  if (typeof details !== "object" || details === null || Array.isArray(details)) return [];
  return asErrorItems((details as Record<string, unknown>).errors);
}

/** 429 PREVIEW_BUSY details.retry_after(초). 없으면 undefined */
export function retryAfterOf(error: unknown): number | undefined {
  if (!(error instanceof ApiError)) return undefined;
  const details = error.details;
  if (typeof details !== "object" || details === null || Array.isArray(details)) return undefined;
  const value = (details as Record<string, unknown>).retry_after;
  return typeof value === "number" && value > 0 ? value : undefined;
}

export const RESULT_TYPE_LABELS: Record<string, string> = COLUMN_TYPE_LABELS;

export const resultTypeLabel = (type: string | null | undefined): string => (type ? (RESULT_TYPE_LABELS[type] ?? type) : "알 수 없음");

export type PreviewCell = { kind: "value"; text: string } | { kind: "error"; text: string; code: string } | { kind: "empty"; text: string };

/** 미리보기 한 칸: 값 / 오류 / 빈 값을 구별한다(05 §1: 오류 칸은 value null + error 코드). */
export function previewCell(row: PreviewRow, resultType: string): PreviewCell {
  if (row.error) return { kind: "error", text: "오류", code: row.error };
  if (row.value === null || row.value === undefined) return { kind: "empty", text: "빈 값" };
  const column = { type: resultType in RESULT_TYPE_LABELS ? resultType : "text" } as Column;
  return { kind: "value", text: displayText(column, row.value) };
}
