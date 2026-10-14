import { ApiError, apiRequest } from "../../api";
import type { ReferenceCorrection, ReferenceItem, ReferencePage, ReferenceUsage, ReferenceValue } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function badShape(): ApiError {
  return new ApiError(200, { code: "INTERNAL_ERROR", message: "서버 응답 형식이 올바르지 않습니다.", details: null, request_id: null });
}

function asPage<T>(data: unknown): ReferencePage<T> {
  if (!isRecord(data) || !Array.isArray(data.items) || typeof data.total !== "number") throw badShape();
  return data as unknown as ReferencePage<T>;
}

function asItem(data: unknown): ReferenceItem {
  if (!isRecord(data) || typeof data.id !== "number" || typeof data.name !== "string") throw badShape();
  return data as unknown as ReferenceItem;
}

function asValue(data: unknown): ReferenceValue {
  if (!isRecord(data) || typeof data.id !== "number" || typeof data.year !== "number" || typeof data.value !== "string") throw badShape();
  return data as unknown as ReferenceValue;
}

const query = (limit: number, offset: number) => `?limit=${limit}&offset=${offset}`;

/** R1. 이름 가나다순. 수식 편집기 자동완성은 limit=200으로 읽는다. */
export async function listReferenceItems(params: { limit: number; offset: number }, signal?: AbortSignal): Promise<ReferencePage<ReferenceItem>> {
  return asPage<ReferenceItem>(await apiRequest<unknown>(`/reference-items${query(params.limit, params.offset)}`, { signal }));
}

/** R2 관리자 */
export async function createReferenceItem(body: { name: string; description?: string }): Promise<ReferenceItem> {
  return asItem(await apiRequest<unknown>("/reference-items", { method: "POST", body }));
}

/** R3. 연도 내림차순 */
export async function listReferenceValues(itemId: number, params: { limit: number; offset: number }, signal?: AbortSignal): Promise<ReferencePage<ReferenceValue>> {
  return asPage<ReferenceValue>(await apiRequest<unknown>(`/reference-items/${itemId}/values${query(params.limit, params.offset)}`, { signal }));
}

/** R4 관리자. year는 JSON 정수, value는 십진 문자열(JSON 숫자는 서버가 거부한다). */
export async function addReferenceValue(itemId: number, body: { year: number; value: string }): Promise<ReferenceValue> {
  return asValue(await apiRequest<unknown>(`/reference-items/${itemId}/values`, { method: "POST", body }));
}

/** R5 관리자. 정정. year·item_id는 보내지 않는다. */
export async function correctReferenceValue(itemId: number, valueId: number, body: { value: string }): Promise<ReferenceCorrection> {
  const data = await apiRequest<unknown>(`/reference-items/${itemId}/values/${valueId}`, { method: "PATCH", body });
  if (!isRecord(data) || typeof data.previous_value !== "string" || typeof data.changed !== "boolean") throw badShape();
  return { value: asValue(data.value), previous_value: data.previous_value, changed: data.changed };
}

/** R6 관리자(선택 기능). 정정 확인창의 영향 목록용이며 실패해도 정정은 막지 않는다. */
export async function getReferenceUsage(itemId: number, signal?: AbortSignal): Promise<ReferenceUsage> {
  const data = await apiRequest<unknown>(`/reference-items/${itemId}/usage`, { signal });
  if (!isRecord(data) || !Array.isArray(data.items)) throw badShape();
  return {
    items: data.items.filter(isRecord) as unknown as ReferenceUsage["items"],
    total: typeof data.total === "number" ? data.total : data.items.length,
    truncated: data.truncated === true,
  };
}
