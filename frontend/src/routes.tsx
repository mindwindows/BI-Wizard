import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";
import { getConfig } from "./config";
import { Home } from "./pages/Home";
import { Placeholder } from "./pages/Placeholder";
import { RouteError, Shell } from "./Shell";

function NotFound() {
  return (
    <section data-testid="screen-not-found">
      <h1>페이지를 찾을 수 없습니다</h1>
      <p className="muted">주소를 확인해 주세요.</p>
    </section>
  );
}

/** 라우트 경로는 basename 아래 기준이다(basePath는 라우터가 붙인다). */
export const routes: RouteObject[] = [
  {
    path: "/",
    element: <Shell />,
    errorElement: <RouteError />,
    children: [
      { index: true, element: <Home /> },
      // S1 접근 안내("접근 권한이 없습니다")는 단위 1a에서 /api/me와 함께 채운다.
      { path: "access-denied", element: <Placeholder screen="S1" title="접근 안내" unit="단위 1a" /> },
      { path: "datasets", element: <Placeholder screen="S2" title="데이터셋 목록" unit="단위 1b" /> },
      { path: "datasets/new", element: <Placeholder screen="S3" title="데이터셋 만들기" unit="단위 1b" /> },
      { path: "datasets/:datasetId", element: <Placeholder screen="S4" title="작업공간" unit="단위 1b~1d" /> },
      { path: "checks", element: <Placeholder screen="S5" title="점검" unit="단위 1d" /> },
      { path: "admin/permissions", element: <Placeholder screen="S6" title="권한 관리" unit="단위 1a" /> },
      { path: "dashboards", element: <Placeholder screen="S7" title="대시보드" unit="단위 1e" /> },
      { path: "admin/dashboards", element: <Placeholder screen="S8" title="대시보드 연결 관리" unit="단위 1e" /> },
      { path: "admin/status", element: <Placeholder screen="S9" title="관리자 현황" unit="단위 1e" /> },
      { path: "*", element: <NotFound /> },
    ],
  },
];

/** react-router의 basename. 루트 배포(빈 basePath)는 "/"다. */
export function routerBasename(basePath: string): string {
  return basePath === "" ? "/" : basePath;
}

/** 실제 브라우저용 라우터. basePath는 config.js(window.__APP_CONFIG__)에서 온다. */
export function createAppRouter() {
  return createBrowserRouter(routes, { basename: routerBasename(getConfig().basePath) });
}

/** 시험용: 주소를 직접 지정하는 메모리 라우터. */
export function createTestRouter(basePath: string, initialEntry: string) {
  return createMemoryRouter(routes, {
    basename: routerBasename(basePath),
    initialEntries: [initialEntry],
  });
}
