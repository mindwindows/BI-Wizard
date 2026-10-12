import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { listAllTeams } from "../access/api";
import { useMe } from "../access/MeContext";
import type { Page, Team } from "../access/types";
import { listDatasets } from "./api";
import { formatDate } from "./format";
import { DATE_UNIT_LABELS, type Dataset } from "./types";

const PAGE_SIZE = 50;

interface LoadResult {
  key: string;
  page?: Page<Dataset>;
  error?: unknown;
}

/**
 * S2 데이터셋 목록(콘솔형, B1). 정렬(내 소속 팀 먼저)은 서버가 하므로 받은 순서를 그대로 보여 준다.
 * 동기 상태 열은 GET /superset/datasets가 생기는 단위 1e에서 이 표에 결합한다(지금은 열도 호출도 없다).
 */
export function DatasetListPage() {
  const { state, workTeamId } = useMe();
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamId, setTeamId] = useState<number | undefined>(undefined);
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<LoadResult | null>(null);

  useEffect(() => {
    let active = true;
    // 팀 이름은 표시용이다. 못 읽어도 목록은 보여 준다(팀 번호로 대신 표시).
    listAllTeams()
      .then((items) => active && setTeams(items))
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  const requestKey = `${reloadKey}|${teamId ?? ""}|${offset}`;
  useEffect(() => {
    let active = true;
    listDatasets({ team_id: teamId, limit: PAGE_SIZE, offset })
      .then((page) => active && setResult({ key: requestKey, page }))
      .catch((error: unknown) => active && setResult({ key: requestKey, error }));
    return () => {
      active = false;
    };
  }, [requestKey, teamId, offset]);

  const me = state.status === "ready" ? state.me : null;
  const workMembership = me?.memberships.find((m) => m.team_id === workTeamId);
  // 화면 편의일 뿐이다. 최종 방어선은 서버의 B2 권한 검사다.
  const canCreate = workMembership?.role === "definer" && workMembership.team_is_active !== false;

  const loading = result?.key !== requestKey;
  const items = result?.page?.items ?? [];
  const total = result?.page?.total ?? 0;
  const teamName = (id: number) => teams.find((t) => t.id === id)?.name ?? `팀 ${id}`;

  return (
    <section data-testid="screen-S2" className="console">
      <h1>S2 데이터셋 목록</h1>
      <div className="toolbar">
        <label>
          팀 필터
          <select
            value={teamId ?? ""}
            onChange={(event) => {
              setOffset(0);
              setTeamId(event.target.value === "" ? undefined : Number(event.target.value));
            }}
          >
            <option value="">전체 팀</option>
            {teams.map((team) => (
              <option key={team.id} value={team.id}>
                {team.name}
              </option>
            ))}
          </select>
        </label>
        {canCreate ? (
          <Link to="/datasets/new" className="button-link">
            새 데이터셋
          </Link>
        ) : (
          <span className="muted" data-testid="define-hint">
            데이터셋은 작업 팀의 정의 담당자만 만들 수 있습니다.
          </span>
        )}
      </div>

      {loading ? <Loading label="데이터셋을 불러오는 중" /> : null}
      {!loading && result?.error ? (
        <ErrorNotice error={result.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {!loading && result?.page ? (
        <>
          {items.length === 0 ? (
            <p className="muted" data-testid="no-datasets">
              {teamId !== undefined ? "이 팀에는 등록된 데이터셋이 없습니다." : "등록된 데이터셋이 없습니다."}
            </p>
          ) : (
            <table aria-label="데이터셋 목록" className="list-table">
              <thead>
                <tr>
                  <th scope="col">이름</th>
                  <th scope="col">팀</th>
                  <th scope="col">날짜 단위</th>
                  <th scope="col">생성자</th>
                  <th scope="col">생성일</th>
                  {/* 1e 연결 지점: GET /superset/datasets 응답을 dataset_id로 결합해 "동기 상태" 열을 여기에 추가한다. */}
                </tr>
              </thead>
              <tbody>
                {items.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <Link to={`/datasets/${dataset.id}`}>{dataset.name}</Link>
                    </td>
                    <td>{teamName(dataset.team_id)}</td>
                    <td>{DATE_UNIT_LABELS[dataset.date_unit] ?? dataset.date_unit}</td>
                    <td>{dataset.created_by?.display_name ?? ""}</td>
                    <td>{formatDate(dataset.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {total > 0 ? (
            <div className="pager">
              <span>
                전체 {total}개 중 {offset + 1}–{Math.min(offset + PAGE_SIZE, total)}
              </span>
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                이전
              </button>
              <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                다음
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
