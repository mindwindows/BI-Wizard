import { NavLink, Outlet, useRouteError } from "react-router-dom";
import { ErrorNotice } from "./components";

const MAIN_LINKS = [
  { to: "/", label: "홈", end: true },
  { to: "/datasets", label: "데이터셋", end: false },
  { to: "/checks", label: "점검", end: false },
  { to: "/dashboards", label: "대시보드", end: false },
];

// 관리자 화면. 역할별 표시/숨김은 단위 1a(/api/me)에서 적용한다. 지금은 모두 보인다.
const ADMIN_LINKS = [
  { to: "/admin/permissions", label: "권한 관리" },
  { to: "/admin/dashboards", label: "대시보드 연결" },
  { to: "/admin/status", label: "현황" },
];

/** S1 포털 셸: 상단 Navigation + 본문. 1920x1080 기준 전체 폭을 쓴다. */
export function Shell() {
  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">BI-Wizard</span>
        <nav aria-label="주 메뉴" className="nav">
          {MAIN_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to} end={link.end}>
              {link.label}
            </NavLink>
          ))}
        </nav>
        <nav aria-label="관리 메뉴" className="nav nav-admin">
          {ADMIN_LINKS.map((link) => (
            <NavLink key={link.to} to={link.to}>
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="content">
        <Outlet />
      </main>
    </div>
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
