import { describe, expect, it } from "vitest";
import cases from "./fixtures/clipboard-cases.json";
import { parsePaste, serializePaste } from "./parser";

/**
 * 시험 기준(07 §9): docs/samples/clipboard-cases.json 42건 + 속성 시험.
 * frontend 이미지는 `docker build --target test frontend`처럼 frontend/ 폴더만 빌드 문맥으로 쓰므로 docs/를 직접 읽을 수 없다.
 * 그래서 fixtures/ 에 사본을 두고, 저장소 전체가 있을 때는 아래 "원본과 같은 내용" 시험이 사본이 어긋나지 않았는지 확인한다.
 *
 * 한계: 합성 사례이며 실제 Excel·Teams 클립보드로 검증하지 않았다(docs/samples/README.md). raw는 직렬화 가정이다.
 */
interface Case {
  name: string;
  raw: string;
  expected: string[][] | null;
  expected_error?: string;
}
const ALL = (cases as { cases: Case[] }).cases;

describe("clipboard-cases.json", () => {
  it("사례는 42건이다", () => {
    expect(ALL).toHaveLength(42);
  });

  it("원본(docs/samples)과 같은 내용이다(저장소 전체가 있을 때만 확인)", () => {
    const original = import.meta.glob("../../../../../docs/samples/clipboard-cases.json", { eager: true, import: "default" });
    const found = Object.values(original);
    if (found.length === 0) return; // 이미지 빌드처럼 docs/가 없는 환경
    expect(found[0]).toEqual(cases);
  });

  for (const c of ALL) {
    if (c.expected === null) {
      it(`${c.name}: 붙여넣기를 거부한다`, () => {
        const result = parsePaste(c.raw);
        expect(result.ok).toBe(false);
        if (!result.ok) expect(result.message.length).toBeGreaterThan(0);
      });
    } else {
      it(`${c.name}`, () => {
        expect(parsePaste(c.raw)).toEqual({ ok: true, rows: c.expected });
      });
    }
  }

  it("거부 사례는 NUL과 닫히지 않은 따옴표를 구별한다", () => {
    expect(parsePaste("a\u0000b")).toMatchObject({ ok: false, error: "NUL" });
    expect(parsePaste('"abc\tdef')).toMatchObject({ ok: false, error: "UNCLOSED_QUOTE" });
    expect(parsePaste('"abc\t"def')).toMatchObject({ ok: false, error: "UNCLOSED_QUOTE" });
  });
});

/** 외부 라이브러리 없이 시드 고정 난수(mulberry32)를 쓴다. */
function rng(seed: number): () => number {
  let a = seed;
  return () => {
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 값 범위 제한: 탭·줄바꿈·따옴표·한글·이모지·공백을 섞되, 따옴표 안에서 \r\n 이 \n 으로 바뀌는 조합("\r\n")은 만들지 않는다.
const ALPHABET = ["a", "b", "1", " ", "가", "😀", ",", "\t", "\n", "\r", '"', '"', "한"];

function randomCell(next: () => number): string {
  const length = Math.floor(next() * 7);
  let out = "";
  for (let i = 0; i < length; i += 1) out += ALPHABET[Math.floor(next() * ALPHABET.length)];
  return out.replaceAll("\r\n", "\r ");
}

function randomTable(next: () => number): string[][] {
  const rows = Math.floor(next() * 7);
  return Array.from({ length: rows }, () => Array.from({ length: 1 + Math.floor(next() * 5) }, () => randomCell(next)));
}

describe("속성 시험: parse(serialize(x)) == x", () => {
  it("무작위 표 2,000개가 CRLF·LF 직렬화 모두 되돌아온다", () => {
    const next = rng(20261012);
    for (let n = 0; n < 2000; n += 1) {
      const table = randomTable(next);
      for (const newline of ["\r\n", "\n"] as const) {
        const text = serializePaste(table, newline);
        const result = parsePaste(text);
        expect(result, JSON.stringify({ table, text })).toEqual({ ok: true, rows: table });
      }
    }
  });

  it("직렬화에서 끝 구분자를 빼도 같은 표가 나온다(마지막 행이 빈 한 칸이 아닐 때)", () => {
    const next = rng(7);
    for (let n = 0; n < 500; n += 1) {
      const table = randomTable(next).filter((row) => row.length > 0);
      if (table.length === 0) continue;
      const last = table[table.length - 1];
      if (last.length === 1 && last[0] === "") continue; // 끝 구분자를 빼면 빈 행 자체가 사라져 구별되지 않는다
      const text = serializePaste(table, "\n").replace(/\n$/, "");
      expect(parsePaste(text), JSON.stringify({ table, text })).toEqual({ ok: true, rows: table });
    }
  });

  it("어떤 입력이든 예외 없이 끝나고 결과는 문자열 배열뿐이다", () => {
    const next = rng(99);
    const chars = ["a", "\t", "\n", "\r", '"', " ", "\u0000", "가"];
    for (let n = 0; n < 3000; n += 1) {
      const length = Math.floor(next() * 12);
      let text = "";
      for (let i = 0; i < length; i += 1) text += chars[Math.floor(next() * chars.length)];
      const result = parsePaste(text);
      if (result.ok) {
        for (const row of result.rows) {
          expect(row.length).toBeGreaterThan(0);
          for (const cell of row) expect(typeof cell).toBe("string");
        }
      } else {
        expect(["NUL", "UNCLOSED_QUOTE"]).toContain(result.error);
      }
    }
  });
});
