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
  /** 05 A1: 비활성 팀 소속도 응답에 나오며 화면은 이 값으로 작업 팀 선택에서 거른다. */
  team_is_active: boolean;
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

/** 05 §1 이름 규칙: 사용자 표시 이름 100자, 로그인 ID 200자(03b 17-1 결정 4). */
export const USER_DISPLAY_NAME_MAX = 100;
export const LOGIN_ID_MAX = 200;

/** `team_is_active`가 false인 소속은 비활성 팀이다. */
export const isActiveMembership = (m: Membership): boolean => m.team_is_active !== false;

/** 05 §1: 팀 표시 이름 상한 50자, A3 code 형식. */
export const TEAM_NAME_MAX = 50;
export const TEAM_CODE_PATTERN = /^[a-z0-9_]{1,32}$/;
