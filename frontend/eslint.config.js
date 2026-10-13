import js from "@eslint/js";
import { defineConfig, globalIgnores } from "eslint/config";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default defineConfig([
  globalIgnores(["dist", "coverage"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, tseslint.configs.recommended, reactHooks.configs.flat.recommended],
    languageOptions: {
      ecmaVersion: 2023,
      globals: globals.browser,
    },
  },
  {
    // 대시보드 임베드(입장권 guest token을 다루는 곳)에서는 저장소·콘솔 사용을 막는다. 토큰은 메모리 변수에만 둔다.
    files: ["src/features/dashboard/**/*.{ts,tsx}"],
    ignores: ["src/features/dashboard/**/*.test.{ts,tsx}"],
    rules: {
      "no-console": "error",
      "no-restricted-globals": [
        "error",
        { name: "localStorage", message: "입장권은 저장소에 두지 않는다." },
        { name: "sessionStorage", message: "입장권은 저장소에 두지 않는다." },
      ],
      "no-restricted-properties": [
        "error",
        { object: "window", property: "localStorage", message: "입장권은 저장소에 두지 않는다." },
        { object: "window", property: "sessionStorage", message: "입장권은 저장소에 두지 않는다." },
        { object: "document", property: "cookie", message: "입장권은 쿠키에 두지 않는다." },
      ],
    },
  },
]);
