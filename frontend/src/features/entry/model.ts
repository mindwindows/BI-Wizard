import type { Column } from "../dataset/types";
import type { CellValue, Row } from "./types";
import { isBlank } from "./values";

/** 칸 표시: 저장 중, 입력 오류, 다른 사람과 충돌 */
export type Mark =
  | { kind: "pending" }
  | { kind: "invalid"; message: string }
  | { kind: "conflict"; mine: string; current: CellValue; source: "edit" | "paste" };

export interface GridRow {
  /** 화면 안에서 쓰는 키: 저장된 행 "r<번호>", 임시 행 "d<번호>", 맨 아래 입력 줄 "entry" */
  key: string;
  rowId: number | null;
  draft: boolean;
  /** 맨 아래 새 행 입력 줄(항상 비어 있는 자리) */
  entry?: boolean;
  /** 서버 값 + 낙관적 표시 */
  cells: Record<string, CellValue>;
  errors: Record<string, string>;
  marks: Record<string, Mark>;
  /** 임시 행: 저장 요청 중 / 마지막 저장 실패 사유(행 단위) */
  saving?: boolean;
  issue?: string | null;
}

export const ENTRY_ROW: GridRow = { key: "entry", rowId: null, draft: true, entry: true, cells: {}, errors: {}, marks: {} };

export const fromServerRow = (row: Row): GridRow => ({
  key: `r${row.row_id}`,
  rowId: row.row_id,
  draft: false,
  cells: { ...row.cells },
  errors: { ...(row.errors ?? {}) },
  marks: {},
});

export const emptyDraft = (id: number): GridRow => ({ key: `d${id}`, rowId: null, draft: true, cells: {}, errors: {}, marks: {} });

export const cellOf = (row: GridRow, columnId: number): CellValue => row.cells[String(columnId)] ?? null;

/** 입력 열 중 필수인 열(기준 날짜 열은 DB NOT NULL이라 필수로 본다, 05 C2). */
export function requiredColumns(columns: Column[], baseDateColumnId: number | null): Column[] {
  return columns.filter((c) => c.kind === "raw" && (c.required || c.id === baseDateColumnId));
}

export function missingRequired(columns: Column[], baseDateColumnId: number | null, cells: Record<string, CellValue>): Column[] {
  return requiredColumns(columns, baseDateColumnId).filter((c) => isBlank(cells[String(c.id)]));
}

/** 필수 칸이 모두 찼고 값이 하나라도 있으면 저장할 수 있다. */
export function draftReady(columns: Column[], baseDateColumnId: number | null, cells: Record<string, CellValue>): boolean {
  if (!Object.values(cells).some((value) => !isBlank(value))) return false;
  return missingRequired(columns, baseDateColumnId, cells).length === 0;
}

/** C2 cells: 입력 열 중 값이 있는 칸만 보낸다(미입력은 생략). */
export function createCells(columns: Column[], cells: Record<string, CellValue>): Record<string, CellValue> {
  const out: Record<string, CellValue> = {};
  for (const column of columns) {
    if (column.kind !== "raw") continue;
    const value = cells[String(column.id)];
    if (!isBlank(value)) out[String(column.id)] = value as CellValue;
  }
  return out;
}

export function withMark(row: GridRow, columnId: number, mark: Mark | null): GridRow {
  const marks = { ...row.marks };
  if (mark) marks[String(columnId)] = mark;
  else delete marks[String(columnId)];
  return { ...row, marks };
}

export function withCell(row: GridRow, columnId: number, value: CellValue): GridRow {
  return { ...row, cells: { ...row.cells, [String(columnId)]: value } };
}
