import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { listAllSupersetDatasets, requestSupersetSync } from "../superset/api";
import { formatMinute } from "../superset/format";
import { SyncBadge } from "../superset/SyncBadge";
import { SYNC_LABELS, type SupersetDatasetStatus, type SyncStatus } from "../superset/types";

const PAGE_SIZE = 50;
/** 접수 뒤 상태가 바뀌었는지 다시 읽는 간격(ms)과 최대 횟수. 과하지 않게 2분 안팎에서 멈춘다. */
export const POLL_INTERVAL_MS = 5_000;
export const MAX_POLLS = 24;

type StatusFilter = "all" | SyncStatus;

interface Loaded {
  items?: SupersetDatasetStatus[];
  error?: unknown;
}

/**
 * S9 'Superset 동기' 구역(E1 상태 목록, E2 다시 동기). 데이터셋을 대시보드 서버(Superset)에 등록하는 일이
 * 끝났는지 관리자가 확인하고, 대기·실패 항목을 다시 등록하게 한다. 등록이 실패해도 입력·수식 저장은 막히지 않는다.
 * E2는 접수(202)만 하므로 결과는 목록을 다시 읽어 확인한다. 대기 항목이 있으면 5초마다 최대 2분간 다시 읽는다.
 */
export function SupersetSyncSection() {
  const [reloadKey, setReloadKey] = useState(0);
  const [polls, setPolls] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [offset, setOffset] = useState(0);
  const [requesting, setRequesting] = useState(false);
  const [outcome, setOutcome] = useState<{ accepted?: number; error?: unknown } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    listAllSupersetDatasets(controller.signal)
      .then((items) => !controller.signal.aborted && setLoaded({ items }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded((previous) => ({ items: previous?.items, error })));
    return () => controller.abort();
  }, [reloadKey]);

  const items = loaded?.items;
  const pendingCount = items?.filter((item) => item.sync_status === "pending").length ?? 0;

  // 대기 항목이 있는 동안만 다시 읽는다. 없어지거나 화면을 떠나면 멈춘다.
  useEffect(() => {
    if (pendingCount === 0 || polls >= MAX_POLLS) return;
    const timer = setTimeout(() => {
      setPolls((value) => value + 1);
      setReloadKey((value) => value + 1);
    }, POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [pendingCount, polls, reloadKey]);

  const reloadNow = useCallback(() => {
    setPolls(0);
    setReloadKey((value) => value + 1);
  }, []);

  const request = useCallback(
    async (ids: number[] | "all") => {
      setRequesting(true);
      setOutcome(null);
      try {
        const accepted = await requestSupersetSync(ids === "all" ? undefined : ids);
        setOutcome({ accepted: accepted.length });
      } catch (error) {
        setOutcome({ error });
      } finally {
        setRequesting(false);
        reloadNow();
      }
    },
    [reloadNow],
  );

  const counts = useMemo(() => {
    const result: Record<SyncStatus, number> = { pending: 0, registered: 0, failed: 0 };
    for (const item of items ?? []) result[item.sync_status] += 1;
    return result;
  }, [items]);

  const visible = useMemo(() => (items ?? []).filter((item) => filter === "all" || item.sync_status === filter), [items, filter]);
  const pageItems = visible.slice(offset, offset + PAGE_SIZE);
  const redoable = counts.pending + counts.failed;
  const gaveUp = pendingCount > 0 && polls >= MAX_POLLS;

  return (
    <section aria-label="Superset 동기" className="panel status-sync" data-testid="sync-section">
      <h2>Superset 동기 (대시보드 서버에 데이터셋 등록)</h2>
      <p className="muted">
        포털의 데이터셋을 차트 작성용 대시보드 서버(Superset)에 등록한 상태입니다. 등록이 늦거나 실패해도 데이터 입력과 수식 저장은 계속 쓸 수 있고, 차트 작성에서만 해당 데이터셋이 보이지 않을 수 있습니다.
      </p>
      {loaded === null ? <Loading label="동기 상태를 불러오는 중" /> : null}
      {loaded?.error !== undefined ? (
        <ErrorNotice error={loaded.error}>
          <button type="button" onClick={reloadNow}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {outcome?.error !== undefined ? (
        <ErrorNotice error={outcome.error}>
          <button type="button" onClick={() => void request("all")} disabled={requesting}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}
      {outcome?.accepted !== undefined ? (
        <p role="status" className="state state-ok" data-testid="sync-accepted">
          {outcome.accepted}개를 다시 등록하도록 접수했습니다. 결과는 아래 목록에서 확인하세요(대기 중이면 자동으로 다시 읽습니다).
        </p>
      ) : null}
      {gaveUp ? (
        <p role="status" className="muted" data-testid="sync-poll-stopped">
          자동으로 다시 읽기를 멈췄습니다. 대기가 길어지면 대시보드 서버(Superset) 상태를 확인하세요.{" "}
          <button type="button" className="link" onClick={reloadNow}>
            지금 다시 읽기
          </button>
        </p>
      ) : null}
      {items ? (
        <>
          <p data-testid="sync-summary">
            전체 {items.length.toLocaleString("en-US")}개 중 등록됨 <strong>{counts.registered.toLocaleString("en-US")}</strong>개, 등록 대기{" "}
            <strong>{counts.pending.toLocaleString("en-US")}</strong>개, 등록 실패 <strong>{counts.failed.toLocaleString("en-US")}</strong>개
          </p>
          <div className="toolbar">
            <label>
              상태 필터
              <select
                value={filter}
                onChange={(event) => {
                  setOffset(0);
                  setFilter(event.target.value as StatusFilter);
                }}
              >
                <option value="all">전체</option>
                <option value="pending">{SYNC_LABELS.pending}</option>
                <option value="failed">{SYNC_LABELS.failed}</option>
                <option value="registered">{SYNC_LABELS.registered}</option>
              </select>
            </label>
            <button type="button" disabled={requesting || redoable === 0} onClick={() => void request("all")}>
              {requesting ? "접수하는 중…" : `대기·실패 전부 다시 동기 (${redoable}개)`}
            </button>
            <button type="button" onClick={reloadNow}>
              새로 읽기
            </button>
          </div>
          {visible.length === 0 ? (
            <p className="muted" data-testid="no-sync-items">
              {items.length === 0 ? "등록할 데이터셋이 없습니다." : "이 상태의 데이터셋이 없습니다."}
            </p>
          ) : (
            <div className="table-scroll" data-testid="sync-table-scroll">
            <table aria-label="Superset 동기 목록" className="list-table sync-table">
              <thead>
                <tr>
                  <th scope="col">데이터셋 (Superset에서의 이름)</th>
                  <th scope="col">상태</th>
                  <th scope="col">마지막 등록</th>
                  <th scope="col">실패 사유</th>
                  <th scope="col">
                    <span className="visually-hidden">동작</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {pageItems.map((item) => (
                  <tr key={item.dataset_id}>
                    <td className="sync-name">
                      <Link to={`/datasets/${item.dataset_id}`}>{item.superset_name || `데이터셋 ${item.dataset_id}`}</Link>
                    </td>
                    <td>
                      <SyncBadge status={item.sync_status} />
                    </td>
                    <td>{formatMinute(item.synced_at)}</td>
                    <td className="sync-error">{item.last_error ?? ""}</td>
                    <td>
                      {item.sync_status !== "registered" ? (
                        <button type="button" disabled={requesting} onClick={() => void request([item.dataset_id])}>
                          다시 동기
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
          {visible.length > PAGE_SIZE ? (
            <div className="pager">
              <span>
                {visible.length}개 중 {offset + 1}–{Math.min(offset + PAGE_SIZE, visible.length)}
              </span>
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                이전
              </button>
              <button type="button" disabled={offset + PAGE_SIZE >= visible.length} onClick={() => setOffset(offset + PAGE_SIZE)}>
                다음
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
