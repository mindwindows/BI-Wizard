import { describe, expect, it } from "vitest";
import { COL } from "../dataset/test-server";
import {
  applySuggestion,
  completionContext,
  insertColumnRef,
  markSegments,
  suggestColumns,
  suggestFunctions,
  suggestReferences,
  suggestTags,
  suggestionsFor,
  toUtf16Index,
} from "./autocomplete";
import type { ReferenceItem } from "../reference/types";
import type { FunctionInfo } from "./types";

const fn = (name: string): FunctionInfo => ({ name, signature: `${name}(값)`, returns: "숫자", help_ko: "도움말", excel_diff: "" });
const FUNCTIONS = ["ROUND", "ROUNDUP", "ROUNDDOWN", "SUM", "SUMTAG", "IF", "IFERROR", "LEFT", "LEN"].map(fn);

describe("completionContext", () => {
  it("함수 이름은 한 글자 이상 쳤을 때 열린다", () => {
    expect(completionContext("=", 1)).toBeNull();
    expect(completionContext("RO", 2)).toEqual({ kind: "function", from: 0, to: 2, query: "RO" });
    expect(completionContext("[매출] + su", 9)).toEqual({ kind: "function", from: 7, to: 9, query: "su" });
    expect(completionContext("", 0)).toBeNull();
  });

  it("숫자 뒤 글자(1E5)와 연산자 직후는 함수 자리가 아니다", () => {
    expect(completionContext("1E", 2)).toBeNull();
    expect(completionContext("1.5e", 4)).toBeNull();
  });

  it("[ 안에서는 열 이름 자리이고, 닫는 ]까지 바꿀 범위에 넣는다", () => {
    expect(completionContext("[매", 2)).toEqual({ kind: "column", from: 0, to: 2, query: "매" });
    expect(completionContext("1 + []", 5)).toEqual({ kind: "column", from: 4, to: 6, query: "" });
    expect(completionContext("[매출] + [", 8)).toEqual({ kind: "column", from: 7, to: 8, query: "" });
  });

  it("글자 상수 안은 함수 자리가 아니고, SUMTAG(\" 안만 태그 자리다", () => {
    expect(completionContext('"RO', 3)).toBeNull();
    expect(completionContext('"a""RO', 6)).toBeNull();
    expect(completionContext('SUMTAG("수', 9)).toEqual({ kind: "tag", from: 7, to: 9, query: "수" });
    expect(completionContext('sumtag( "수입")', 11)).toEqual({ kind: "tag", from: 8, to: 12, query: "수입" });
  });

  it("닫힌 [..]·\"..\" 뒤는 다시 일반 자리", () => {
    expect(completionContext('"abc" & LE', 10)).toEqual({ kind: "function", from: 8, to: 10, query: "LE" });
    expect(completionContext("[매출] & LE", 11)?.kind).toBe("function");
  });
});

const ref = (name: string, description: string | null = null): ReferenceItem => ({
  id: 1,
  name,
  description,
  value_count: 0,
  year_min: null,
  year_max: null,
  created_by: { id: 1, display_name: "관리자" },
  created_at: "2026-10-14T09:00:00+09:00",
});

