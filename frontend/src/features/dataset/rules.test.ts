import { describe, expect, it } from "vitest";
import {
  compareDecimal,
  draftFromRules,
  emptyDraft,
  rulesFromDraft,
  validateColumnName,
  validateTag,
} from "./rules";

describe("validateColumnName (05 §1 이름 규칙)", () => {
  it.each([["[매출]"], ["매출]"], ['매"출'], ["a\nb"], ["a\tb"], ["a\u0000b"]])("금지 문자 %j는 거부한다", (name) => {
    expect(validateColumnName(name)).toContain("쓸 수 없습니다");
  });

  it.each([["team"], ["팀"], ["row_id"], ["행 번호"], ["  team  "]])("예약어 %j는 안내와 함께 거부한다", (name) => {
    const message = validateColumnName(name);
    expect(message).toContain("예약");
    expect(message).toContain("행 번호");
  });

  it("비어 있거나 공백뿐이면 거부, 100자는 통과, 101자는 거부", () => {
    expect(validateColumnName("   ")).toContain("입력");
    expect(validateColumnName("가".repeat(100))).toBeNull();
    expect(validateColumnName("가".repeat(101))).toContain("100자");
  });

  it("보통 이름은 통과한다(괄호·공백·점 포함)", () => {
    expect(validateColumnName("매출 (원)")).toBeNull();
    expect(validateColumnName("Team A")).toBeNull();
  });
});

describe("validateTag", () => {
  it("50자, 큰따옴표·제어문자 금지", () => {
    expect(validateTag("")).toBeNull();
    expect(validateTag("비용")).toBeNull();
    expect(validateTag("a".repeat(51))).toContain("50자");
    expect(validateTag('a"b')).toContain("쓸 수 없습니다");
    expect(validateTag("a\nb")).toContain("쓸 수 없습니다");
  });
});

describe("compareDecimal (십진 문자열 비교, 부동소수점을 쓰지 않음)", () => {
  it("부호·자릿수·소수부를 정확히 비교한다", () => {
    expect(compareDecimal("1", "2")).toBeLessThan(0);
    expect(compareDecimal("10", "9.99")).toBeGreaterThan(0);
    expect(compareDecimal("-1.5", "-1.50")).toBe(0);
    expect(compareDecimal("-2", "1")).toBeLessThan(0);
    expect(compareDecimal("0.1", "0.10000000000000000001")).toBeLessThan(0);
    expect(compareDecimal("12345678901234567890123456789012345678", "12345678901234567890123456789012345679")).toBeLessThan(0);
  });
});

describe("rulesFromDraft (규칙 입력 -> 요청 rules)", () => {
  const draft = (patch: Partial<ReturnType<typeof emptyDraft>>) => ({ ...emptyDraft(), ...patch });

  it("number: min·max는 십진 문자열, decimals는 정수로 보낸다", () => {
    expect(rulesFromDraft("number", draft({ min: "0", max: "100.50", decimals: "2" }))).toEqual({
      ok: true,
      rules: { min: "0", max: "100.50", decimals: 2 },
    });
  });

  it("number: 비운 항목은 키를 보내지 않는다", () => {
    expect(rulesFromDraft("number", draft({ min: " -5 " }))).toEqual({ ok: true, rules: { min: "-5" } });
    expect(rulesFromDraft("number", draft({}))).toEqual({ ok: true, rules: {} });
  });

  it.each([["abc"], ["1e3"], ["1,000"], ["."], ["--1"], ["1."]])("number: 최솟값 %j는 십진수가 아니라 거부", (min) => {
    const result = rulesFromDraft("number", draft({ min }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.min).toContain("숫자");
  });

  it("number: 최솟값이 최댓값보다 크면 거부, 같으면 통과", () => {
    const bad = rulesFromDraft("number", draft({ min: "10.5", max: "10.49" }));
    expect(bad.ok).toBe(false);
    if (!bad.ok) expect(bad.errors.max).toContain("최솟값");
    expect(rulesFromDraft("number", draft({ min: "5", max: "5.0" })).ok).toBe(true);
  });

  it.each([["-1"], ["1.5"], ["x"]])("number: 소수 자릿수 %j는 거부", (decimals) => {
    const result = rulesFromDraft("number", draft({ decimals }));
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.decimals).toContain("0 이상의 정수");
  });

  it("text: max_length는 1 이상의 정수", () => {
    expect(rulesFromDraft("text", draft({ maxLength: "30" }))).toEqual({ ok: true, rules: { max_length: 30 } });
    expect(rulesFromDraft("text", draft({}))).toEqual({ ok: true, rules: {} });
    for (const bad of ["0", "-3", "2.5", "a"]) {
      const result = rulesFromDraft("text", draft({ maxLength: bad }));
      expect(result.ok).toBe(false);
    }
  });

  it("date: YYYY-MM-DD만, 이른 날짜가 늦은 날짜보다 뒤면 거부", () => {
    expect(rulesFromDraft("date", draft({ dateMin: "2026-01-01", dateMax: "2026-12-31" }))).toEqual({
      ok: true,
      rules: { min: "2026-01-01", max: "2026-12-31" },
    });
    const bad = rulesFromDraft("date", draft({ dateMin: "2026-05-01", dateMax: "2026-04-30" }));
    expect(bad.ok).toBe(false);
    const format = rulesFromDraft("date", draft({ dateMin: "2026/01/01" }));
    expect(format.ok).toBe(false);
    const impossible = rulesFromDraft("date", draft({ dateMax: "2026-02-30" }));
    expect(impossible.ok).toBe(false);
  });

  it("choice: 줄마다 하나, 앞뒤 공백 제거, 빈 줄 무시, 최소 1개, 중복 거부", () => {
    expect(rulesFromDraft("choice", draft({ options: " 상 \n\n중\r\n하 " }))).toEqual({
      ok: true,
      rules: { options: ["상", "중", "하"] },
    });
    const none = rulesFromDraft("choice", draft({ options: " \n " }));
    expect(none.ok).toBe(false);
    if (!none.ok) expect(none.errors.options).toContain("하나 이상");
    const dup = rulesFromDraft("choice", draft({ options: "상\n상" }));
    expect(dup.ok).toBe(false);
    if (!dup.ok) expect(dup.errors.options).toContain("같은 항목");
  });

  it("boolean: 규칙 없음", () => {
    expect(rulesFromDraft("boolean", draft({ min: "5" }))).toEqual({ ok: true, rules: {} });
  });
});

describe("draftFromRules (서버 rules -> 입력칸)", () => {
  it("숫자로 온 min·max도 문자열로 보여 준다", () => {
    expect(draftFromRules("number", { min: 0, max: "100.5", decimals: 2 })).toMatchObject({ min: "0", max: "100.5", decimals: "2" });
  });
  it("null·빈 rules·다른 타입 키는 빈 입력", () => {
    expect(draftFromRules("number", null)).toEqual(emptyDraft());
    expect(draftFromRules("text", {})).toEqual(emptyDraft());
    expect(draftFromRules("choice", { options: ["a", "b"] }).options).toBe("a\nb");
    expect(draftFromRules("text", { max_length: 10 }).maxLength).toBe("10");
    expect(draftFromRules("date", { min: "2026-01-01" }).dateMin).toBe("2026-01-01");
  });
});
