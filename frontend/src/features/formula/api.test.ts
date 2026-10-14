import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { installFetch, json } from "../../test-utils";
import { checkFormula, getFunctions, getViewsStatus, listFormulaErrorSummaries, previewFormula } from "./api";
import { DEFAULT_CELL_ERRORS, cellErrorText, invalidErrorsOf, previewCell, retryAfterOf } from "./messages";
import { ApiError } from "../../api";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: "/bi-wizard", supersetRoot: "" };
});
afterEach(() => {
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

describe("수식 API 응답 읽기(05 §2-4)", () => {
  it("D1: 문자열이 아닌 signature·returns도 글자로 받고, 이름 없는 항목은 버린다", async () => {
    installFetch({
      "GET /formulas/functions": () =>
        json(200, { functions: [{ name: "IF", signature: { args: ["c", "a", "b"] }, returns: "같은 종류", help_ko: "고름", excel_diff: "" }, { signature: "x" }], cell_errors: { E1: "문구", E9: 3 } }),
    });
    const catalog = await getFunctions();
    expect(catalog.functions).toHaveLength(1);
    expect(catalog.functions[0].signature).toBe('{"args":["c","a","b"]}');
    expect(catalog.cell_errors).toEqual({ E1: "문구" });
  });

  it("D1: 형식이 다르면 오류", async () => {
    installFetch({ "GET /formulas/functions": () => json(200, { nope: 1 }) });
    await expect(getFunctions()).rejects.toBeInstanceOf(ApiError);
  });

  it("D2·D3: 모르는 필드는 무시하고 빠진 숫자는 0", async () => {
    installFetch({
      "POST /datasets/7/formulas/check": () => json(200, { ok: false, errors: [{ code: "X", message: "m", start: 2 }, { nope: true }] }),
      "POST /datasets/7/formulas/preview": () => json(200, { result_type: "number", rows: [], total_rows: 0 }),
    });
    const check = await checkFormula(7, { expression: "1+" });
    expect(check).toMatchObject({ ok: false, result_type: null, refs: [], errors: [{ code: "X", message: "m", start: 2, end: 2 }] });
    expect(await previewFormula(7, { expression: "1" })).toMatchObject({ error_count: 0, empty_count: 0, rows: [] });
  });

  it("D7·D9: 배열·페이지 모두 받고 D9 건수가 없으면 실패 목록 길이", async () => {
    installFetch({
      "GET /checks/formula-errors": () => json(200, [{ dataset_id: 1 }]),
      "GET /checks/views": () => json(200, { failed: [{ dataset_id: 1, dataset_name: "a", reason: "r", since: null }] }),
    });
    expect(await listFormulaErrorSummaries({ limit: 50, offset: 0 })).toMatchObject({ total: 1 });
    expect(await getViewsStatus()).toMatchObject({ views: 0, views_failed_count: 1 });
  });
});

describe("messages", () => {
  it("셀 오류 문구는 D1 우선, 없으면 기본 문구", () => {
    expect(cellErrorText("E2", { E2: "서버" })).toBe("서버");
    expect(cellErrorText("E2", undefined)).toBe(DEFAULT_CELL_ERRORS.E2);
    // FU-3: E4 기본 문구(07 §3-1)와 서버 문구 우선
    expect(cellErrorText("E4", undefined)).toBe(
      "이 행의 기준 날짜가 속한 연도의 기준값이 등록되어 있지 않아 계산하지 못했습니다. 기준값 화면에서 그 연도 값을 추가하세요.",
    );
    expect(cellErrorText("E4", { E4: "서버 E4" })).toBe("서버 E4");
    expect(cellErrorText("E9", {})).toBe("계산할 수 없는 값입니다.");
  });

  it("미리보기 칸: 값 / 오류 / 빈 값 구별, 불리언·숫자 서식", () => {
    expect(previewCell({ row_id: 1, period: null, value: "0", error: null }, "number")).toEqual({ kind: "value", text: "0" });
    expect(previewCell({ row_id: 1, period: null, value: null, error: "E1" }, "number")).toMatchObject({ kind: "error", code: "E1" });
    expect(previewCell({ row_id: 1, period: null, value: null, error: null }, "number")).toEqual({ kind: "empty", text: "빈 값" });
    expect(previewCell({ row_id: 1, period: null, value: true, error: null }, "boolean")).toEqual({ kind: "value", text: "예" });
    expect(previewCell({ row_id: 1, period: null, value: "12345.50", error: null }, "number").kind).toBe("value");
    expect(previewCell({ row_id: 1, period: null, value: "가", error: null }, "알 수 없음")).toEqual({ kind: "value", text: "가" });
  });

  it("오류 details 읽기", () => {
    const invalid = new ApiError(422, { code: "FORMULA_INVALID", message: "", details: { errors: [{ code: "A", message: "m", start: 1, end: 2 }] }, request_id: null });
    expect(invalidErrorsOf(invalid)).toHaveLength(1);
    expect(invalidErrorsOf(new Error("x"))).toEqual([]);
    expect(retryAfterOf(new ApiError(429, { code: "PREVIEW_BUSY", message: "", details: { retry_after: 3 }, request_id: null }))).toBe(3);
    expect(retryAfterOf(new ApiError(429, { code: "PREVIEW_BUSY", message: "", details: null, request_id: null }))).toBeUndefined();
  });
});
