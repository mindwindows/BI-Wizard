import { ApiError, apiRequest } from "../../api";
import type { Page } from "../access/types";
import type { Column, ColumnRules, ColumnSaved, ColumnType, Dataset, DatasetDetail, DatasetStatus, DateUnit } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, {
    code: "INTERNAL_ERROR",
    message: "서버 응답 형식이 올바르지 않습니다.",
    details: null,
    request_id: null,
  });
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** B1 보기. 서버 기본은 active이며 화면은 항상 명시해서 보낸다(FU-2b). total도 같은 필터로 센다. */
export type DatasetView = DatasetStatus | "all";

/** B1. 정렬(내 소속 팀 먼저)은 서버가 하므로 받은 순서 그대로 쓴다. */
export async function listDatasets(
  params: { team_id?: number; status?: DatasetView; limit: number; offset: number },
  signal?: AbortSignal,
): Promise<Page<Dataset>> {
  const data = await apiRequest<unknown>(`/datasets${query(params)}`, { signal });
  if (!isRecord(data) || !Array.isArray(data.items) || typeof data.total !== "number") throw badShape();
  return data as unknown as Page<Dataset>;
}

function asDetail(data: unknown): DatasetDetail {
  if (
    !isRecord(data) ||
    typeof data.id !== "number" ||
    typeof data.def_version !== "number" ||
    !Array.isArray(data.columns) ||
    !isRecord(data.permissions)
  ) {
    throw badShape();
  }
  return data as unknown as DatasetDetail;
}

/** B7 보관. 본문 없음, 200 상세. 이미 보관 상태여도 200이다(FU-2b). */
export async function archiveDataset(id: number): Promise<DatasetDetail> {
  return asDetail(await apiRequest<unknown>(`/datasets/${id}/archive`, { method: "POST" }));
}

/** B8 복구. 본문 없음, 200 상세. 이미 사용 중이어도 200이다(FU-2b). */
export async function restoreDataset(id: number): Promise<DatasetDetail> {
  return asDetail(await apiRequest<unknown>(`/datasets/${id}/restore`, { method: "POST" }));
}

/** B2 */
export async function createDataset(body: { team_id: number; name: string; date_unit: DateUnit }): Promise<DatasetDetail> {
  return asDetail(await apiRequest<unknown>("/datasets", { method: "POST", body }));
}

/** B3 */
export async function getDataset(id: number, signal?: AbortSignal): Promise<DatasetDetail> {
  return asDetail(await apiRequest<unknown>(`/datasets/${id}`, { signal }));
}

/** B4. 바뀐 필드만 보낸다. base_date_column_id는 null로 지정 해제할 수 있다. */
export async function updateDataset(
  id: number,
  body: { expected_version: number; name?: string; date_unit?: DateUnit; base_date_column_id?: number | null },
): Promise<DatasetDetail> {
  return asDetail(await apiRequest<unknown>(`/datasets/${id}`, { method: "PATCH", body }));
}

function asSaved(data: unknown): ColumnSaved {
  if (!isRecord(data) || !isRecord(data.column) || typeof data.column.id !== "number" || typeof data.def_version !== "number") {
    throw badShape();
  }
  return data as unknown as ColumnSaved;
}

/** B5. 원본 열만(계산 열은 단위 1d). */
export async function addColumn(
  datasetId: number,
  body: {
    expected_version: number;
    display_name: string;
    type: ColumnType;
    required?: boolean;
    rules?: ColumnRules;
    tag?: string;
    position?: number;
  },
): Promise<ColumnSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/columns`, { method: "POST", body }));
}

/** B6. type·kind는 보내지 않는다(변경 불가). */
export async function updateColumn(
  datasetId: number,
  columnId: number,
  body: {
    expected_version: number;
    display_name?: string;
    required?: boolean;
    rules?: ColumnRules;
    tag?: string | null;
    position?: number;
  },
): Promise<ColumnSaved> {
  return asSaved(await apiRequest<unknown>(`/datasets/${datasetId}/columns/${columnId}`, { method: "PATCH", body }));
}

export const sortColumns = (columns: Column[]): Column[] =>
  [...columns].sort((a, b) => a.position - b.position || a.id - b.id);
