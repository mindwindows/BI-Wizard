import { NavLink, Outlet, useRouteError } from "react-router-dom";
import { ErrorNotice, Loading } from "./components";
import { AccessDenied } from "./features/access/AccessDenied";
import { MeProvider, useMe } from "./features/access/MeContext";
import { StubSwitcher } from "./features/access/StubSwitcher";
import { WorkTeamSelect } from "./features/access/WorkTeamSelect";

const MAIN_LINKS = [
  { to: "/", label: "홈", end: true },
  { to: "/datasets", label: "데이터셋", end: false },
  { to: "/checks", label: "점검", end: false },
  { to: "/dashboards", label: "대시보드", end: false },
  { to: "/reference-values", label: "기준값", end: false },
];

const ADMIN_LINKS = [
  { to: "/admin/permissions", label: "권한 관리" },
  { to: "/admin/dashboards", label: "대시보드 연결" },
  { to: "/admin/status", label: "현황" },
  { to: "/admin/audit", label: "감사 기록" },
];

function ShellFrame() {
  const { state, refresh } = useMe();
  const ready = state.status === "ready";
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">BI-Wizard</span>
        {ready ? (
          <nav aria-label="주 메뉴" className="nav">
            {MAIN_LINKS.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end}>
                {link.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
        <WorkTeamSelect />
        <span className="topbar-right">
          <StubSwitcher />
          {ready ? <span className="who">{state.me.display_name}</span> : null}
          {/*
            관리 메뉴(S6·S8·S9·S10)는 편의상 관리자에게만 보여 준다. 숨김은 보안 경계가 아니다.
            최종 방어선은 서버의 권한 검사(관리자 전용 API가 403 FORBIDDEN)이며 화면도 직접 접속 때 다시 막는다.
          */}
          {ready && state.me.is_admin ? (
            <nav aria-label="관리 메뉴" className="nav nav-admin">
              {ADMIN_LINKS.map((link) => (
                <NavLink key={link.to} to={link.to}>
                  {link.label}
                </NavLink>
              ))}
            </nav>
          ) : null}
        </span>
      </header>
      {/* key: 신원이 바뀌면(스텁 전환) 화면 상태를 새로 시작한다. */}
      <main className="content" key={state.status === "ready" ? `u${state.me.id}` : state.status}>
        {state.status === "loading" ? <Loading label="사용자 정보를 확인하는 중" /> : null}
        {state.status === "denied" ? <AccessDenied /> : null}
        {state.status === "error" ? (
          <ErrorNotice error={state.error}>
            <button type="button" onClick={refresh}>
              다시 시도
            </button>
          </ErrorNotice>
        ) : null}
        {ready ? <Outlet /> : null}
      </main>
    </div>
  );
}

/** S1 포털 셸: 상단 Navigation + 작업 팀 선택 + 본문. 1920x1080 기준 전체 폭을 쓴다. */
export function Shell() {
  return (
    <MeProvider>
      <ShellFrame />
    </MeProvider>
  );
}

/** 라우트 렌더 중 예외가 났을 때 셸 안에서 보여 주는 오류 화면. */
export function RouteError() {
  const error = useRouteError();
  return (
    <div className="content">
      <ErrorNotice error={error} />
    </div>
  );
}
