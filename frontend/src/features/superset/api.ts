import { ApiError, apiRequest } from "../../api";
import type { SupersetDatasetStatus, SyncStatus } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, { code: "INTERNAL_ERROR", message: "서버 응답 형식이 올바르지 않습니다.", details: null, request_id: null });
}

const STATUSES: readonly string[] = ["pending", "registered", "failed"];

function asStatus(value: unknown): SupersetDatasetStatus {
  if (!isRecord(value) || typeof value.dataset_id !== "number") throw badShape();
  const status: SyncStatus = typeof value.sync_status === "string" && STATUSES.includes(value.sync_status) ? (value.sync_status as SyncStatus) : "pending";
  return {
    dataset_id: value.dataset_id,
    superset_name: typeof value.superset_name === "string" ? value.superset_name : "",
    sync_status: status,
    synced_at: typeof value.synced_at === "string" ? value.synced_at : null,
    last_error: typeof value.last_error === "string" ? value.last_error : null,
  };
}

interface RawPage {
  items: SupersetDatasetStatus[];
  total: number;
}

async function getPage(params: URLSearchParams, signal?: AbortSignal): Promise<RawPage> {
  const data = await apiRequest<unknown>(`/superset/datasets?${params.toString()}`, { signal });
  if (Array.isArray(data)) return { items: data.map(asStatus), total: data.length };
  if (!isRecord(data) || !Array.isArray(data.items)) throw badShape();
  return { items: data.items.map(asStatus), total: typeof data.total === "number" ? data.total : data.items.length };
}

/** 한 번에 읽는 최대 쪽 수. 데이터셋 수천 개 규모까지 덮고 무한 반복을 막는다. */
const MAX_PAGES = 25;

/**
 * E1 전체 목록. 서버가 쪽 단위(limit 최대 200)로 주므로 total에 닿을 때까지 이어서 읽는다.
 * S9의 상태 필터·건수 요약은 이 전체 목록에서 화면이 계산한다(서버 필터 지원 여부에 의존하지 않는다).
 */
export async function listAllSupersetDatasets(signal?: AbortSignal): Promise<SupersetDatasetStatus[]> {
  const out: SupersetDatasetStatus[] = [];
  for (let page = 0; page < MAX_PAGES; page += 1) {
    const params = new URLSearchParams({ limit: "200", offset: String(out.length) });
    const result = await getPage(params, signal);
    out.push(...result.items);
    if (result.items.length === 0 || out.length >= result.total) break;
  }
  return out;
}

/**
 * E1에서 화면에 보이는 데이터셋들의 상태만 읽는다(S2). dataset_ids는 쉼표 목록이며 backend가 지원하는 추가 쿼리다(제안).
 * 서버가 이 쿼리를 무시하더라도 결과를 번호로 맞춰 쓰므로 화면은 깨지지 않는다.
 */
export async function listSupersetStatusFor(datasetIds: number[], signal?: AbortSignal): Promise<Map<number, SupersetDatasetStatus>> {
  const params = new URLSearchParams({ limit: "200", offset: "0", dataset_ids: datasetIds.join(",") });
  const result = await getPage(params, signal);
  return new Map(result.items.map((item) => [item.dataset_id, item]));
}

/** E2. dataset_ids를 생략하면 pending·failed 전부. 202 접수이며 결과는 E1 재조회로 확인한다. */
export async function requestSupersetSync(datasetIds?: number[]): Promise<number[]> {
  const body = datasetIds === undefined ? {} : { dataset_ids: datasetIds };
  const data = await apiRequest<unknown>("/superset/sync", { method: "POST", body });
  if (isRecord(data) && Array.isArray(data.accepted)) return data.accepted.filter((n): n is number => typeof n === "number");
  return [];
}
