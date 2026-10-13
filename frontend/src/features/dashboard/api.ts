import { ApiError, apiRequest } from "../../api";
import type { Dashboard, DashboardList } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, { code: "INTERNAL_ERROR", message: "서버 응답 형식이 올바르지 않습니다.", details: null, request_id: null });
}

function asDashboard(value: unknown): Dashboard {
  if (!isRecord(value) || typeof value.id !== "number" || typeof value.name !== "string" || typeof value.embedded_uuid !== "string") throw badShape();
  return { id: value.id, name: value.name, embedded_uuid: value.embedded_uuid, is_active: value.is_active !== false };
}

/** E3. 05는 "목록"이라고만 적었고 05 §1 목록 규칙에 따라 {items,total}이다. 배열이어도 받는다. 한 번에 최대 200개(목록 상한). */
export async function listDashboards(options: { includeInactive?: boolean } = {}, signal?: AbortSignal): Promise<DashboardList> {
  const params = new URLSearchParams({ limit: "200", offset: "0" });
  if (options.includeInactive) params.set("include_inactive", "true");
  const data = await apiRequest<unknown>(`/dashboards?${params.toString()}`, { signal });
  if (Array.isArray(data)) return { items: data.map(asDashboard), total: data.length };
  if (!isRecord(data) || !Array.isArray(data.items)) throw badShape();
  return { items: data.items.map(asDashboard), total: typeof data.total === "number" ? data.total : data.items.length };
}

/** E4. embedded_uuid는 호출하는 쪽이 소문자 36자 정규형으로 만들어 보낸다. */
export async function createDashboard(body: { name: string; embedded_uuid: string }): Promise<Dashboard> {
  return asDashboard(await apiRequest<unknown>("/dashboards", { method: "POST", body }));
}

/** E5. 이름 변경, 해제·재사용(is_active). embedded_uuid는 바꿀 수 없다. */
export async function updateDashboard(id: number, body: { name?: string; is_active?: boolean }): Promise<Dashboard> {
  return asDashboard(await apiRequest<unknown>(`/dashboards/${id}`, { method: "PATCH", body }));
}