describe('REF(" 기준값 이름 자리 (FU-3)', () => {
  it('REF(" 안은 기준값 자리이고 닫는 따옴표까지 바꿀 범위에 넣는다', () => {
    expect(completionContext('REF("', 5)).toEqual({ kind: "reference", from: 4, to: 5, query: "" });
    expect(completionContext('REF("전', 6)).toEqual({ kind: "reference", from: 4, to: 6, query: "전" });
    expect(completionContext('ref( "전기")', 8)).toEqual({ kind: "reference", from: 5, to: 9, query: "전기" });
    expect(completionContext('[매출] * REF("전', 13)).toEqual({ kind: "reference", from: 11, to: 13, query: "전" });
  });

  it("다른 함수 이름의 끝이 REF인 경우(SUMREF, MYREF)와 열 이름·일반 글자 상수는 기준값 자리가 아니다", () => {
    expect(completionContext('SUMREF("전', 10)).toBeNull();
    expect(completionContext('MY_REF("전', 10)).toBeNull();
    expect(completionContext('IF("전', 6)).toBeNull();
    expect(completionContext("[REF(전", 7)?.kind).toBe("column");
  });

  it("글자 상수의 따옴표 두 개(\"\")는 한 글자로 풀어 질의한다", () => {
    expect(completionContext('REF("a""b', 9)?.query).toBe('a"b');
  });

  it("이름 앞부분이 같은 것을 먼저, 포함은 그다음. 설명이 없으면 '기준값'을 보조 설명으로 쓴다", () => {
    const items = [ref("가스요금_A팀"), ref("전기요금_A팀", "A팀 전기 단가"), ref("전기요금_B팀"), ref("환율")];
    expect(suggestReferences(items, "전기").map((s) => s.label)).toEqual(["전기요금_A팀", "전기요금_B팀"]);
    expect(suggestReferences(items, "_a").map((s) => s.label)).toEqual(["가스요금_A팀", "전기요금_A팀"]);
    expect(suggestReferences(items, "").map((s) => s.detail)).toEqual(["기준값", "A팀 전기 단가", "기준값", "기준값"]);
    expect(suggestReferences(items, "zzz")).toEqual([]);
  });

  it("suggestionsFor는 reference 자리에서 항목 후보를 돌려주고 항목이 없으면 빈 목록이다", () => {
    const ctx = completionContext('REF("', 5);
    expect(suggestionsFor(ctx, FUNCTIONS, [], [ref("환율")]).map((s) => s.kind)).toEqual(["reference"]);
    expect(suggestionsFor(ctx, FUNCTIONS, [])).toEqual([]);
  });

  it('고르면 REF("이름") 모양의 글자 상수가 되고 이미 닫힌 따옴표와 겹치지 않는다', () => {
    const pick = suggestReferences([ref("전기요금_A팀")], "전")[0];
    const open = 'REF("전';
    expect(applySuggestion(open, completionContext(open, open.length)!, pick)).toEqual({ text: 'REF("전기요금_A팀"', caret: 13 });
    const closed = 'REF("전")';
    expect(applySuggestion(closed, completionContext(closed, 6)!, pick)).toEqual({ text: 'REF("전기요금_A팀")', caret: 13 });
  });
});

describe("제안 목록", () => {
  it("함수는 앞부분이 같은 것을 먼저, 대소문자 무시", () => {
    expect(suggestFunctions(FUNCTIONS, "ro").map((s) => s.label)).toEqual(["ROUND", "ROUNDUP", "ROUNDDOWN", "IFERROR"]);
    expect(suggestFunctions(FUNCTIONS, "er").map((s) => s.label)).toEqual(["IFERROR"]); // 포함
    expect(suggestFunctions(FUNCTIONS, "zzz")).toEqual([]);
  });

  it("후보를 자르지 않는다(스크롤로 끝까지 고른다)", () => {
    const many = Array.from({ length: 20 }, (_, i) => fn(`F${i}`));
    expect(suggestFunctions(many, "f")).toHaveLength(20);
  });

  it("열 이름은 한글도 앞부분·포함 순, 계산 열 표시", () => {
    const columns = [COL(1, "매출", "number"), COL(2, "총매출", "number", { kind: "formula" }), COL(3, "메모", "text")];
    expect(suggestColumns(columns, "매").map((s) => s.label)).toEqual(["매출", "총매출"]);
    expect(suggestColumns(columns, "").map((s) => s.label)).toHaveLength(3);
    expect(suggestColumns(columns, "총")[0].detail).toBe("계산 열");
  });

  it("태그는 중복 없이", () => {
    const columns = [COL(1, "a", "number", { tag: "수입" }), COL(2, "b", "number", { tag: "수입" }), COL(3, "c", "number", { tag: "지출" })];
    expect(suggestTags(columns, "").map((s) => s.label)).toEqual(["수입", "지출"]);
  });

  it("자리가 없으면 빈 목록, 함수 자리는 질의가 있어야", () => {
    expect(suggestionsFor(null, FUNCTIONS, [])).toEqual([]);
    expect(suggestionsFor({ kind: "function", from: 0, to: 0, query: "" }, FUNCTIONS, [])).toEqual([]);
  });
});

