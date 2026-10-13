import { useEffect, useId, useState } from "react";
import { clearStubUser, getStubUsers, setStubUser } from "./api";
import { describeApiError } from "../../errors";
import { useMe } from "./MeContext";
import type { StubUsers } from "./types";

/**
 * 개발·시험 전용 스텁 신원 전환기(S1). GET /dev/stub-users가 200일 때만 보이고 404(운영 설정)면 아무것도 그리지 않는다.
 * 스텁은 서버가 켠 환경에서만 존재하므로 프런트는 응답 여부만 본다(config.js·환경변수 추가 없음).
 */
export function StubSwitcher() {
  const { refresh } = useMe();
  const id = useId();
  const [stub, setStub] = useState<StubUsers | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void getStubUsers().then((result) => {
      if (active) setStub(result);
    });
    return () => {
      active = false;
    };
  }, []);

  if (!stub) return null;

  async function change(loginId: string) {
    setError(null);
    try {
      if (loginId === "") await clearStubUser();
      else await setStubUser(loginId);
      setStub((previous) => (previous ? { ...previous, current: loginId === "" ? null : loginId } : previous));
      refresh();
    } catch (cause) {
      setError(describeApiError(cause));
    }
  }

  return (
    <span className="stub-switcher" data-testid="stub-switcher">
      <label htmlFor={id}>개발용 신원</label>
      <select id={id} value={stub.current ?? ""} onChange={(event) => void change(event.target.value)}>
        <option value="">(선택 안 함)</option>
        {/* 쿠키 값이 등록 사용자 목록에 없으면(미등록 로그인 ID) 선택 안 함으로 오해하지 않게 따로 보여 준다. */}
        {stub.current && !stub.items.some((item) => item.login_id === stub.current) ? (
          <option value={stub.current}>(미등록) {stub.current}</option>
        ) : null}
        {stub.items.map((item) => (
          <option key={item.login_id} value={item.login_id}>
            {item.display_name} ({item.login_id}){item.is_admin ? " - 관리자" : ""}
          </option>
        ))}
      </select>
      {error ? (
        <span role="alert" className="stub-error">
          {error}
        </span>
      ) : null}
    </span>
  );
}
