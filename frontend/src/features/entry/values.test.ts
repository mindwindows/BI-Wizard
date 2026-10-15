import { describe, expect, it } from "vitest";
import { COL } from "../dataset/test-server";
import { cellTitle } from "./gridColumns";
import { ENTRY_ROW, type GridRow } from "./model";
import { displayText, editorText, formatComputedNumber, formatNumber, parseEditInput, pasteCellValue, sameValue } from "./values";

const NUM = COL(1, "매출", "number", { rules: { decimals: 2 } });
const NUM_FREE = COL(2, "수량", "number");

describe("formatNumber: 십진 문자열의 표시 서식(문자열 그대로, 부동소수점 없음)", () => {
  it.each([
    ["1234.5", 2, "1,234.50"],
    ["1234.50", undefined, "1,234.50"],
    ["0", undefined, "0"],
    ["0", 2, "0.00"],
    ["-5", 1, "-5.0"],
    ["-1234567", undefined, "-1,234,567"],
    ["12345678901234567890.12345", 2, "12,345,678,901,234,567,890.12345"], // 자릿수 규칙보다 길면 깎지 않는다
    ["0.1000", undefined, "0.1000"], // 서버가 준 끝자리 0 보존
    ["999", undefined, "999"],
    ["1000", undefined, "1,000"],
  ])("%s (decimals %s) -> %s", (raw, decimals, expected) => {
    expect(formatNumber(raw, decimals)).toBe(expected);
  });

  it("십진 형식이 아니면 받은 글자를 그대로 둔다(화면이 값을 추측해 고치지 않음)", () => {
    expect(formatNumber("1e5")).toBe("1e5");
    expect(formatNumber("abc")).toBe("abc");
  });
});

describe("displayText: 빈 칸(null)과 값 0은 다르다", () => {
  it("null/undefined는 빈 글자, 0은 '0.00'", () => {
    expect(displayText(NUM, null)).toBe("");
    expect(displayText(NUM, undefined)).toBe("");
    expect(displayText(NUM, "0")).toBe("0.00");
    expect(displayText(NUM_FREE, "0")).toBe("0");
  });
  it("오류 코드가 있으면 값이 null이어도 '오류'", () => {
    expect(displayText(NUM, null, "E1")).toBe("오류");
  });
  it("예/아니오는 글자로, 문자열 true/false도 받는다", () => {
    const b = COL(3, "승인", "boolean");
    expect(displayText(b, true)).toBe("예");
    expect(displayText(b, false)).toBe("아니오");
    expect(displayText(b, "true")).toBe("예");
    expect(displayText(b, null)).toBe("");
  });
  it("편집기에는 서식 없는 원래 값을 넣는다", () => {
    expect(editorText(NUM, "1234.50")).toBe("1234.50");
    expect(editorText(NUM, null)).toBe("");
    expect(editorText(COL(3, "승인", "boolean"), false)).toBe("아니오");
  });
});

describe("parseEditInput", () => {
  it("빈 글자는 null", () => {
    for (const column of [NUM, COL(3, "메모", "text"), COL(4, "날짜", "date"), COL(5, "승인", "boolean"), COL(6, "선택", "choice")]) {
      expect(parseEditInput(column, "")).toEqual({ ok: true, value: null });
    }
  });
  it("숫자는 십진 문자열 그대로(앞뒤 공백만 제거), 아니면 쉬운 문구", () => {
    expect(parseEditInput(NUM, " 12.50 ")).toEqual({ ok: true, value: "12.50" });
    expect(parseEditInput(NUM, "-3")).toEqual({ ok: true, value: "-3" });
    for (const bad of ["1,234", "12.5%", "abc", "1e5", ".5", "5."]) {
      const result = parseEditInput(NUM, bad);
      expect(result.ok, bad).toBe(false);
    }
  });
  it("날짜는 YYYY-MM-DD이고 존재하는 날이어야 한다", () => {
    expect(parseEditInput(COL(4, "날짜", "date"), "2026-02-28")).toEqual({ ok: true, value: "2026-02-28" });
    expect(parseEditInput(COL(4, "날짜", "date"), "2026-02-30").ok).toBe(false);
    expect(parseEditInput(COL(4, "날짜", "date"), "2026/02/28").ok).toBe(false);
  });
  it("예/아니오는 불리언으로", () => {
    const b = COL(5, "승인", "boolean");
    expect(parseEditInput(b, "예")).toEqual({ ok: true, value: true });
    expect(parseEditInput(b, "아니오")).toEqual({ ok: true, value: false });
    expect(parseEditInput(b, "maybe").ok).toBe(false);
  });
  it("글자는 공백을 포함해 그대로", () => {
    expect(parseEditInput(COL(3, "메모", "text"), " a ")).toEqual({ ok: true, value: " a " });
  });
});