describe("넣기", () => {
  it("함수를 고르면 NAME( 으로 바뀌고 커서는 ( 뒤", () => {
    const text = "[매출] + RO";
    const ctx = completionContext(text, text.length)!;
    const [first] = suggestFunctions(FUNCTIONS, ctx.query);
    expect(applySuggestion(text, ctx, first)).toEqual({ text: "[매출] + ROUND(", caret: 13 });
  });

  it("뒤에 ( 가 이미 있으면 이름만 바꾸고 커서를 ( 뒤로", () => {
    const text = "RO(1)";
    const ctx = completionContext(text, 2)!;
    const edited = applySuggestion(text, ctx, suggestFunctions(FUNCTIONS, "RO")[0]);
    expect(edited).toEqual({ text: "ROUND(1)", caret: 6 });
  });

  it("열 제안은 [이름]으로, 이미 닫는 ] 가 있으면 겹치지 않는다", () => {
    const text = "1 + [매]";
    const ctx = completionContext(text, 6)!;
    expect(applySuggestion(text, ctx, suggestColumns([COL(1, "매출", "number")], "매")[0])).toEqual({ text: "1 + [매출]", caret: 8 });
  });

  it("태그 제안은 따옴표 포함", () => {
    const text = 'SUMTAG("수';
    const ctx = completionContext(text, text.length)!;
    expect(applySuggestion(text, ctx, { kind: "tag", label: "수입", detail: "", insert: "수입" })).toEqual({ text: 'SUMTAG("수입"', caret: 11 });
  });

  it("칩: 커서 위치에 [열 이름], 선택 범위는 바꿔 넣는다", () => {
    expect(insertColumnRef("1 + ", 4, 4, "매출")).toEqual({ text: "1 + [매출]", caret: 8 });
    expect(insertColumnRef("1 + x", 4, 5, "매출")).toEqual({ text: "1 + [매출]", caret: 8 });
    expect(insertColumnRef("ab", 1, 1, "매출")).toEqual({ text: "a[매출]b", caret: 5 });
  });

  it("칩: 열린 [ 를 치던 중이면 그것을 완성한다", () => {
    expect(insertColumnRef("1 + [매", 6, 6, "매출")).toEqual({ text: "1 + [매출]", caret: 8 });
  });
});

describe("오류 위치 표시", () => {
  const error = (start: number, end: number) => ({ code: "X", message: "m", start, end });

  it("오류 구간만 bad로 나눈다", () => {
    expect(markSegments("1 + * 2", [error(4, 5)])).toEqual([
      { text: "1 + ", bad: false },
      { text: "*", bad: true },
      { text: " 2", bad: false },
    ]);
  });

  it("겹치는 오류는 합치고, 수식 밖 위치는 수식 길이로 줄인다", () => {
    expect(markSegments("abcdef", [error(1, 3), error(2, 5), error(4, 99)])).toEqual([
      { text: "a", bad: false },
      { text: "bcdef", bad: true },
    ]);
  });

  it("길이 0 오류는 그 자리 글자 하나, 수식 끝이면 끝 표시 칸", () => {
    expect(markSegments("1 +", [error(1, 1)])).toEqual([
      { text: "1", bad: false },
      { text: " ", bad: true },
      { text: "+", bad: false },
    ]);
    expect(markSegments("1 +", [error(3, 3)])).toEqual([
      { text: "1 +", bad: false },
      { text: " ", bad: true, placeholder: true },
    ]);
  });

  it("오류가 없으면 수식 한 덩어리", () => {
    expect(markSegments("1 + 2", [])).toEqual([{ text: "1 + 2", bad: false }]);
    expect(markSegments("", [])).toEqual([]);
  });

  it("서버 위치(코드포인트)를 UTF-16 위치로 바꾼다", () => {
    expect(toUtf16Index("가나다", 2)).toBe(2);
    expect(toUtf16Index("😀+x", 1)).toBe(2);
    expect(markSegments("😀+x", [error(2, 3)])).toEqual([
      { text: "😀+", bad: false },
      { text: "x", bad: true },
    ]);
  });
});
