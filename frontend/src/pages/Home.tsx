import { useEffect, useState } from "react";
import { checkApi, checkDatabase, type HealthResult } from "../api";
import { Loading } from "../components";
import { useMe } from "../features/access/MeContext";
import { ROLE_LABELS, isActiveMembership } from "../features/access/types";

type Status = HealthResult | "checking";

function StatusRow({ label, status }: { label: string; status: Status }) {
  const text = status === "checking" ? "확인 중" : `${status.ok ? "정상" : "오류"} (${status.detail})`;
  return (
    <tr>
      <th scope="row">{label}</th>
      <td data-testid={`status-${label}`}>{text}</td>
    </tr>
  );
}

/** S1 포털 첫 화면: 내 정보, 소속 팀과 역할, 연결 상태. 접근 불가 안내는 셸이 대신 보여 준다. */
export function Home() {
  const { state, workTeamId } = useMe();
  const [api, setApi] = useState<Status>("checking");
  const [db, setDb] = useState<Status>("checking");

  useEffect(() => {
    let active = true;
    void checkApi().then((result) => active && setApi(result));
    void checkDatabase().then((result) => active && setDb(result));
    return () => {
      active = false;
    };
  }, []);

  const me = state.status === "ready" ? state.me : null;

  return (
    <section data-testid="screen-S1">
      <h1>S1 포털</h1>
      {me ? (
        <>
          <p>
            {me.display_name}님{me.is_admin ? " (관리자)" : ""}
          </p>
          <h2>소속 팀</h2>
          {me.memberships.length === 0 ? (
            <p className="muted" data-testid="no-teams">
              소속된 팀이 없습니다. 데이터는 볼 수 있지만 입력과 정의는 팀에 소속된 뒤 가능합니다. 관리자에게 팀 소속을 요청해 주세요.
            </p>
          ) : (
            <table aria-label="소속 팀">
              <thead>
                <tr>
                  <th scope="col">팀</th>
                  <th scope="col">역할</th>
                  <th scope="col">작업 팀</th>
                </tr>
              </thead>
              <tbody>
                {me.memberships.map((m) => (
                  <tr key={m.team_id}>
                    <td>
                      {m.team_name}
                      {isActiveMembership(m) ? null : <span className="badge badge-off">비활성</span>}
                    </td>
                    <td>{ROLE_LABELS[m.role] ?? m.role}</td>
                    <td>{m.team_id === workTeamId ? "선택됨" : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      ) : null}
      <h2>연결 상태</h2>
      {api === "checking" || db === "checking" ? <Loading label="연결 상태 확인 중" /> : null}
      <table>
        <tbody>
          <StatusRow label="API" status={api} />
          <StatusRow label="DB" status={db} />
        </tbody>
      </table>
    </section>
  );
}
