import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { ApiError } from "../../api";
import { getMe } from "./api";
import { isActiveMembership, type Me } from "./types";

export type DenyReason = "UNAUTHENTICATED" | "USER_NOT_REGISTERED" | "USER_INACTIVE";

export type MeState =
  | { status: "loading" }
  | { status: "ready"; me: Me }
  | { status: "denied"; reason: DenyReason }
  | { status: "error"; error: unknown };

interface MeContextValue {
  state: MeState;
  /** 작업 팀. 서버에 저장하지 않는 화면 상태(+ sessionStorage)다. 소속이 없으면 null. */
  workTeamId: number | null;
  setWorkTeamId: (teamId: number) => void;
  /** /me를 다시 읽는다(스텁 신원을 바꾼 뒤 등). */
  refresh: () => void;
}

const MeContext = createContext<MeContextValue | null>(null);

export const WORK_TEAM_STORAGE_KEY = "bi-wizard.workTeamId";

function readStoredTeam(): number | null {
  try {
    const raw = window.sessionStorage.getItem(WORK_TEAM_STORAGE_KEY);
    const value = raw === null ? NaN : Number(raw);
    return Number.isInteger(value) ? value : null;
  } catch {
    return null;
  }
}

/** 401과 403 두 가지 사용자 사유는 접근 안내(S1)로, 그 밖의 실패는 일반 오류로 나눈다. */
export async function fetchMeState(): Promise<MeState> {
  try {
    return { status: "ready", me: await getMe() };
  } catch (error) {
    if (error instanceof ApiError) {
      if (error.code === "UNAUTHENTICATED" || error.status === 401) return { status: "denied", reason: "UNAUTHENTICATED" };
      if (error.code === "USER_NOT_REGISTERED") return { status: "denied", reason: "USER_NOT_REGISTERED" };
      if (error.code === "USER_INACTIVE") return { status: "denied", reason: "USER_INACTIVE" };
    }
    return { status: "error", error };
  }
}

export function MeProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<MeState>({ status: "loading" });
  const [storedTeam, setStoredTeam] = useState<number | null>(readStoredTeam);

  useEffect(() => {
    let active = true;
    void fetchMeState().then((next) => {
      if (active) setState(next);
    });
    return () => {
      active = false;
    };
  }, []);

  const refresh = useCallback(() => {
    setState({ status: "loading" });
    void fetchMeState().then(setState);
  }, []);

  const setWorkTeamId = useCallback((teamId: number) => {
    setStoredTeam(teamId);
    try {
      window.sessionStorage.setItem(WORK_TEAM_STORAGE_KEY, String(teamId));
    } catch {
      // 저장소를 쓸 수 없어도 화면 상태로는 동작한다.
    }
  }, []);

  const value = useMemo<MeContextValue>(() => {
    // 저장된 값이 현재 소속에 없거나 비활성 팀이면(사용자 전환, 소속 해제, 팀 비활성) 첫 활성 팀을 쓴다.
    let workTeamId: number | null = null;
    if (state.status === "ready") {
      const teams = state.me.memberships.filter(isActiveMembership);
      workTeamId = teams.some((m) => m.team_id === storedTeam) ? storedTeam : (teams[0]?.team_id ?? null);
    }
    return { state, workTeamId, setWorkTeamId, refresh };
  }, [state, storedTeam, setWorkTeamId, refresh]);

  return <MeContext.Provider value={value}>{children}</MeContext.Provider>;
}

export function useMe(): MeContextValue {
  const value = useContext(MeContext);
  if (!value) throw new Error("MeProvider 안에서만 사용할 수 있습니다.");
  return value;
}
