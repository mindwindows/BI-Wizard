import { apiError, json, type Handler, type RecordedCall } from "../../test-utils";
import { COL, makeDetail } from "../dataset/test-server";
import type { Column, DatasetDetail } from "../dataset/types";
import type { CellValue, Row } from "./types";

/**
 * 시험용 C1~C4 가짜 서버. 05 계약(§2-3)대로 동작한다: expected_version 비교, 칸 단위 expected 가드,
 * 새 행의 기간 유일성, 붙여넣기 전부 취소. 실제 백엔드를 부르지 않는다.
 */
export const SALES_COLUMNS: Column[] = [
  COL(1, "기준일", "date", { required: true }),
  COL(2, "매출", "number", { rules: { min: "0", decimals: 2 } }),
  COL(3, "메모", "text", { rules: { max_length: 20 } }),
  COL(4, "등급", "choice", { rules: { options: ["상", "중", "하"] } }),
  COL(5, "합계", "number", { kind: "formula" }),
];

export const row = (row_id: number, cells: Record<string, CellValue>, errors?: Record<string, string>): Row => ({ row_id, cells, errors });

export const SALES_ROWS: Row[] = [
  row(1, { "1": "2026-03-01", "2": "1234.50", "3": null, "4": "상" }),
  row(2, { "1": "2026-02-01", "2": "0", "3": "2월 메모", "4": null }, { "5": "E1" }),
  row(3, { "1": "2026-01-01", "2": null, "3": null, "4": "하" }),
];

export const salesDetail = (patch: Partial<DatasetDetail> = {}): DatasetDetail =>
  makeDetail({ columns: SALES_COLUMNS, base_date_column_id: 1, ...patch });

export interface FakeRows {
  rows: Row[];
  detail: DatasetDetail;
  handlers: Record<string, Handler>;
  calls: RecordedCall[];
}

const same = (a: CellValue | undefined, b: CellValue | undefined) => (a ?? null) === (b ?? null);

export function makeFakeRows(detail: DatasetDetail, initial: Row[], opts: { total?: number } = {}): FakeRows {
  const state: FakeRows = { rows: structuredClone(initial), detail, handlers: {}, calls: [] };
  const id = detail.id;
  const baseId = detail.base_date_column_id;
  const version = () => state.detail.def_version;
  const mismatch = (body: { expected_version?: number }) =>
    body.expected_version === version() ? null : apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: version() });
  const nextId = () => Math.max(0, ...state.rows.map((r) => r.row_id)) + 1;
  const periodTaken = (value: CellValue | undefined, except?: number) =>
    baseId !== null && state.rows.some((r) => r.row_id !== except && r.cells[String(baseId)] === value);

  state.handlers[`GET /datasets/${id}`] = () => json(200, state.detail);
  state.handlers[`GET /datasets/${id}/rows`] = (call) => {
    state.calls.push(call);
    const limit = Number(call.query.get("limit") ?? 50);
    const offset = Number(call.query.get("offset") ?? 0);
    const sorted = [...state.rows].sort((a, b) => (call.query.get("order") === "asc" ? a.row_id - b.row_id : b.row_id - a.row_id));
    return json(200, { def_version: version(), items: sorted.slice(offset, offset + limit), total: opts.total ?? state.rows.length, limit, offset });
  };
  state.handlers[`POST /datasets/${id}/rows`] = (call) => {
    state.calls.push(call);
    const body = call.body as { expected_version: number; cells: Record<string, CellValue> };
    const forced = mismatch(body);
    if (forced) return forced;
    const missing = state.detail.columns.filter((c) => (c.required || c.id === baseId) && (body.cells[String(c.id)] ?? null) === null);
    if (missing.length > 0) {
      return apiError(422, "VALIDATION_ERROR", "서버 문구", { fields: missing.map((c) => ({ column_id: c.id, code: "REQUIRED", message: "필수" })) });
    }
    if (baseId !== null && periodTaken(body.cells[String(baseId)])) return apiError(409, "PERIOD_CONFLICT", "서버 문구", { conflicts: [] });
    const created = row(nextId(), { ...body.cells });
    state.rows.push(created);
    return json(201, { row: created, def_version: version() });
  };
  const patch: Handler = (call) => {
    state.calls.push(call);
    const rowId = Number(call.path.split("/").at(-1));
    const body = call.body as { expected_version: number; changes: { column_id: number; expected: CellValue; value: CellValue }[] };
    const forced = mismatch(body);
    if (forced) return forced;
    const target = state.rows.find((r) => r.row_id === rowId);
    if (!target) return apiError(404, "ROW_NOT_FOUND");
    const conflicts = body.changes
      .filter((c) => !same(target.cells[String(c.column_id)], c.expected))
      .map((c) => ({ row_id: rowId, column_id: c.column_id, current: target.cells[String(c.column_id)] ?? null }));
    if (conflicts.length > 0) return apiError(409, "CELL_CONFLICT", "서버 문구", { conflicts });
    for (const change of body.changes) {
      if (change.column_id === baseId && periodTaken(change.value, rowId)) return apiError(409, "PERIOD_CONFLICT", "서버 문구", { conflicts: [] });
      target.cells[String(change.column_id)] = change.value;
    }
    return json(200, { row: target, def_version: version() });
  };
  for (let n = 1; n <= 60; n += 1) state.handlers[`PATCH /datasets/${id}/rows/${n}`] = patch;
  state.handlers[`POST /datasets/${id}/rows/paste`] = (call) => {
    state.calls.push(call);
    const body = call.body as { expected_version: number; column_ids: number[]; rows: { row_id: number | null; expected?: CellValue[]; values: (string | null)[] }[] };
    const forced = mismatch(body);
    if (forced) return forced;
    const conflicts: unknown[] = [];
    body.rows.forEach((r, index) => {
      if (r.row_id === null) return;
      const target = state.rows.find((x) => x.row_id === r.row_id);
      if (!target) {
        conflicts.push({ row_index: index, row_id: r.row_id, column_id: null, kind: "row_missing", current: null });
        return;
      }
      body.column_ids.forEach((columnId, i) => {
        if (!same(target.cells[String(columnId)], r.expected?.[i])) {
          conflicts.push({ row_index: index, row_id: r.row_id, column_id: columnId, kind: "cell", current: target.cells[String(columnId)] ?? null });
        }
      });
    });
    if (conflicts.length > 0) return apiError(409, "PASTE_CONFLICT", "서버 문구", { conflicts });
    let updated = 0;
    const createdRows: { index: number; row_id: number }[] = [];
    body.rows.forEach((r, index) => {
      const cells: Record<string, CellValue> = {};
      body.column_ids.forEach((columnId, i) => {
        cells[String(columnId)] = r.values[i];
      });
      if (r.row_id === null) {
        const created = row(nextId(), cells);
        state.rows.push(created);
        createdRows.push({ index, row_id: created.row_id });
      } else {
        const target = state.rows.find((x) => x.row_id === r.row_id) as Row;
        Object.assign(target.cells, cells);
        updated += 1;
      }
    });
    return json(200, { updated, created: createdRows.length, created_rows: createdRows, def_version: version() });
  };
  return state;
}
