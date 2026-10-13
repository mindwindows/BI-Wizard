import { ApiError, apiRequest } from "../../api";
import type { Me, Page, StubUsers, Team, TeamRole, User } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** A1. 응답 모양이 계약과 다르면 화면이 깨지지 않게 오류로 처리한다. */
export async function getMe(signal?: AbortSignal): Promise<Me> {
  const data = await apiRequest<unknown>("/me", { signal });
  if (!isRecord(data) || typeof data.id !== "number" || !Array.isArray(data.memberships)) {
    throw new ApiError(200, {
      code: "INTERNAL_ERROR",
      message: "서버 응답 형식이 올바르지 않습니다.",
      details: null,
      request_id: null,
    });
  }
  return data as unknown as Me;
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

/** A2 한 쪽. 서버 상한은 limit 200이다. */
export const listTeamsPage = (limit: number, offset: number) =>
  apiRequest<Page<Team>>(`/teams${query({ limit, offset })}`);

/** A2 전체(200개씩 이어서 읽는다). 비활성 팀도 응답에 포함되는 것으로 읽는다(is_active 필드). */
export async function listAllTeams(): Promise<Team[]> {
  const all: Team[] = [];
  for (let guard = 0; guard < 50; guard += 1) {
    const page = await listTeamsPage(200, all.length);
    all.push(...page.items);
    if (page.items.length === 0 || all.length >= page.total) break;
  }
  return all;
}

/** A5 */
export const listUsers = (params: { q?: string; limit: number; offset: number }) =>
  apiRequest<Page<User>>(`/users${query(params)}`);

/** A3 */
export const createTeam = (body: { code: string; name: string }) =>
  apiRequest<Team>("/teams", { method: "POST", body });

/** A4 */
export const updateTeam = (teamId: number, body: { name?: string; is_active?: boolean }) =>
  apiRequest<Team>(`/teams/${teamId}`, { method: "PATCH", body });

/** A6 */
export const createUser = (body: { login_id: string; display_name: string; is_admin?: boolean }) =>
  apiRequest<User>("/users", { method: "POST", body });

/** A7 */
export const updateUser = (userId: number, body: { display_name?: string; is_admin?: boolean; is_active?: boolean }) =>
  apiRequest<User>(`/users/${userId}`, { method: "PATCH", body });

/** A8 */
export const putMember = (teamId: number, userId: number, role: TeamRole) =>
  apiRequest<{ team_id: number; user_id: number; role: TeamRole }>(`/teams/${teamId}/members/${userId}`, {
    method: "PUT",
    body: { role },
  });

/** A9 */
export const deleteMember = (teamId: number, userId: number) =>
  apiRequest<void>(`/teams/${teamId}/members/${userId}`, { method: "DELETE" });

/**
 * DV1. 200이면 전환기 데이터, 404(스텁이 꺼진 운영 설정)나 그 밖의 실패면 null이다.
 * 판별은 응답 여부뿐이다(config.js·환경변수 변경 없음, 05 §2-6).
 */
export async function getStubUsers(signal?: AbortSignal): Promise<StubUsers | null> {
  try {
    const data = await apiRequest<unknown>("/dev/stub-users", { signal });
    if (!isRecord(data) || !Array.isArray(data.items)) return null;
    let current: string | null = null;
    if (typeof data.current === "string") current = data.current;
    else if (isRecord(data.current) && typeof data.current.login_id === "string") current = data.current.login_id;
    return { items: data.items as StubUsers["items"], current };
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return null;
  }
}

/** DV2 */
export const setStubUser = (loginId: string) =>
  apiRequest<void>("/dev/stub-user", { method: "PUT", body: { login_id: loginId } });

/** DV3 */
export const clearStubUser = () => apiRequest<void>("/dev/stub-user", { method: "DELETE" });
