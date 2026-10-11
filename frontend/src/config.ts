/** 런타임 공개 설정. 컨테이너 시작 때 생성되는 config.js(window.__APP_CONFIG__)에서 읽는다. */
export interface AppConfig {
  /** 포털의 하위 경로(APP_BASE_PATH). 루트 배포는 빈 문자열. */
  basePath: string;
  /** Superset의 하위 경로(SUPERSET_APP_ROOT). 루트 배포는 빈 문자열. */
  supersetRoot: string;
}

declare global {
  interface Window {
    __APP_CONFIG__?: Partial<AppConfig>;
  }
}

// API 경로는 ${basePath}/api 이다. 호스트는 붙이지 않는다(상대경로 + 프록시).
const API_SEGMENT = "/api";

const SEGMENT = /^[A-Za-z0-9._~-]+$/;

/**
 * 하위 경로 형식: 빈 값이거나 앞 "/" 필수, 뒤 "/" 금지, "//" 금지, 세그먼트는 허용 문자만,
 * "."와 ".." 세그먼트 금지. 규칙은 backend/app/config.py, nginx 시작 스크립트와 같다.
 * 형식이 틀리면 빈 값(루트)으로 본다.
 */
export function normalizePath(value: string | undefined): string {
  if (value === undefined || value === "") return "";
  if (!value.startsWith("/")) return "";
  const segments = value.slice(1).split("/");
  const valid = segments.every((segment) => SEGMENT.test(segment) && segment !== "." && segment !== "..");
  return valid ? value : "";
}

export function getConfig(): AppConfig {
  const raw = window.__APP_CONFIG__ ?? {};
  return {
    basePath: normalizePath(raw.basePath),
    supersetRoot: normalizePath(raw.supersetRoot),
  };
}

/** `${basePath}/api/...` 형태의 호스트 없는 상대경로를 만든다. */
export function apiUrl(path: string, basePath: string = getConfig().basePath): string {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  return `${basePath}${API_SEGMENT}${suffix}`;
}
