import { createBrowserRouter, createMemoryRouter, type RouteObject } from "react-router-dom";
import { getConfig } from "./config";
import { AccessDenied } from "./features/access/AccessDenied";
import { ChecksPage } from "./features/checks/ChecksPage";
import { PermissionsPage } from "./features/access/permissions/PermissionsPage";
import { DatasetCreatePage } from "./features/dataset/DatasetCreatePage";
import { DatasetListPage } from "./features/dataset/DatasetListPage";
import { AdminStatusPage } from "./features/status/AdminStatusPage";
import { WorkspacePage } from "./features/dataset/workspace/WorkspacePage";
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
      { path: "access-denied", element: <AccessDenied /> },
      { path: "datasets", element: <DatasetListPage /> },
      { path: "datasets/new", element: <DatasetCreatePage /> },
      { path: "datasets/:datasetId", element: <WorkspacePage /> },
      { path: "checks", element: <ChecksPage /> },
      { path: "admin/permissions", element: <PermissionsPage /> },
      { path: "dashboards", element: <Placeholder screen="S7" title="대시보드" unit="단위 1e" /> },
      { path: "admin/dashboards", element: <Placeholder screen="S8" title="대시보드 연결 관리" unit="단위 1e" /> },
      { path: "admin/status", element: <AdminStatusPage /> },
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
