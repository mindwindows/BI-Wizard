import { apiError, json, type Handler, type RecordedCall } from "../../test-utils";
import { COL, makeDetail } from "../dataset/test-server";
import type { Column, DatasetDetail } from "../dataset/types";
import type { Row } from "../entry/types";
import type { CheckResult, FormulaView, FunctionCatalog, PreviewResult } from "./types";

/**
 * 시험용 D1~D6 가짜 서버. 05 §2-4 계약대로 응답 모양을 흉내 내고 expected_version을 확인한다. 실제 백엔드를 부르지 않는다.
 * 수식 의미는 평가하지 않는다: 검사는 기본 통과, 미리보기는 고정 3행. 시험이 handlers를 덮어써서 다른 응답을 만든다.
 */
export const CATALOG: FunctionCatalog = {
  functions: [
    { name: "ROUND", signature: "ROUND(수, 자릿수)", returns: "숫자", help_ko: "수를 지정한 자릿수에서 반올림합니다.", excel_diff: "자릿수는 상수만 쓸 수 있습니다." },
    { name: "ROUNDUP", signature: "ROUNDUP(수, 자릿수)", returns: "숫자", help_ko: "0에서 먼 쪽으로 올립니다.", excel_diff: "" },
    { name: "SUM", signature: "SUM(수, ...)", returns: "숫자", help_ko: "더합니다.", excel_diff: "빈 칸이 있으면 결과도 빈 값입니다." },
    { name: "SUMTAG", signature: 'SUMTAG("태그")', returns: "숫자", help_ko: "같은 태그의 숫자 열을 모두 더합니다.", excel_diff: "엑셀에 없는 함수입니다." },
    { name: "REF", signature: 'REF("이름")', returns: "숫자", help_ko: "그 행의 기준 날짜가 속한 연도의 기준값을 가져옵니다.", excel_diff: "엑셀에 없는 함수입니다." },
    { name: "IF", signature: "IF(조건, 참, 거짓)", returns: "같은 종류", help_ko: "조건에 따라 값을 고릅니다.", excel_diff: "" },
  ],
  cell_errors: { E1: "서버 문구: 0으로 나눌 수 없습니다.", E2: "서버 문구: 글자 길이가 범위를 벗어났습니다.", E3: "서버 문구: 날짜가 범위를 벗어났습니다.", E4: "서버 문구: 기준값이 없습니다." },
};

export const SALES = [
  COL(1, "기준일", "date", { required: true }),
  COL(2, "매출", "number", { tag: "수입" }),
  COL(3, "비용", "number"),
  COL(4, "메모", "text"),
  COL(5, "이익", "number", { kind: "formula" }),
];

export const PREVIEW_OK: PreviewResult = {
  result_type: "number",
  rows: [
    { row_id: 3, period: "2026-03-01", value: "1234.5", error: null },
    { row_id: 2, period: "2026-02-01", value: null, error: "E1" },
    { row_id: 1, period: "2026-01-01", value: null, error: null },
  ],
  total_rows: 36,
  error_count: 1,
  empty_count: 1,
  def_version: 3,
};

export const CHECK_OK: CheckResult = { ok: true, result_type: "number", refs: [{ column_id: 2, display_name: "매출" }], errors: [] };

export interface FormulaFake {
  state: DatasetDetail;
  rows: Row[];
  views: Record<number, FormulaView>;
  handlers: Record<string, Handler>;
  calls: RecordedCall[];
}

export const salesDetail = (patch: Partial<DatasetDetail> = {}): DatasetDetail =>
  makeDetail({ columns: structuredClone(SALES), base_date_column_id: 1, ...patch });

export function makeFormulaFake(detail: DatasetDetail = salesDetail(), rows: Row[] = []): FormulaFake {
  const state: DatasetDetail = structuredClone(detail);
  const id = state.id;
  const fake: FormulaFake = { state, rows, views: {}, handlers: {}, calls: [] };
  for (const column of state.columns) {
    if (column.kind === "formula") {
      fake.views[column.id] = { column_id: column.id, text: "[매출] - [비용]", refs: [], tag_columns: [], error_count: 0 };
    }
  }
  const mismatch = (call: RecordedCall) => {
    const body = call.body as { expected_version?: number };
    return body.expected_version === state.def_version
      ? null
      : apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: state.def_version });
  };
  const h = fake.handlers;
  h[`GET /datasets/${id}`] = () => json(200, state);
  h[`GET /datasets/${id}/rows`] = (call) => {
    const limit = Number(call.query.get("limit") ?? 50);
    const offset = Number(call.query.get("offset") ?? 0);
    return json(200, { def_version: state.def_version, items: fake.rows.slice(offset, offset + limit), total: fake.rows.length, limit, offset });
  };
  h["GET /formulas/functions"] = () => json(200, CATALOG);
  h[`POST /datasets/${id}/formulas/check`] = () => json(200, CHECK_OK);
  h[`POST /datasets/${id}/formulas/preview`] = () => json(200, PREVIEW_OK);
  h[`POST /datasets/${id}/formulas`] = (call) => {
    const forced = mismatch(call);
    if (forced) return forced;
    const body = call.body as { display_name: string; expression: string; tag?: string; position?: number };
    const column: Column = {
      id: Math.max(0, ...state.columns.map((c) => c.id)) + 1,
      display_name: body.display_name,
      type: "number",
      kind: "formula",
      required: false,
      rules: null,
      tag: body.tag ?? null,
      position: body.position ?? state.columns.length + 1,
    };
    state.columns.push(column);
    state.def_version += 1;
    fake.views[column.id] = { column_id: column.id, text: body.expression, refs: [], tag_columns: [], error_count: 0 };
    return json(201, { column, def_version: state.def_version });
  };
  const put: Handler = (call) => {
    const forced = mismatch(call);
    if (forced) return forced;
    const columnId = Number(call.path.split("/").at(-1));
    const column = state.columns.find((c) => c.id === columnId);
    if (!column) return apiError(404, "NOT_FOUND");
    fake.views[columnId] = { ...fake.views[columnId], text: (call.body as { expression: string }).expression };
    state.def_version += 1;
    return json(200, { column, def_version: state.def_version, result_type_changed: false });
  };
  const view: Handler = (call) => {
    const columnId = Number(call.path.split("/").at(-1));
    return fake.views[columnId] ? json(200, fake.views[columnId]) : apiError(404, "NOT_FOUND");
  };
  for (let n = 1; n <= 30; n += 1) {
    h[`PUT /datasets/${id}/formulas/${n}`] = put;
    h[`GET /datasets/${id}/formulas/${n}`] = view;
  }
  return fake;
}
