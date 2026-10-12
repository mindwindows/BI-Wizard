import { apiError, json, type Handler, type RecordedCall } from "../../test-utils";
import type { Column, DatasetDetail } from "./types";

/** 시험용 B3~B6 가짜 서버: 계약대로 expected_version을 확인하고 성공하면 버전을 올린다. 실제 백엔드를 부르지 않는다. */
export interface FakeWorkspace {
  state: DatasetDetail;
  handlers: Record<string, Handler>;
  /** 다음 쓰기 요청 하나를 이 응답으로 대신한다(오류 시험용). */
  failNext: (response: () => Response) => void;
}

export const COL = (id: number, display_name: string, type: Column["type"], extra: Partial<Column> = {}): Column => ({
  id,
  display_name,
  type,
  kind: "raw",
  required: false,
  rules: null,
  tag: null,
  position: id,
  ...extra,
});

export function makeDetail(patch: Partial<DatasetDetail> = {}): DatasetDetail {
  return {
    id: 7,
    team_id: 10,
    name: "월별 매출",
    date_unit: "month",
    base_date_column_id: null,
    status: "active",
    def_version: 3,
    created_by: { id: 1, display_name: "관리자 김" },
    created_at: "2026-10-12T09:30:00+09:00",
    team: { id: 10, code: "sales", name: "영업" },
    columns: [],
    permissions: { define: true, enter: true },
    ...patch,
  };
}

export function makeFakeWorkspace(initial: DatasetDetail): FakeWorkspace {
  const state: DatasetDetail = structuredClone(initial);
  let failure: (() => Response) | null = null;
  const id = state.id;
  const take = () => {
    const response = failure;
    failure = null;
    return response ? response() : null;
  };
  const mismatch = (call: RecordedCall) => {
    const body = call.body as { expected_version?: number };
    return body.expected_version === state.def_version
      ? null
      : apiError(409, "DEFINITION_VERSION_MISMATCH", "서버 문구", { current_version: state.def_version });
  };
  const handlers: Record<string, Handler> = {
    [`GET /datasets/${id}`]: () => json(200, state),
    [`POST /datasets/${id}/columns`]: (call) => {
      const forced = take() ?? mismatch(call);
      if (forced) return forced;
      const body = call.body as Record<string, unknown>;
      const column: Column = {
        id: Math.max(0, ...state.columns.map((c) => c.id)) + 1,
        display_name: body.display_name as string,
        type: body.type as Column["type"],
        kind: "raw",
        required: Boolean(body.required),
        rules: (body.rules as Column["rules"]) ?? null,
        tag: (body.tag as string | undefined) ?? null,
        position: (body.position as number | undefined) ?? state.columns.length + 1,
      };
      state.columns.push(column);
      state.def_version += 1;
      return json(201, { column, def_version: state.def_version });
    },
    [`PATCH /datasets/${id}`]: (call) => {
      const forced = take() ?? mismatch(call);
      if (forced) return forced;
      const { expected_version: _ignored, ...changes } = call.body as Record<string, unknown>;
      void _ignored;
      Object.assign(state, changes);
      state.def_version += 1;
      return json(200, state);
    },
  };
  // 열 수정은 열마다 경로가 달라 호출 시점에 찾는다.
  const patchColumn: Handler = (call) => {
    const forced = take() ?? mismatch(call);
    if (forced) return forced;
    const columnId = Number(call.path.split("/").at(-1));
    const column = state.columns.find((c) => c.id === columnId);
    if (!column) return apiError(404, "NOT_FOUND");
    const { expected_version: _ignored, ...changes } = call.body as Record<string, unknown>;
    void _ignored;
    Object.assign(column, changes);
    state.def_version += 1;
    return json(200, { column, def_version: state.def_version });
  };
  for (const column of state.columns) handlers[`PATCH /datasets/${id}/columns/${column.id}`] = patchColumn;
  // 새로 추가된 열의 PATCH도 받도록 흔한 id 범위를 미리 등록한다.
  for (let n = 1; n <= 30; n += 1) handlers[`PATCH /datasets/${id}/columns/${n}`] = patchColumn;
  return { state, handlers, failNext: (response) => (failure = response) };
}
