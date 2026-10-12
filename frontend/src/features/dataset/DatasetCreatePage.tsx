import { useId, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ErrorNotice } from "../../components";
import { useMe } from "../access/MeContext";
import { ROLE_LABELS, isActiveMembership } from "../access/types";
import { createDataset } from "./api";
import { DATASET_NAME_MAX, DATE_UNITS, DATE_UNIT_LABELS, type DateUnit } from "./types";

/** S3 데이터셋 만들기(폼, B2). 만든 뒤 작업공간(S4)으로 이동하고 열은 거기서 추가한다. */
export function DatasetCreatePage() {
  const { state, workTeamId } = useMe();
  if (state.status !== "ready") return null;
  // 정의 담당자인 활성 팀만 고를 수 있다(서버가 최종 검사).
  const teams = state.me.memberships.filter((m) => m.role === "definer" && isActiveMembership(m));
  if (teams.length === 0) {
    return (
      <section data-testid="screen-S3">
        <h1>S3 데이터셋 만들기</h1>
        <p className="muted" data-testid="no-definer-team">
          데이터셋은 팀의 {ROLE_LABELS.definer}만 만들 수 있습니다. 정의 담당자인 팀이 없습니다. 관리자에게 팀의 정의 담당자 지정을 요청해 주세요.
        </p>
        <Link to="/datasets">데이터셋 목록으로</Link>
      </section>
    );
  }
  const initialTeam = teams.find((t) => t.team_id === workTeamId)?.team_id ?? teams[0].team_id;
  return (
    <section data-testid="screen-S3">
      <h1>S3 데이터셋 만들기</h1>
      <CreateForm teams={teams.map((t) => ({ id: t.team_id, name: t.team_name }))} initialTeam={initialTeam} />
    </section>
  );
}

function CreateForm({ teams, initialTeam }: { teams: Array<{ id: number; name: string }>; initialTeam: number }) {
  const navigate = useNavigate();
  const ids = { team: useId(), name: useId(), unit: useId() };
  const [teamId, setTeamId] = useState(initialTeam);
  const [name, setName] = useState("");
  const [dateUnit, setDateUnit] = useState<DateUnit>("day");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const trimmed = name.normalize("NFC").trim();
    setError(null);
    if (trimmed === "") {
      setMessage("데이터셋 이름을 입력해 주세요.");
      return;
    }
    if (trimmed.length > DATASET_NAME_MAX) {
      setMessage(`데이터셋 이름은 ${DATASET_NAME_MAX}자 이하로 입력해 주세요.`);
      return;
    }
    setMessage(null);
    setBusy(true);
    try {
      const created = await createDataset({ team_id: teamId, name: trimmed, date_unit: dateUnit });
      void navigate(`/datasets/${created.id}`);
    } catch (caught) {
      setError(caught);
      setBusy(false);
    }
  }

  return (
    <form className="panel" aria-label="데이터셋 만들기" onSubmit={(event) => void submit(event)} noValidate>
      <label htmlFor={ids.team}>팀</label>
      <select id={ids.team} value={teamId} onChange={(event) => setTeamId(Number(event.target.value))}>
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {team.name}
          </option>
        ))}
      </select>
      <label htmlFor={ids.name}>이름</label>
      <input id={ids.name} value={name} maxLength={DATASET_NAME_MAX} onChange={(event) => setName(event.target.value)} />
      <label htmlFor={ids.unit}>날짜 단위</label>
      <select id={ids.unit} value={dateUnit} onChange={(event) => setDateUnit(event.target.value as DateUnit)}>
        {DATE_UNITS.map((unit) => (
          <option key={unit} value={unit}>
            {DATE_UNIT_LABELS[unit]}
          </option>
        ))}
      </select>
      <p className="muted">
        한 행은 한 기간입니다. 날짜 단위는 기간의 크기(일·월·연)이며, 행이 입력된 뒤에는 바꿀 수 없습니다. 열은 만든 뒤 작업공간에서 추가합니다.
      </p>
      {message ? (
        <p role="alert" className="state-error-inline">
          {message}
        </p>
      ) : null}
      {error ? <ErrorNotice error={error} /> : null}
      <div className="actions">
        <button type="submit" disabled={busy}>
          만들기
        </button>
        <Link to="/datasets">취소</Link>
      </div>
    </form>
  );
}
