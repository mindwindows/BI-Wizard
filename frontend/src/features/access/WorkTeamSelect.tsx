import { useId } from "react";
import { useMe } from "./MeContext";
import { isActiveMembership } from "./types";

/** 상단 작업 팀 선택. 여러 팀에 속한 사용자가 고른다(서버 비저장). 비활성 팀은 보이되 고를 수 없다. */
export function WorkTeamSelect() {
  const { state, workTeamId, setWorkTeamId } = useMe();
  const id = useId();
  if (state.status !== "ready") return null;
  const teams = state.me.memberships;
  if (teams.length === 0) return <span className="muted-on-dark">소속 팀 없음</span>;
  if (!teams.some(isActiveMembership)) return <span className="muted-on-dark">활성 팀 없음</span>;
  return (
    <span className="work-team">
      <label htmlFor={id}>작업 팀</label>
      <select id={id} value={workTeamId ?? ""} onChange={(event) => setWorkTeamId(Number(event.target.value))}>
        {teams.map((team) => (
          <option key={team.team_id} value={team.team_id} disabled={!isActiveMembership(team)}>
            {team.team_name}
            {isActiveMembership(team) ? "" : " (비활성)"}
          </option>
        ))}
      </select>
    </span>
  );
}
