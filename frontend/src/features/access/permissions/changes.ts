import { createTeam, createUser, deleteMember, putMember, updateTeam, updateUser } from "../api";
import { ROLE_LABELS, type TeamRole } from "../types";

/** S6에서 모아 두었다가 확인 뒤 한 번에 호출하는 변경. 라벨은 요약 문구용(저장 시점의 화면 이름)이다. */
export type Change =
  | { kind: "team_create"; code: string; name: string }
  | { kind: "team_update"; teamId: number; label: string; name?: string; is_active?: boolean }
  | { kind: "user_create"; login_id: string; display_name: string; is_admin: boolean }
  | { kind: "user_update"; userId: number; label: string; display_name?: string; is_admin?: boolean; is_active?: boolean }
  | { kind: "member_set"; teamId: number; teamLabel: string; userId: number; userLabel: string; role: TeamRole; from: TeamRole | null }
  | { kind: "member_remove"; teamId: number; teamLabel: string; userId: number; userLabel: string; from: TeamRole };

export type Staged = Record<string, Change>;

export const teamKey = (id: number) => `team:${id}`;
export const userKey = (id: number) => `user:${id}`;
export const memberKey = (teamId: number, userId: number) => `member:${teamId}:${userId}`;
export const newTeamKey = (code: string) => `team:new:${code}`;
export const newUserKey = (loginId: string) => `user:new:${loginId}`;

/** 변경 요약 확인창에 보이는 한 줄 설명. */
export function describeChange(change: Change): string {
  switch (change.kind) {
    case "team_create":
      return `팀 만들기: ${change.name} (코드 ${change.code})`;
    case "team_update": {
      const parts: string[] = [];
      if (change.name !== undefined) parts.push(`이름을 "${change.name}"(으)로 변경`);
      if (change.is_active === false) parts.push("사용 중지(비활성)");
      if (change.is_active === true) parts.push("다시 사용");
      return `팀 수정: ${change.label} - ${parts.join(", ")}`;
    }
    case "user_create":
      return `사용자 사전 등록: ${change.display_name} (${change.login_id})${change.is_admin ? ", 관리자" : ""}`;
    case "user_update": {
      const parts: string[] = [];
      if (change.display_name !== undefined) parts.push(`표시 이름을 "${change.display_name}"(으)로 변경`);
      if (change.is_admin === true) parts.push("관리자 권한 부여");
      if (change.is_admin === false) parts.push("관리자 권한 해제");
      if (change.is_active === false) parts.push("사용 중지(비활성)");
      if (change.is_active === true) parts.push("다시 사용");
      return `사용자 수정: ${change.label} - ${parts.join(", ")}`;
    }
    case "member_set":
      return change.from === null
        ? `소속 추가: ${change.userLabel} → ${change.teamLabel} (${ROLE_LABELS[change.role]})`
        : `역할 변경: ${change.userLabel} / ${change.teamLabel} (${ROLE_LABELS[change.from]} → ${ROLE_LABELS[change.role]})`;
    case "member_remove":
      return `소속 해제: ${change.userLabel} ← ${change.teamLabel} (현재 ${ROLE_LABELS[change.from]})`;
  }
}

/**
 * 호출 순서: 팀 만들기 → 사용자 등록 → 팀 수정 → (권한을 주는 사용자 수정) → 소속 추가·역할 변경 → 소속 해제 → (권한을 거두는 사용자 수정).
 * 관리자를 새로 지정한 뒤에 다른 관리자를 해제해야 마지막 관리자 보호(LAST_ADMIN)에 걸리지 않기 때문이다.
 * 같은 단계 안에서는 모은 순서를 지킨다.
 */
function rank(change: Change): number {
  switch (change.kind) {
    case "team_create":
      return 0;
    case "user_create":
      return 1;
    case "team_update":
      return 2;
    case "user_update":
      return change.is_admin === false || change.is_active === false ? 6 : 3;
    case "member_set":
      return 4;
    case "member_remove":
      return 5;
  }
}

export function orderChanges(staged: Staged): Array<[string, Change]> {
  return Object.entries(staged)
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => rank(a.entry[1]) - rank(b.entry[1]) || a.index - b.index)
    .map(({ entry }) => entry);
}

/** 변경 하나를 해당 API(A3~A9)로 호출한다. 본문에는 바뀐 필드만 싣는다. */
export async function applyChange(change: Change): Promise<void> {
  switch (change.kind) {
    case "team_create":
      await createTeam({ code: change.code, name: change.name });
      return;
    case "team_update": {
      const body: { name?: string; is_active?: boolean } = {};
      if (change.name !== undefined) body.name = change.name;
      if (change.is_active !== undefined) body.is_active = change.is_active;
      await updateTeam(change.teamId, body);
      return;
    }
    case "user_create":
      await createUser({ login_id: change.login_id, display_name: change.display_name, is_admin: change.is_admin });
      return;
    case "user_update": {
      const body: { display_name?: string; is_admin?: boolean; is_active?: boolean } = {};
      if (change.display_name !== undefined) body.display_name = change.display_name;
      if (change.is_admin !== undefined) body.is_admin = change.is_admin;
      if (change.is_active !== undefined) body.is_active = change.is_active;
      await updateUser(change.userId, body);
      return;
    }
    case "member_set":
      await putMember(change.teamId, change.userId, change.role);
      return;
    case "member_remove":
      await deleteMember(change.teamId, change.userId);
      return;
  }
}
