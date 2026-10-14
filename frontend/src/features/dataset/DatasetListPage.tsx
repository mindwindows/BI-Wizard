import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { listAllTeams } from "../access/api";
import { useMe } from "../access/MeContext";
import type { Page, Team } from "../access/types";
import { ArchiveAction, doneText } from "./ArchiveAction";
import { listDatasets, type DatasetView } from "./api";
import { listSupersetStatusFor } from "../superset/api";
import { SyncBadge } from "../superset/SyncBadge";
import type { SupersetDatasetStatus } from "../superset/types";
import { formatDate } from "./format";
import { DATE_UNIT_LABELS, type Dataset } from "./types";

const PAGE_SIZE = 50;

const VIEW_LABELS: Record<DatasetView, string> = { active: "사용 중", archived: "보관됨", all: "전체" };
const VIEWS: DatasetView[] = ["active", "archived", "all"];

/** 동기 상태 칸. undefined = 읽는 중, null = 읽었지만 이 데이터셋의 상태를 못 받음. */
function SyncCell({ status }: { status: SupersetDatasetStatus | null | undefined }) {
  if (status === undefined) return <span className="muted">확인 중…</span>;
  if (status === null) return <span className="muted">확인 못함</span>;
  return (
    <span title={status.last_error ?? undefined}>
      <SyncBadge status={status.sync_status} />
    </span>
  );
}

interface LoadResult {
  key: string;
  page?: Page<Dataset>;
  error?: unknown;
}

/**
 * S2 데이터셋 목록(콘솔형, B1). 정렬(내 소속 팀 먼저)은 서버가 하므로 받은 순서를 그대로 보여 준다.
 * "동기 상태" 열(1e)은 표시된 쪽의 데이터셋 번호로 E1을 한 번 불러 결합한다(dataset은 superset을 읽지 않는다, 04 §3).
 * 실패 사유(last_error)는 관리자에게만 서버가 채워 주며 목록에는 배지만 보이고 사유는 툴팁으로 둔다.
 */
export function DatasetListPage() {
  const { state, workTeamId } = useMe();
  const [teams, setTeams] = useState<Team[]>([]);
  const [teamId, setTeamId] = useState<number | undefined>(undefined);
  const [view, setView] = useState<DatasetView>("active");
  const [notice, setNotice] = useState<string | null>(null);
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

  const requestKey = `${reloadKey}|${teamId ?? ""}|${view}|${offset}`;
  useEffect(() => {
    let active = true;
    listDatasets({ team_id: teamId, status: view, limit: PAGE_SIZE, offset })
      .then((page) => active && setResult({ key: requestKey, page }))
      .catch((error: unknown) => active && setResult({ key: requestKey, error }));
    return () => {
      active = false;
    };
  }, [requestKey, teamId, view, offset]);

  // 동기 상태: 표시된 쪽의 번호들로 한 번 읽는다. 못 읽어도 목록은 그대로 보여 주고 열에는 "확인 못함"을 둔다.
  const pageIds = (result?.page?.items ?? []).map((dataset) => dataset.id).join(",");
  const [sync, setSync] = useState<{ ids: string; map?: Map<number, SupersetDatasetStatus> } | null>(null);
  useEffect(() => {
    if (pageIds === "") return;
    const controller = new AbortController();
    listSupersetStatusFor(pageIds.split(",").map(Number), controller.signal)
      .then((map) => !controller.signal.aborted && setSync({ ids: pageIds, map }))
      .catch(() => !controller.signal.aborted && setSync({ ids: pageIds }));
    return () => controller.abort();
  }, [pageIds]);
  const syncReady = sync !== null && sync.ids === pageIds;

  const me = state.status === "ready" ? state.me : null;
  const workMembership = me?.memberships.find((m) => m.team_id === workTeamId);
  // 화면 편의일 뿐이다. 최종 방어선은 서버의 B2 권한 검사다.
  const canCreate = workMembership?.role === "definer" && workMembership.team_is_active !== false;

  // 보관·복구 버튼은 그 데이터셋 팀의 정의 담당자에게만 보인다(관리자 예외 없음, 비활성 팀이어도 표시). 최종 방어선은 서버(B7·B8)다.
  const isDefinerOf = (teamIdOfDataset: number) => me?.memberships.some((m) => m.team_id === teamIdOfDataset && m.role === "definer") ?? false;

  const loading = result?.key !== requestKey;
  const items = result?.page?.items ?? [];
  const total = result?.page?.total ?? 0;
  const showActions = items.some((dataset) => isDefinerOf(dataset.team_id));
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
        <label>
          보기
          <select
            value={view}
            onChange={(event) => {
              setOffset(0);
              setNotice(null);
              setView(event.target.value as DatasetView);
            }}
          >
            {VIEWS.map((v) => (
              <option key={v} value={v}>
                {VIEW_LABELS[v]}
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

      {notice ? (
        <p role="status" className="state state-ok" data-testid="archive-notice">
          {notice}
        </p>
      ) : null}
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
              {view === "archived"
                ? "보관된 데이터셋이 없습니다."
                : teamId !== undefined
                  ? "이 팀에는 등록된 데이터셋이 없습니다."
                  : "등록된 데이터셋이 없습니다."}
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
                  <th scope="col">동기 상태</th>
                  {showActions ? <th scope="col">관리</th> : null}
                </tr>
              </thead>
              <tbody>
                {items.map((dataset) => (
                  <tr key={dataset.id}>
                    <td>
                      <Link to={`/datasets/${dataset.id}`}>{dataset.name}</Link>
                      {dataset.status === "archived" ? <span className="badge badge-archived">보관</span> : null}
                    </td>
                    <td>{teamName(dataset.team_id)}</td>
                    <td>{DATE_UNIT_LABELS[dataset.date_unit] ?? dataset.date_unit}</td>
                    <td>{dataset.created_by?.display_name ?? ""}</td>
                    <td>{formatDate(dataset.created_at)}</td>
                    <td data-testid={`sync-${dataset.id}`}>
                      <SyncCell status={syncReady ? (sync.map?.get(dataset.id) ?? null) : undefined} />
                    </td>
                    {showActions ? (
                      <td>
                        {isDefinerOf(dataset.team_id) ? (
                          <ArchiveAction
                            dataset={dataset}
                            onDone={(kind) => {
                              setNotice(doneText(kind, dataset.name));
                              setReloadKey((value) => value + 1);
                            }}
                          />
                        ) : null}
                      </td>
                    ) : null}
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
