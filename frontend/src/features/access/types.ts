/** 05 §2-1 (A1~A9), §2-6 (DV1) 응답 형태. 계약에 없는 필드는 가정하지 않는다. */
export type TeamRole = "definer" | "entry";

export const ROLE_LABELS: Record<TeamRole, string> = {
  definer: "정의 담당자",
  entry: "입력자",
};

export interface Membership {
  team_id: number;
  team_code: string;
  team_name: string;
  role: TeamRole;
}

/** A1 GET /me */
export interface Me {
  id: number;
  display_name: string;
  is_active: boolean;
  is_admin: boolean;
  memberships: Membership[];
}

/** A2~A4 */
export interface Team {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
}

/** A5~A7 */
export interface User {
  id: number;
  login_id: string;
  display_name: string;
  is_admin: boolean;
  is_active: boolean;
  memberships: Array<{ team_id: number; role: TeamRole }>;
}

/** 05 §1 목록 규칙 */
export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** DV1 */
export interface StubUser {
  login_id: string;
  display_name: string;
  is_admin: boolean;
}

export interface StubUsers {
  items: StubUser[];
  /** 현재 선택된 스텁 login_id. 없으면 null. */
  current: string | null;
}

/** 05 §1: 팀 표시 이름 상한 50자, A3 code 형식. */
export const TEAM_NAME_MAX = 50;
export const TEAM_CODE_PATTERN = /^[a-z0-9_]{1,32}$/;
