import type { Column } from "../dataset/types";

/**
 * 05 §1 Row 형태와 §2-3(C1~C4) 요청·응답. 계약에 없는 필드는 가정하지 않는다.
 * 칸 값: number는 십진 문자열, 미입력은 null. (boolean은 JSON 불리언으로 가정한다. 05에 명시가 없어 보고서에 확인 항목으로 적었다.)
 */
export type CellValue = string | number | boolean | null;

export interface Row {
  row_id: number;
  cells: Record<string, CellValue>;
  /** 계산 열 칸의 오류 코드 {"<column_id>": "E1"}. 있으면 오류 칸, 없으면 값 또는 미입력. */
  errors?: Record<string, string>;
}

/** C1 응답 */
export interface RowsPage {
  def_version: number;
  items: Row[];
  total: number;
  limit: number;
  offset: number;
}

export type RowOrder = "asc" | "desc";

/** C2·C3 응답 */
export interface RowSaved {
  row: Row;
  def_version: number;
}

export interface CellChange {
  column_id: number;
  expected: CellValue;
  value: CellValue;
}

/** C4 요청의 한 줄. 새 행은 row_id=null이고 expected가 없다. */
export interface PasteRow {
  row_id: number | null;
  expected?: CellValue[];
  values: (string | null)[];
}

export interface PasteRequest {
  expected_version: number;
  column_ids: number[];
  rows: PasteRow[];
}

/** C4 성공 응답 */
export interface PasteResult {
  updated: number;
  created: number;
  created_rows: { index: number; row_id: number }[];
  def_version: number;
}

/** 05 §2-3: 409 details.conflicts[] (C3: row_id·column_id·current / C4: 거기에 row_index·kind) */
export interface ConflictItem {
  row_index?: number;
  row_id: number | null;
  column_id: number | null;
  kind?: "cell" | "period" | "row_missing";
  current: CellValue;
}

/** 05 §1 오류: details.fields[] */
export interface FieldIssue {
  field?: string;
  row_index?: number;
  column_id?: number;
  code?: string;
  message?: string;
}

export type { Column };
