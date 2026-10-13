import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { getViewsStatus, retryViews } from "../formula/api";
import type { ViewsRetryResult, ViewsStatus } from "../formula/types";

type Loaded = { key: number; status?: ViewsStatus; error?: unknown } | null;
type Retrying = null | { ids: number[] | "all" };

/** 시각 ISO 8601에서 날짜와 분까지만 보여 준다(서버가 한국 시간으로 준다, 05 §1). */
const formatSince = (iso: string | null | undefined): string => (typeof iso === "string" && iso.length >= 16 ? iso.slice(0, 16).replace("T", " ") : (iso ?? ""));

/**
 * S9 '뷰 재생성' 구역(D9 현황, D10 다시 시도). 수식 계산에 쓰는 데이터 구조(뷰)를 만들지 못한 데이터셋을 관리자가 확인하고 다시 만든다.
 * 같은 숫자가 /health 본문의 views·views_failed_count에도 있다. 실패 상세는 서버 메모리에만 있어 서버를 다시 시작하면 사라진다(07 §8).
 */
export function ViewsSection() {
  const [reloadKey, setReloadKey] = useState(0);
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [retrying, setRetrying] = useState<Retrying>(null);
  const [outcome, setOutcome] = useState<{ result?: ViewsRetryResult; error?: unknown } | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getViewsStatus(controller.signal)
      .then((status) => !controller.signal.aborted && setLoaded({ key: reloadKey, status }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key: reloadKey, error }));
    return () => controller.abort();
  }, [reloadKey]);

  const retry = useCallback(async (ids: number[] | "all") => {
    setRetrying({ ids });
    setOutcome(null);
    try {
      const result = await retryViews(ids === "all" ? {} : { dataset_ids: ids });
      setOutcome({ result });
    } catch (error) {
      setOutcome({ error });
    } finally {
      setRetrying(null);
      setReloadKey((value) => value + 1);
    }
  }, []);

  const loading = loaded?.key !== reloadKey;
  const status = loaded?.status;
  const busy = retrying !== null;

  return (
    <section aria-label="뷰 재생성" className="panel status-views">
      <h2>뷰 재생성 (수식 계산용 데이터 구조)</h2>
      <p className="muted">
        수식 계산에 쓰는 데이터 구조(뷰)를 만들지 못한 데이터셋을 보여 줍니다. 만들지 못해도 다른 기능은 계속 동작하며, 해당 데이터셋의 계산 열 값만 보이지 않을 수 있습니다.
      </p>
      {loading && !status ? <Loading label="뷰 현황을 불러오는 중" /> : null}
      {loaded?.key === reloadKey && loaded.error !== undefined ? (
        <ErrorNotice error={loaded.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {outcome?.error !== undefined ? (
        <ErrorNotice error={outcome.error}>
          <button type="button" onClick={() => void retry("all")} disabled={busy}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}
      {outcome?.result ? (
        <p role="status" className={outcome.result.views_failed_count > 0 ? "state state-error" : "state state-ok"} data-testid="views-retry-result">
          {outcome.result.rebuilt}개를 다시 만들었습니다.{" "}
          {outcome.result.views_failed_count > 0
            ? `아직 ${outcome.result.views_failed_count}개가 실패 상태입니다. 사유를 확인해 주세요.`
            : "실패한 항목이 더 없습니다."}
        </p>
      ) : null}
      {status ? (
        <>
          <p data-testid="views-summary">
            확인한 데이터셋 {status.views.toLocaleString("en-US")}개 중 실패 <strong>{status.views_failed_count.toLocaleString("en-US")}개</strong>
          </p>
          {status.failed.length === 0 ? (
            <p className="muted" data-testid="no-failed-views">
              뷰를 만들지 못한 데이터셋이 없습니다.
            </p>
          ) : (
            <>
              <table aria-label="뷰 재생성 실패 목록" className="list-table">
                <thead>
                  <tr>
                    <th scope="col">데이터셋</th>
                    <th scope="col">사유</th>
                    <th scope="col">실패한 시각</th>
                    <th scope="col">
                      <span className="visually-hidden">동작</span>
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {status.failed.map((item) => (
                    <tr key={item.dataset_id}>
                      <td>
                        <Link to={`/datasets/${item.dataset_id}`}>{item.dataset_name}</Link>
                      </td>
                      <td>{item.reason}</td>
                      <td>{formatSince(item.since)}</td>
                      <td>
                        <button type="button" disabled={busy} onClick={() => void retry([item.dataset_id])}>
                          이 데이터셋 다시 시도
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="actions">
                <button type="button" className="primary" disabled={busy} onClick={() => void retry("all")}>
                  {busy ? "다시 만드는 중…" : "실패한 항목 전부 다시 시도"}
                </button>
              </div>
            </>
          )}
        </>
      ) : null}
    </section>
  );
}
