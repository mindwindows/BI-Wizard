import { ApiError, apiRequest } from "../../api";
import type {
  CheckResult,
  FormulaErrorCell,
  FormulaErrorItem,
  FormulaErrorSummary,
  FormulaSaved,
  FormulaView,
  FunctionCatalog,
  FunctionInfo,
  ListPage,
  PreviewResult,
  PreviewRow,
  ViewsRetryResult,
  ViewsStatus,
} from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, { code: "INTERNAL_ERROR", message: "서버 응답 형식이 올바르지 않습니다.", details: null, request_id: null });
}

const text = (value: unknown): string => (typeof value === "string" ? value : value === undefined || value === null ? "" : JSON.stringify(value));

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

/** 목록 응답: 05 §1 `{items, total, …}`이면 그대로, 배열이면 배열 길이를 전체 건수로 쓴다(D7·D8이 "목록"으로만 적혀 있어 둘 다 받는다). */
function asList<T>(data: unknown): ListPage<T> {
  if (Array.isArray(data)) return { items: data as T[], total: data.length };
  if (isRecord(data) && Array.isArray(data.items)) {
    return { items: data.items as T[], total: typeof data.total === "number" ? data.total : data.items.length };
  }
  throw badShape();
}

function asFunctionInfo(value: unknown): FunctionInfo | null {
  if (!isRecord(value) || typeof value.name !== "string") return null;
  return {
    name: value.name,
    signature: text(value.signature),
    returns: text(value.returns),
    help_ko: text(value.help_ko),
    excel_diff: text(value.excel_diff),
  };
}

/** D1 */
export async function getFunctions(signal?: AbortSignal): Promise<FunctionCatalog> {
  const data = await apiRequest<unknown>("/formulas/functions", { signal });
  if (!isRecord(data) || !Array.isArray(data.functions)) throw badShape();
  const cellErrors: Record<string, string> = {};
  if (isRecord(data.cell_errors)) {
    for (const [code, phrase] of Object.entries(data.cell_errors)) if (typeof phrase === "string") cellErrors[code] = phrase;
  }
  return { functions: data.functions.map(asFunctionInfo).filter((f): f is FunctionInfo => f !== null), cell_errors: cellErrors };
}

export function asErrorItems(value: unknown): FormulaErrorItem[] {
  if (!Array.isArray(value)) return [];
  const out: FormulaErrorItem[] = [];
  for (const item of value) {
    if (!isRecord(item) || typeof item.message !== "string") continue;
    out.push({
      code: typeof item.code === "string" ? item.code : "",
      message: item.message,
      start: typeof item.start === "number" ? item.start : 0,
      end: typeof item.end === "number" ? item.end : typeof item.start === "number" ? item.start : 0,
    });
  }
  return out;
}

/** D2 */
export async function checkFormula(datasetId: number, body: { expression: string; column_id?: number }, signal?: AbortSignal): Promise<CheckResult> {
  const data = await apiRequest<unknown>(`/datasets/${datasetId}/formulas/check`, { method: "POST", body, signal });
  if (!isRecord(data) || typeof data.ok !== "boolean") throw badShape();
  return {
    ok: data.ok,
    result_type: typeof data.result_type === "string" ? data.result_type : null,
    refs: Array.isArray(data.refs) ? (data.refs.filter(isRecord) as unknown as CheckResult["refs"]) : [],
    errors: asErrorItems(data.errors),
  };
}

/** D3. 저장 없음. */
export async function previewFormula(datasetId: number, body: { expression: string; column_id?: number }, signal?: AbortSignal): Promise<PreviewResult> {
  const data = await apiRequest<unknown>(`/datasets/${datasetId}/formulas/preview`, { method: "POST", body, signal });
  if (!isRecord(data) || !Array.isArray(data.rows) || typeof data.total_rows !== "number") throw badShape();
  return {
    result_type: text(data.result_type),
    rows: data.rows.filter(isRecord) as unknown as PreviewRow[],
    total_rows: data.total_rows,
    error_count: typeof data.error_count === "number" ? data.error_count : 0,
    empty_count: typeof data.empty_count === "number" ? data.empty_count : 0,
    def_version: typeof data.def_version === "number" ? data.def_version : 0,
  };
}

function asSaved(data: unknown): FormulaSaved {
  if (!isRecord(data) || !isRecord(data.column) || typeof data.column.id !== "number" || typeof data.def_version !== "number") throw badShape();
  return data as unknown as FormulaSaved;
}

/** D4 계산 열 만들기 */
export async function createFormula(
  datasetId: number,
  body: { expected_version: number; display_name: string; expression: string; tag?: string; position?: number },
): Promise<FormulaSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/formulas`, { method: "POST", body }));
}

/** D5 수식 바꾸기 */
export async function updateFormula(datasetId: number, columnId: number, body: { expected_version: number; expression: string }): Promise<FormulaSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/formulas/${columnId}`, { method: "PUT", body }));
}

/** D6 수식 보기 */
export async function getFormulaView(datasetId: number, columnId: number, signal?: AbortSignal): Promise<FormulaView> {
  const data = await apiRequest<unknown>(`/datasets/${datasetId}/formulas/${columnId}`, { signal });
  if (!isRecord(data) || typeof data.text !== "string") throw badShape();
  return {
    column_id: typeof data.column_id === "number" ? data.column_id : columnId,
    text: data.text,
    refs: Array.isArray(data.refs) ? (data.refs.filter(isRecord) as unknown as FormulaView["refs"]) : [],
    tag_columns: Array.isArray(data.tag_columns) ? data.tag_columns.filter((n): n is string => typeof n === "string") : [],
    error_count: typeof data.error_count === "number" ? data.error_count : 0,
  };
}

/** D7 */
export async function listFormulaErrorSummaries(params: { limit: number; offset: number }, signal?: AbortSignal): Promise<ListPage<FormulaErrorSummary>> {
  return asList<FormulaErrorSummary>(await apiRequest<unknown>(`/checks/formula-errors${query(params)}`, { signal }));
}

/** D8 */
export async function listFormulaErrorCells(
  datasetId: number,
  params: { column_id?: number; limit: number; offset: number },
  signal?: AbortSignal,
): Promise<ListPage<FormulaErrorCell>> {
  return asList<FormulaErrorCell>(await apiRequest<unknown>(`/datasets/${datasetId}/formula-errors${query(params)}`, { signal }));
}

/** D9 관리자 */
export async function getViewsStatus(signal?: AbortSignal): Promise<ViewsStatus> {
  const data = await apiRequest<unknown>("/checks/views", { signal });
  if (!isRecord(data) || !Array.isArray(data.failed)) throw badShape();
  return {
    views: typeof data.views === "number" ? data.views : 0,
    views_failed_count: typeof data.views_failed_count === "number" ? data.views_failed_count : data.failed.length,
    failed: data.failed.filter(isRecord) as unknown as ViewsStatus["failed"],
  };
}

/** D10 관리자. dataset_ids를 생략하면 실패 전부. */
export async function retryViews(body: { dataset_ids?: number[] }): Promise<ViewsRetryResult> {
  const data = await apiRequest<unknown>("/checks/views/retry", { method: "POST", body });
  if (!isRecord(data) || typeof data.rebuilt !== "number") throw badShape();
  return { rebuilt: data.rebuilt, views_failed_count: typeof data.views_failed_count === "number" ? data.views_failed_count : 0 };
}
