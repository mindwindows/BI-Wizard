import { describe, expect, it } from "vitest";

/**
 * 비밀·저장소 정적 검사(단위 1e, 03b 21-3 조건).
 * 1) 소스 검사는 항상 돈다.
 * 2) 빌드 산출물(dist/) 검사는 `npm run build`가 만든 dist/가 있을 때만 돈다. 없으면 건너뛴다.
 *    QA는 빌드 뒤 `npx vitest run src/static-checks.test.ts`를 돌려 건너뛴 항목이 0인지 확인한다.
 */
const sources = import.meta.glob("./**/*.{ts,tsx}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const dist = import.meta.glob("../dist/**/*.{js,css,html}", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const publicConfig = import.meta.glob("../public/config.js", { query: "?raw", import: "default", eager: true }) as Record<string, string>;
const packageJson = import.meta.glob("../package.json", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const isTest = (path: string) => /\.test\.(ts|tsx)$/.test(path) || /\/test-(utils|server)\.ts$/.test(path);
const appSources = Object.entries(sources).filter(([path]) => !isTest(path));

/** 줄 주석과 블록 주석을 지운다(문자열 안의 // 는 앞이 공백·줄 시작일 때만 주석으로 본다). */
const stripComments = (code: string) => code.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|\s)\/\/.*$/gm, "$1");

const SECRET_NAMES = ["SUPERSET_ADMIN", "SUPERSET_SERVICE", "SUPERSET_GUEST_ISSUER", "SECRET_KEY", "GUEST_TOKEN_JWT_SECRET", "PASSWORD"];

describe("소스 정적 검사", () => {
  it("검사 대상 소스를 찾았다(glob이 비어 있으면 아래 검사가 무의미하다)", () => {
    expect(appSources.length).toBeGreaterThan(30);
    expect(appSources.some(([path]) => path === "./features/dashboard/DashboardEmbed.tsx")).toBe(true);
  });

  it("Superset 계정·SECRET_KEY·토큰 발급 자격·비밀번호 이름이 프런트 소스에 없다", () => {
    const hits: string[] = [];
    for (const [path, code] of appSources) for (const name of SECRET_NAMES) if (code.includes(name)) hits.push(`${path}: ${name}`);
    expect(hits).toEqual([]);
  });

  it("환경변수를 번들에 넣는 import.meta.env / VITE_ 사용이 없다", () => {
    const hits = appSources.filter(([, code]) => /import\.meta\.env|VITE_/.test(code)).map(([path]) => path);
    expect(hits).toEqual([]);
  });

  it("localStorage와 document.cookie를 쓰는 소스가 없다", () => {
    const hits = appSources.filter(([, code]) => /\blocalStorage\b|document\.cookie|\bindexedDB\b/.test(stripComments(code))).map(([path]) => path);
    expect(hits).toEqual([]);
  });

  it("sessionStorage는 기존 작업 팀 키(MeContext) 한 곳에서만 쓰고 새 사용이 없다", () => {
    const hits = appSources.filter(([, code]) => /\bsessionStorage\b/.test(stripComments(code))).map(([path]) => path);
    expect(hits).toEqual(["./features/access/MeContext.tsx"]);
    const code = stripComments(sources["./features/access/MeContext.tsx"]);
    const calls = code.match(/sessionStorage\.\w+\(([^)]*)\)/g) ?? [];
    expect(calls.length).toBeGreaterThan(0);
    // 저장하는 키는 작업 팀 번호 하나다.
    for (const call of calls) expect(call).toContain("WORK_TEAM_STORAGE_KEY");
  });

  it("대시보드 임베드 소스(features/dashboard)에는 저장소·쿠키·콘솔·주소 이력 조작이 없다", () => {
    const own = appSources.filter(([path]) => path.startsWith("./features/dashboard/"));
    expect(own.length).toBeGreaterThanOrEqual(5);
    const hits: string[] = [];
    for (const [path, code] of own) {
      const body = stripComments(code);
      if (/\b(localStorage|sessionStorage)\b|document\.cookie|\bconsole\.|history\.(push|replace)State|window\.name|sendBeacon|postMessage/.test(body)) hits.push(path);
    }
    expect(hits).toEqual([]);
  });

  it("입장권 요청 함수는 요청 후 응답 객체를 보관하지 않는다(모듈 수준 let/var 없음)", () => {
    const code = stripComments(sources["./features/dashboard/guestToken.ts"]);
    expect(code).not.toMatch(/^(let|var)\s/m);
    expect(code).toContain('cache: "no-store"');
  });

  it("공개 설정 config.js는 basePath와 supersetRoot만 가진다", () => {
    const text = Object.values(publicConfig)[0];
    expect(text).toBeDefined();
    const keys = [...text.matchAll(/(\w+)\s*:/g)].map((match) => match[1]).sort();
    expect(keys).toEqual(["basePath", "supersetRoot"]);
    for (const name of SECRET_NAMES) expect(text).not.toContain(name);
  });

  it("config.ts의 공개 설정 필드도 둘뿐이다", () => {
    const code = stripComments(sources["./config.ts"]);
    const body = /export interface AppConfig \{([\s\S]*?)\n\}/.exec(code)?.[1] ?? "";
    expect([...body.matchAll(/(\w+)\s*:/g)].map((match) => match[1])).toEqual(["basePath", "supersetRoot"]);
  });
});

describe("패키지 정적 검사", () => {
  const pkg = JSON.parse(Object.values(packageJson)[0]) as { dependencies: Record<string, string>; devDependencies: Record<string, string> };

  it("Embedded SDK는 승인된 0.4.0 정확한 고정 표기이고 Enterprise 패키지는 없다", () => {
    expect(pkg.dependencies["@superset-ui/embedded-sdk"]).toBe("0.4.0");
    const all = { ...pkg.dependencies, ...pkg.devDependencies };
    for (const [name, version] of Object.entries(all)) {
      expect(version, name).toMatch(/^\d+\.\d+\.\d+$/);
      expect(name).not.toMatch(/enterprise/i);
    }
  });
});

describe.skipIf(Object.keys(dist).length === 0)("빌드 산출물(dist/) 검사 - npm run build 뒤에만 실행", () => {
  const files = Object.entries(dist);

  it("번들에 Superset 계정·SECRET_KEY·토큰 발급 자격·비밀번호 문자열이 0건이다", () => {
    expect(files.some(([path]) => path.endsWith(".js"))).toBe(true);
    const hits: string[] = [];
    for (const [path, text] of files) for (const name of SECRET_NAMES) if (text.includes(name)) hits.push(`${path}: ${name}`);
    expect(hits).toEqual([]);
  });

  it("Embedded SDK가 번들에 들어 있고 입장권 저장 흔적(localStorage, document.cookie)이 없다", () => {
    const js = files.filter(([path]) => path.endsWith(".js")).map(([, text]) => text).join("\n");
    expect(js).toContain("__embedded_comms__");
    expect(js).not.toMatch(/localStorage|document\.cookie|indexedDB/);
  });

  it("계정 이름(bi_service, bi_guest_issuer)과 JWT 머리 형태(eyJ…)가 번들에 없다", () => {
    const js = files.map(([, text]) => text).join("\n");
    expect(js).not.toMatch(/bi_service|bi_guest_issuer/);
    expect(js).not.toMatch(/eyJ[A-Za-z0-9_-]{8,}\./);
  });
});
