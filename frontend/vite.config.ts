import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// base를 './'로 두어 빌드 결과가 경로와 무관하게 재사용되게 한다.
// 실제 하위 경로(APP_BASE_PATH)는 컨테이너 시작 때 index.html의 <base href>와 config.js로 주입한다.
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: {
    host: true,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    // 레이아웃 시험(src/layout.test.ts)이 styles.css 원문을 읽을 수 있게 이 파일만 처리한다.
    css: { include: [/src\/styles\.css/] },
    // CPU 부하에서 AG Grid 마운트·디바운스 시험이 기본 5초를 넘기므로 전역 제한을 늘린다(시험 실행에만 영향).
    testTimeout: 20000,
    hookTimeout: 20000,
  },
});