describe("pasteCellValue: 문자열|null 그대로, 모호한 숫자·날짜만 막는다", () => {
  it("빈 글자는 null, 글자는 공백 그대로", () => {
    expect(pasteCellValue(COL(3, "메모", "text"), "")).toEqual({ ok: true, value: null });
    expect(pasteCellValue(COL(3, "메모", "text"), " a ")).toEqual({ ok: true, value: " a " });
  });
  it("숫자는 엄격한 십진 문자열만 통과한다(엑셀 표시 서식은 모호하므로 오류)", () => {
    expect(pasteCellValue(NUM, "1234.50")).toEqual({ ok: true, value: "1234.50" });
    for (const bad of ["1,234.50", "12.5%", "₩1,000", "(1,000)", "1.2E+05", " 12"]) {
      expect(pasteCellValue(NUM, bad).ok, bad).toBe(false);
    }
  });
  it("날짜는 YYYY-MM-DD만", () => {
    const d = COL(4, "날짜", "date");
    expect(pasteCellValue(d, "2026-10-11").ok).toBe(true);
    for (const bad of ["2026/10/11", "10/11/2026", "2026년 10월 11일"]) expect(pasteCellValue(d, bad).ok, bad).toBe(false);
  });
  it("선택 목록·예/아니오는 서버가 판정한다(화면은 통과)", () => {
    expect(pasteCellValue(COL(5, "승인", "boolean"), "maybe")).toEqual({ ok: true, value: "maybe" });
    expect(pasteCellValue(COL(6, "선택", "choice"), "없는값")).toEqual({ ok: true, value: "없는값" });
  });
});

describe("sameValue", () => {
  it("미입력끼리는 같고 0과 미입력은 다르다", () => {
    expect(sameValue(null, undefined)).toBe(true);
    expect(sameValue("0", null)).toBe(false);
    expect(sameValue("1234.50", "1234.50")).toBe(true);
    expect(sameValue("1234.5", "1234.50")).toBe(false); // 십진 문자열을 부동소수점으로 합치지 않는다
    expect(sameValue(true, "true")).toBe(true);
  });
});

