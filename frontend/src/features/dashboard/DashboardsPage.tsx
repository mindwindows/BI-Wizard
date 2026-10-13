import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { hasSuperset, supersetLink } from "../../config";
import { listDashboards } from "./api";
import { AuthorGuide } from "./AuthorGuide";
import { DashboardEmbed } from "./DashboardEmbed";
import type { DashboardList } from "./types";

interface Loaded {
  key: number;
  list?: DashboardList;
  error?: unknown;
}

/**
 * S7 대시보드 목록·보기. 선택은 주소의 `?d=<포털 번호>`로 기억한다(임베드 번호·입장권은 주소에 두지 않는다).
 * 서버 권한이 최종 방어선이다(E6가 활성 여부와 로그인을 확인한다).
 */
export function DashboardsPage() {
  const [params, setParams] = useSearchParams();
  const [reloadKey, setReloadKey] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const superset = hasSuperset();

  useEffect(() => {
    const controller = new AbortController();
    listDashboards({}, controller.signal)
      .then((list) => !controller.signal.aborted && setLoaded({ key: reloadKey, list }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key: reloadKey, error }));
    return () => controller.abort();
  }, [reloadKey]);

  const select = useCallback(
    (id: number) => {
      setParams({ d: String(id) }, { replace: true });
    },
    [setParams],
  );

  const loading = loaded?.key !== reloadKey;
  const items = (loaded?.list?.items ?? []).filter((item) => item.is_active);
  const selectedId = Number(params.get("d"));
  const selected = items.find((item) => item.id === selectedId);
  const truncated = (loaded?.list?.total ?? 0) > (loaded?.list?.items.length ?? 0);

  return (
    <section data-testid="screen-S7" className="console dashboards-page">
      <div className="screen-head">
        <h1>S7 대시보드</h1>
        {superset ? (
          <a className="button-link" href={supersetLink("/")} target="_blank" rel="noopener noreferrer">
            차트 만들기 (새 창)
          </a>
        ) : null}
      </div>
      {superset ? (
        <AuthorGuide />
      ) : (
        <p className="state state-error" role="status" data-testid="no-superset-root">
          대시보드 서버 주소가 설정되지 않아 대시보드를 열 수 없습니다. 관리자에게 문의해 주세요.
        </p>
      )}

      {loading ? <Loading label="대시보드 목록을 불러오는 중" /> : null}
      {!loading && loaded?.error !== undefined ? (
        <ErrorNotice error={loaded.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {!loading && loaded?.list ? (
        items.length === 0 ? (
          <p className="muted" data-testid="no-dashboards">
            연결된 대시보드가 없습니다. 차트를 만든 뒤 관리자에게 대시보드 연결을 요청하세요.
          </p>
        ) : (
          <div className="dashboards-layout">
            <nav aria-label="대시보드 목록" className="dashboard-list">
              <ul>
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={item.id === selected?.id ? "dashboard-item active" : "dashboard-item"}
                      aria-current={item.id === selected?.id ? "true" : undefined}
                      onClick={() => select(item.id)}
                    >
                      {item.name}
                    </button>
                  </li>
                ))}
              </ul>
              {truncated ? <p className="muted">일부만 표시됨(전체 {loaded.list.total.toLocaleString("en-US")}개 중 일부)</p> : null}
            </nav>
            <div className="dashboard-view">
              {selected && superset ? (
                <>
                  <h2>{selected.name}</h2>
                  <DashboardEmbed key={selected.id} dashboard={selected} />
                </>
              ) : (
                <p className="muted" data-testid="pick-dashboard">
                  {selected ? "" : "왼쪽 목록에서 대시보드를 고르세요."}
                </p>
              )}
            </div>
          </div>
        )
      ) : null}
    </section>
  );
}
