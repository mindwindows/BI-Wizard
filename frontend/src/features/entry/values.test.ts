import { describe, expect, it } from "vitest";
import { COL } from "../dataset/test-server";
import { displayText, editorText, formatNumber, parseEditInput, pasteCellValue, sameValue } from "./values";

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