describe("formatComputedNumber: 계산 열 표시(소수 최대 6자리, 끝자리 0 제거, 쉼표, 0에서 먼 쪽 반올림)", () => {
  it.each([
    ["0.5", "0.5"],
    ["1234.500000", "1,234.5"], // 끝자리 0 제거
    ["1234.000000", "1,234"],
    ["12.3456780000", "12.345678"],
    ["0", "0"],
    ["0.000000", "0"],
    ["100", "100"],
    ["1000", "1,000"],
    ["-1234567.5", "-1,234,567.5"],
    ["0.1234564", "0.123456"], // 7번째 자리 4: 내림
    ["0.1234565", "0.123457"], // 5: 올림(경계)
    ["0.1234569", "0.123457"],
    ["-0.1234565", "-0.123457"], // 음수도 0에서 먼 쪽
    ["-0.1234564", "-0.123456"],
    ["0.9999995", "1"], // 자리 올림이 정수부까지
    ["999.9999995", "1,000"],
    ["-0.9999995", "-1"],
    ["999999.9999999", "1,000,000"],
    ["0.0000004", "0"], // 반올림하면 0
    ["-0.0000004", "0"], // -0이 되지 않음
    ["-0.0000005", "-0.000001"],
    ["0.0000005", "0.000001"],
    ["0.0000001", "0"], // 1E-7 같은 과학 표기가 오지 않음
    ["1234567890123456789012345678901234.5678", "1,234,567,890,123,456,789,012,345,678,901,234.5678"],
    ["12345678901234567890123456789012345678", "12,345,678,901,234,567,890,123,456,789,012,345,678"], // 38자리 정수
    ["1234567890123456789012345678.123456789012", "1,234,567,890,123,456,789,012,345,678.123457"],
    ["99999999999999999999999999999999999999.9999999", "100,000,000,000,000,000,000,000,000,000,000,000,000"],
  ])("%s -> %s", (raw, expected) => {
    expect(formatComputedNumber(raw).text).toBe(expected);
    expect(formatComputedNumber(raw).text).not.toMatch(/e/i);
    expect(formatComputedNumber(raw).full).toBe(raw);
  });

  it("6자리를 넘는 0이 아닌 자릿수가 있을 때만 truncated", () => {
    expect(formatComputedNumber("0.1234567").truncated).toBe(true);
    expect(formatComputedNumber("0.0000004").truncated).toBe(true);
    expect(formatComputedNumber("1.5000000").truncated).toBe(false); // 끝자리 0만 잘림
    expect(formatComputedNumber("1.123456").truncated).toBe(false);
    expect(formatComputedNumber("42").truncated).toBe(false);
  });

  it("십진 형식이 아니면 그대로 둔다", () => {
    expect(formatComputedNumber("abc")).toEqual({ text: "abc", full: "abc", truncated: false });
  });

  it("displayText는 계산 열 숫자에만 적용하고 입력 열(decimals 0 채움 등)은 그대로 둔다", () => {
    const calc = COL(9, "합계", "number", { kind: "formula" });
    const raw = COL(1, "매출", "number", { rules: { decimals: 2 } });
    expect(displayText(calc, "1234.5000000")).toBe("1,234.5");
    expect(displayText(calc, "0.1234567")).toBe("0.123457");
    expect(displayText(calc, null)).toBe("");
    expect(displayText(raw, "1234.5")).toBe("1,234.50");
    expect(displayText(raw, "0.1234567")).toBe("0.1234567"); // 입력 열은 깎지 않음
    expect(displayText(COL(10, "메모", "text", { kind: "formula" }), "0.1234567")).toBe("0.1234567"); // 숫자가 아닌 계산 열은 그대로
  });
});

