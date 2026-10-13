import { apiRequest } from "../../api";
import { listUsers } from "../access/api";
import type { User } from "../access/types";
import { PAGE_SIZE, type AuditFilters, type AuditPageData } from "./types";

/**
 * 필터와 쪽 위치를 F1 쿼리 문자열(앞에 `?` 포함)로 바꾼다. 빈 필터는 넣지 않고 limit·offset은 항상 넣는다.
 * 대상 번호는 대상 종류가 있을 때만 보낸다(05 F1 규칙 ②).
 */
export function buildAuditQuery(filters: AuditFilters, offset: number, limit: number = PAGE_SIZE): string {
  const search = new URLSearchParams();
  if (filters.from) search.set("from", filters.from);
  if (filters.to) search.set("to", filters.to);
  if (filters.actor) search.set("actor_user_id", filters.actor);
  if (filters.targetType) {
    search.set("target_type", filters.targetType);
    if (filters.targetId) search.set("target_id", filters.targetId);
  }
  if (filters.action) search.set("action", filters.action);
  search.set("limit", String(limit));
  search.set("offset", String(offset));
  return `?${search.toString()}`;
}

/** F1 */
export const listAuditLogs = (filters: AuditFilters, offset: number, signal?: AbortSignal) =>
  apiRequest<AuditPageData>(`/audit-logs${buildAuditQuery(filters, offset)}`, { signal });

/** A5 전체(200개씩 이어서 읽는다). 행위자 선택과 소속 요약의 사용자 이름에 쓴다. */
export async function listAllUsers(signal?: AbortSignal): Promise<User[]> {
  const all: User[] = [];
  for (let guard = 0; guard < 50; guard += 1) {
    const page = await listUsers({ limit: 200, offset: all.length });
    if (signal?.aborted) break;
    all.push(...page.items);
    if (page.items.length === 0 || all.length >= page.total) break;
  }
  return all;
}
