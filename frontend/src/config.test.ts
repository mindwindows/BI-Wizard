import { afterEach, describe, expect, it } from "vitest";
import { apiUrl, getConfig, normalizePath } from "./config";

afterEach(() => {
  delete window.__APP_CONFIG__;
});

describe("normalizePath", () => {
  it("빈 값과 올바른 경로는 그대로 둔다", () => {
    expect(normalizePath(undefined)).toBe("");
    expect(normalizePath("")).toBe("");
    expect(normalizePath("/bi-wizard")).toBe("/bi-wizard");
    expect(normalizePath("/bi-wizard/superset")).toBe("/bi-wizard/superset");
  });

  it("형식이 틀리면 빈 값으로 본다", () => {
    expect(normalizePath("/bi-wizard/")).toBe("");
    expect(normalizePath("bi-wizard")).toBe("");
    expect(normalizePath("//evil.example")).toBe("");
    expect(normalizePath("/a b")).toBe("");
  });
});

describe("apiUrl", () => {
  it("하위 경로 아래의 호스트 없는 상대경로를 만든다", () => {
    expect(apiUrl("/health", "/bi-wizard")).toBe("/bi-wizard/api/health");
    expect(apiUrl("health/db", "/bi-wizard")).toBe("/bi-wizard/api/health/db");
  });

  it("루트 배포에서는 접두가 없다", () => {
    expect(apiUrl("/health", "")).toBe("/api/health");
  });

  it("window.__APP_CONFIG__의 basePath를 쓴다", () => {
    window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
    expect(getConfig()).toEqual({ basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" });
    expect(apiUrl("/health")).toBe("/bi-wizard/api/health");
    expect(apiUrl("/health")).not.toMatch(/^https?:/);
  });
});
