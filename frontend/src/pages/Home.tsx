import { useEffect, useState } from "react";
import { checkApi, checkDatabase, type HealthResult } from "../api";
import { Loading } from "../components";

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

/** S1 포털 첫 화면. 팀 선택·접근 안내는 단위 1a(/api/me)에서 채운다. 지금은 연결 상태만 보여 준다. */
export function Home() {
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

  return (
    <section data-testid="screen-S1">
      <h1>S1 포털</h1>
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
