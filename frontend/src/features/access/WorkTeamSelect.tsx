import { useId } from "react";
import { useMe } from "./MeContext";

/** 상단 작업 팀 선택. 여러 팀에 속한 사용자가 고른다(서버 비저장). */
export function WorkTeamSelect() {
  const { state, workTeamId, setWorkTeamId } = useMe();
  const id = useId();
  if (state.status !== "ready") return null;
  const teams = state.me.memberships;
  if (teams.length === 0) return <span className="muted-on-dark">소속 팀 없음</span>;
  return (
    <span className="work-team">
      <label htmlFor={id}>작업 팀</label>
      <select id={id} value={workTeamId ?? ""} onChange={(event) => setWorkTeamId(Number(event.target.value))}>
        {teams.map((team) => (
          <option key={team.team_id} value={team.team_id}>
            {team.team_name}
          </option>
        ))}
      </select>
    </span>
  );
}
