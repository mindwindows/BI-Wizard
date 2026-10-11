import { useEffect, useState } from "react";
import { checkApi, checkDatabase, type HealthResult } from "./api";

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

export default function App() {
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
    <main className="shell">
      <h1>BI-Wizard</h1>
      <p>환경 구축(Gate ②) 골격입니다. 업무 화면은 아직 없습니다.</p>
      <table>
        <tbody>
          <StatusRow label="API" status={api} />
          <StatusRow label="DB" status={db} />
        </tbody>
      </table>
    </main>
  );
}
