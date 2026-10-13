import { useMe } from "../access/MeContext";
import { SupersetSyncSection } from "./SupersetSyncSection";
import { ViewsSection } from "./ViewsSection";

/** S9 관리자 현황. 관리자만 쓴다(서버 권한이 최종 방어선). Superset 동기 구역(1e)과 뷰 재생성 구역(1d)을 나란히 둔다. */
export function AdminStatusPage() {
  const { state } = useMe();
  if (state.status !== "ready") return null;
  if (!state.me.is_admin) {
    return (
      <section data-testid="screen-S9">
        <h1>S9 관리자 현황</h1>
        <p role="alert" className="state state-error">
          관리자만 사용할 수 있는 화면입니다.
        </p>
      </section>
    );
  }
  return (
    <section data-testid="screen-S9" className="console">
      <h1>S9 관리자 현황</h1>
      <div className="status-grid">
        <SupersetSyncSection />
        <ViewsSection />
      </div>
    </section>
  );
}
