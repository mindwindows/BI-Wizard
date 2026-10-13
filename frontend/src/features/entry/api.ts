import { ApiError, apiRequest } from "../../api";
import type { CellChange, CellValue, PasteRequest, PasteResult, Row, RowOrder, RowSaved, RowsPage } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, { code: "INTERNAL_ERROR", message: "서버 응답 형식이 올바르지 않습니다.", details: null, request_id: null });
}

function asRow(data: unknown): Row {
  if (!isRecord(data) || typeof data.row_id !== "number" || !isRecord(data.cells)) throw badShape();
  return {
    row_id: data.row_id,
    cells: data.cells as Row["cells"],
    errors: isRecord(data.errors) ? (data.errors as Record<string, string>) : undefined,
  };
}

/** C1 */
export async function listRows(
  datasetId: number,
  params: { order: RowOrder; limit: number; offset: number },
  signal?: AbortSignal,
): Promise<RowsPage> {
  const search = new URLSearchParams({ order: params.order, limit: String(params.limit), offset: String(params.offset) });
  const data = await apiRequest<unknown>(`/datasets/${datasetId}/rows?${search.toString()}`, { signal });
  if (
    !isRecord(data) ||
    typeof data.def_version !== "number" ||
    !Array.isArray(data.items) ||
    typeof data.total !== "number"
  ) {
    throw badShape();
  }
  return {
    def_version: data.def_version,
    items: data.items.map(asRow),
    total: data.total,
    limit: typeof data.limit === "number" ? data.limit : params.limit,
    offset: typeof data.offset === "number" ? data.offset : params.offset,
  };
}

function asSaved(data: unknown): RowSaved {
  if (!isRecord(data) || typeof data.def_version !== "number") throw badShape();
  return { row: asRow(data.row), def_version: data.def_version };
}

/** C2: 임시 행의 필수 칸이 모두 찼을 때 한 번 부른다. */
export async function createRow(
  datasetId: number,
  body: { expected_version: number; cells: Record<string, CellValue> },
): Promise<RowSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/rows`, { method: "POST", body }));
}

/** C3: 칸 단위 수정. 칸마다 expected(화면의 이전 값, 빈 칸은 null)가 필수다. */
export async function patchRow(
  datasetId: number,
  rowId: number,
  body: { expected_version: number; changes: CellChange[] },
): Promise<RowSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/rows/${rowId}`, { method: "PATCH", body }));
}

/** C4 */
export async function pasteRows(datasetId: number, body: PasteRequest): Promise<PasteResult> {
  const data = await apiRequest<unknown>(`/datasets/${datasetId}/rows/paste`, { method: "POST", body });
  if (
    !isRecord(data) ||
    typeof data.updated !== "number" ||
    typeof data.created !== "number" ||
    typeof data.def_version !== "number"
  ) {
    throw badShape();
  }
  return {
    updated: data.updated,
    created: data.created,
    created_rows: Array.isArray(data.created_rows) ? (data.created_rows as PasteResult["created_rows"]) : [],
    def_version: data.def_version,
  };
}
