import type { Column, ColumnKind } from "../dataset/types";

/**
 * 05 §2-4(D1~D10) 요청·응답 형태. 계약에 없는 필드는 가정하지 않는다.
 * `signature`·`returns`의 구체 형태(문자열인지 구조인지)는 계약에 적혀 있지 않아 문자열로 읽고,
 * 문자열이 아니면 화면이 JSON 글자로 대신 보여 준다(api.ts의 asFunctionInfo).
 */
export interface FunctionInfo {
  name: string;
  signature: string;
  returns: string;
  help_ko: string;
  excel_diff: string;
}

/** D1 */
export interface FunctionCatalog {
  functions: FunctionInfo[];
  /** 셀 오류 코드(E1~E4)의 쉬운 말. 05 §3 */
  cell_errors: Record<string, string>;
}

/** D2·D3 FORMULA_INVALID details.errors[]. start·end는 수식 글자 위치(0부터, end는 포함하지 않음)로 읽는다. */
export interface FormulaErrorItem {
  code: string;
  message: string;
  start: number;
  end: number;
}

/** D2 */
export interface CheckResult {
  ok: boolean;
  result_type: string | null;
  refs: { column_id: number; display_name: string }[];
  errors: FormulaErrorItem[];
}

/** D3 rows[]: value가 null이고 error가 null이면 빈 값, error가 있으면 오류 칸. */
export interface PreviewRow {
  row_id: number;
  period: string | null;
  value: string | number | boolean | null;
  error: string | null;
}

export interface PreviewResult {
  result_type: string;
  rows: PreviewRow[];
  total_rows: number;
  error_count: number;
  empty_count: number;
  def_version: number;
}

/** D4·D5 */
export interface FormulaSaved {
  column: Column;
  def_version: number;
  /** D5만. 결과 형이 바뀌었는가 */
  result_type_changed?: boolean;
}

/** D6 */
export interface FormulaView {
  column_id: number;
  text: string;
  refs: { column_id: number; display_name: string; kind: ColumnKind }[];
  tag_columns: string[];
  error_count: number;
}

/** D7 */
export interface FormulaErrorSummary {
  dataset_id: number;
  dataset_name: string;
  team_name: string;
  column_id: number;
  column_name: string;
  error_count: number;
}

/** D8 */
export interface FormulaErrorCell {
  row_id: number;
  period: string | null;
  column_id: number;
  error: string;
  message: string;
}

/** D9 */
export interface ViewsStatus {
  views: number;
  views_failed_count: number;
  failed: { dataset_id: number; dataset_name: string; reason: string; since: string | null }[];
}

/** D10 */
export interface ViewsRetryResult {
  rebuilt: number;
  views_failed_count: number;
}

export interface ListPage<T> {
  items: T[];
  total: number;
}
