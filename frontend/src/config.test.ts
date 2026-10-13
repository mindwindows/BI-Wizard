import { afterEach, describe, expect, it } from "vitest";
import { apiUrl, getConfig, hasSuperset, normalizePath, supersetDomain, supersetLink } from "./config";

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
    expect(normalizePath("/")).toBe("");
    expect(normalizePath("/a\n/b")).toBe("");
    expect(normalizePath("/a\n")).toBe("");
    expect(normalizePath("/..")).toBe("");
    expect(normalizePath("/a/../b")).toBe("");
    expect(normalizePath("/a/./b")).toBe("");
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

describe("supersetDomain / supersetLink / hasSuperset", () => {
  it("origin + 하위 경로로 조립하고 끝에 /를 붙이지 않는다", () => {
    expect(supersetDomain("/bi-wizard/superset", "http://127.0.0.1:5173")).toBe("http://127.0.0.1:5173/bi-wizard/superset");
    expect(supersetDomain("/superset", "https://bi.example.com")).toBe("https://bi.example.com/superset");
  });

  it("기본값은 config.js의 supersetRoot와 현재 페이지 origin을 쓴다", () => {
    window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
    expect(supersetDomain()).toBe(`${window.location.origin}/bi-wizard/superset`);
    expect(supersetLink("/")).toBe("/bi-wizard/superset/");
    expect(supersetLink("")).toBe("/bi-wizard/superset/");
    expect(supersetLink("/chart/add")).toBe("/bi-wizard/superset/chart/add");
    expect(hasSuperset()).toBe(true);
  });

  it("supersetRoot가 비었으면 설정이 없는 것으로 본다", () => {
    window.__APP_CONFIG__ = { basePath: "", supersetRoot: "" };
    expect(hasSuperset()).toBe(false);
    window.__APP_CONFIG__ = { basePath: "", supersetRoot: "/a b" };
    expect(hasSuperset()).toBe(false);
  });

  it("포털 하위 경로 유무와 상관없이 Superset 주소는 supersetRoot만으로 정해진다(STRIP true/false 동일)", () => {
    window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "/bi-wizard/superset" };
    const withBase = supersetDomain();
    window.__APP_CONFIG__ = { basePath: "", supersetRoot: "/bi-wizard/superset" };
    expect(supersetDomain()).toBe(withBase);
  });
});
