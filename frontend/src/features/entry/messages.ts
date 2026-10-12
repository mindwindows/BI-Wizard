import { ApiError } from "../../api";
import { describeApiError, fieldCodePhrase } from "../../errors";
import type { Column } from "../dataset/types";
import type { ConflictItem, FieldIssue } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** 409 details.conflicts[] (CELL_CONFLICT·PASTE_CONFLICT). 형식이 다른 항목은 건너뛴다. */
export function conflictsOf(error: unknown): ConflictItem[] {
  if (!(error instanceof ApiError) || !isRecord(error.details) || !Array.isArray(error.details.conflicts)) return [];
  const out: ConflictItem[] = [];
  for (const item of error.details.conflicts) {
    if (!isRecord(item)) continue;
    out.push({
      row_index: typeof item.row_index === "number" ? item.row_index : undefined,
      row_id: typeof item.row_id === "number" ? item.row_id : null,
      column_id: typeof item.column_id === "number" ? item.column_id : null,
      kind: item.kind === "cell" || item.kind === "period" || item.kind === "row_missing" ? item.kind : undefined,
      current: (item.current ?? null) as ConflictItem["current"],
    });
  }
  return out;
}

/** 422 details.fields[] */
export function fieldIssuesOf(error: unknown): FieldIssue[] {
  if (!(error instanceof ApiError) || !isRecord(error.details) || !Array.isArray(error.details.fields)) return [];
  return error.details.fields.filter(isRecord).map((item) => ({
    field: typeof item.field === "string" ? item.field : undefined,
    row_index: typeof item.row_index === "number" ? item.row_index : undefined,
    column_id: typeof item.column_id === "number" ? item.column_id : undefined,
    code: typeof item.code === "string" ? item.code : undefined,
    message: typeof item.message === "string" ? item.message : undefined,
  }));
}

/** 필드 코드를 칸 규칙과 함께 풀어 쓴다. 예: "허용 범위를 벗어났습니다(0 ~ 100)". */
export function describeFieldCode(code: string | undefined, column: Column | undefined): string {
  const base = fieldCodePhrase(code) ?? "값을 확인해 주세요";
  const rules = column?.rules;
  if (!rules) return base;
  if (code === "OUT_OF_RANGE" && (rules.min !== undefined || rules.max !== undefined)) {
    return `${base}(${rules.min ?? "제한 없음"} ~ ${rules.max ?? "제한 없음"})`;
  }
  if (code === "TOO_LONG" && typeof rules.max_length === "number") return `${base}(${rules.max_length}자 이하)`;
  if (code === "NOT_IN_OPTIONS" && Array.isArray(rules.options)) return `${base}(${rules.options.join(", ")} 중에서 고릅니다)`;
  return base;
}

export const PASTE_LIMIT_TEXT = "한 번에 5,000행, 요청 크기 1MiB까지 붙여넣을 수 있습니다. 나누어 붙여 주세요.";

/** 붙여넣기 요청의 오류 문구. 413은 nginx의 JSON 아닌 응답도 PAYLOAD_TOO_LARGE로 들어온다(api.ts). */
export function describePasteError(error: unknown): string {
  if (error instanceof ApiError && (error.code === "PAYLOAD_TOO_LARGE" || error.status === 413)) {
    return `붙여넣을 내용이 너무 큽니다. ${PASTE_LIMIT_TEXT}`;
  }
  return describeApiError(error);
}

export const isCode = (error: unknown, code: string): boolean => error instanceof ApiError && error.code === code;
