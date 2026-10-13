import { Link } from "react-router-dom";
import { useMe, type DenyReason } from "./MeContext";

const GUIDE: Record<DenyReason, string> = {
  UNAUTHENTICATED: "로그인 정보를 확인하지 못했습니다. 회사 계정으로 접속했는지 확인한 뒤 다시 시도해 주세요.",
  USER_NOT_REGISTERED:
    "아직 이 포털에 등록되지 않은 사용자입니다. 관리자에게 사용자 등록을 요청해 주세요.",
  USER_INACTIVE: "사용이 중지된 계정입니다. 다시 사용해야 한다면 관리자에게 문의해 주세요.",
};

/** S1 접근 안내. /me가 401·403(미등록·비활성)일 때 셸 본문 전체를 대신한다. */
export function AccessDenied() {
  const { state, refresh } = useMe();
  const reason = state.status === "denied" ? state.reason : null;
  return (
    <section data-testid="screen-S1" className="access-denied">
      <h1>접근 권한이 없습니다</h1>
      {reason ? (
        <p data-testid="access-denied-guide">{GUIDE[reason]}</p>
      ) : (
        <p className="muted">현재 계정은 포털을 사용할 수 있습니다. <Link to="/">처음 화면으로 이동</Link></p>
      )}
      {reason ? (
        <p>
          <button type="button" onClick={refresh}>
            다시 확인
          </button>
        </p>
      ) : null}
    </section>
  );
}