describe("formatComputedNumber: 열별 표시 형식(display_decimals, display_thousands)", () => {
  it.each([
    ["1234.5", 2, "1,234.50"], // 끝자리 0 채움
    ["1234", 2, "1,234.00"],
    ["0", 3, "0.000"],
    ["2026", 0, "2,026"],
    ["1234.5", 0, "1,235"], // 경계 반올림(5는 올림)
    ["1234.4999", 0, "1,234"],
    ["0.125", 2, "0.13"],
    ["0.124999", 2, "0.12"],
    ["-0.125", 2, "-0.13"], // 음수도 0에서 먼 쪽
    ["-1234.5", 0, "-1,235"],
    ["-0.004", 2, "0.00"], // 반올림 결과가 0이면 부호 없음
    ["-0", 0, "0"],
    ["-0.0", 1, "0.0"],
    ["0.995", 2, "1.00"], // 자리 올림이 정수부까지
    ["999.999", 2, "1,000.00"],
    ["-999.999", 2, "-1,000.00"],
    ["1.5", 10, "1.5000000000"],
    ["0.12345678905", 10, "0.1234567891"],
    ["12345678901234567890123456789012345678.5", 0, "12,345,678,901,234,567,890,123,456,789,012,345,679"],
    ["99999999999999999999999999999999999999.99", 1, "100,000,000,000,000,000,000,000,000,000,000,000,000.0"],
  ])("%s, 자릿수 %i -> %s", (raw, decimals, expected) => {
    const shown = formatComputedNumber(raw, { decimals });
    expect(shown.text).toBe(expected);
    expect(shown.full).toBe(raw);
  });

  it("쉼표를 끄면 정수부에 쉼표가 없다(YEAR 결과 등)", () => {
    expect(formatComputedNumber("2026", { thousands: false }).text).toBe("2026");
    expect(formatComputedNumber("2026").text).toBe("2,026");
    expect(formatComputedNumber("-1234567.5", { thousands: false }).text).toBe("-1234567.5");
    expect(formatComputedNumber("1234567.891", { decimals: 1, thousands: false }).text).toBe("1234567.9");
    expect(formatComputedNumber("999.9999995", { thousands: false }).text).toBe("1000");
  });

  it("옵션이 없거나 thousands만 있으면 소수 6자리·끝자리 0 제거 규칙 그대로", () => {
    expect(formatComputedNumber("1234.5000000", {}).text).toBe("1,234.5");
    expect(formatComputedNumber("0.1234567", { thousands: true }).text).toBe("0.123457");
  });

  it("truncated는 표시 자릿수 밖에 0이 아닌 자릿수가 있을 때 true", () => {
    expect(formatComputedNumber("1.239", { decimals: 2 }).truncated).toBe(true);
    expect(formatComputedNumber("1.200", { decimals: 2 }).truncated).toBe(false);
  });

  it("displayText: 열 rules를 읽고, 숫자가 아닌 계산 열·입력 열은 무시한다(지우지 않음)", () => {
    const calc = COL(9, "합계", "number", { kind: "formula", rules: { display_decimals: 2, display_thousands: false } });
    expect(displayText(calc, "12345.678")).toBe("12345.68");
    expect(displayText(calc, "7")).toBe("7.00");
    expect(displayText({ ...calc, rules: { display_decimals: 0 } }, "2026")).toBe("2,026");
    expect(displayText({ ...calc, rules: { display_decimals: 11, display_thousands: "no" } as never }, "1234.5000000")).toBe("1,234.5"); // 범위 밖·불리언 아님은 무시
    expect(displayText({ ...calc, rules: { display_decimals: 1.5 } }, "1.25")).toBe("1.25");
    const text = COL(10, "메모", "text", { kind: "formula", rules: { display_decimals: 2 } });
    expect(displayText(text, "0.1234567")).toBe("0.1234567");
    const input = COL(1, "매출", "number", { rules: { display_decimals: 0, display_thousands: false } });
    expect(displayText(input, "1234.5")).toBe("1,234.5"); // 입력 열은 이번에 제외
    expect(displayText(calc, "abc")).toBe("abc");
  });

  it("복사·API 값(원본 문자열)은 서식과 무관하다", () => {
    expect(formatComputedNumber("1234.5678", { decimals: 1 }).full).toBe("1234.5678");
  });
});

describe("cellTitle(툴팁): 열 표시 자릿수에 맞춰 잘린 칸만 전체 값을 알려 준다", () => {
  const row = (value: string): GridRow => ({ ...ENTRY_ROW, key: "r1", rowId: 1, draft: false, entry: false, cells: { "9": value } });
  it("자릿수 설정에서 반올림된 칸은 전체 값, 같은 칸이 아니면 일반 안내", () => {
    const calc = COL(9, "합계", "number", { kind: "formula", rules: { display_decimals: 2 } });
    expect(cellTitle(calc, row("1.239"))).toBe("전체 값: 1.239");
    expect(cellTitle(calc, row("1.2"))).toContain("직접 고칠 수 없습니다");
    expect(cellTitle({ ...calc, rules: null }, row("1.239"))).toContain("직접 고칠 수 없습니다"); // 기본은 6자리
  });
});
