import { describe, expect, it } from "vitest";
import { COL } from "../../dataset/test-server";
import { SALES_COLUMNS } from "../test-server";
import type { Row } from "../types";
import { buildPastePlan, MAX_PASTE_ROWS, type PasteInput } from "./plan";

const ROWS: Row[] = [
  { row_id: 3, cells: { "1": "2026-03-01", "2": "30", "3": "c" } },
  { row_id: 2, cells: { "1": "2026-02-01", "2": "20", "3": null } },
  { row_id: 1, cells: { "1": "2026-01-01", "2": "10", "3": "a" } },
];

const base = (patch: Partial<PasteInput>): PasteInput => ({
  matrix: [["1"]],
  columns: SALES_COLUMNS,
  savedRows: ROWS,
  startRow: 0,
  startColumn: 1,
  isLastPage: true,
  baseDateColumnId: 1,
  expectedVersion: 5,
  ...patch,
});

describe("buildPastePlan", () => {
  it("현재 칸부터 아래/오른쪽으로 채운다: 기존 행은 row_id + expected, 값은 문자열|null 그대로", () => {
    const built = buildPastePlan(base({ matrix: [["11", "x"], ["", " y "]], startRow: 1, startColumn: 1 }));
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.plan.request).toEqual({
      expected_version: 5,
      column_ids: [2, 3],
      rows: [
        { row_id: 2, expected: ["20", null], values: ["11", "x"] },
        { row_id: 1, expected: ["10", "a"], values: [null, " y "] },
      ],
    });
    expect(built.plan).toMatchObject({ existingRows: 2, newRows: 0, columnNames: ["매출", "메모"], rowSlots: [1, 2] });
  });

  it("끝을 넘는 줄은 새 행(row_id=null, expected 키 없음)", () => {
    const built = buildPastePlan(base({ matrix: [["2026-01-01", "1"], ["2026-04-01", "2"], ["2026-05-01", "3"]], startRow: 2, startColumn: 0 }));
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.plan.request.rows).toEqual([
      { row_id: 1, expected: ["2026-01-01", "10"], values: ["2026-01-01", "1"] },
      { row_id: null, values: ["2026-04-01", "2"] },
      { row_id: null, values: ["2026-05-01", "3"] },
    ]);
    expect(built.plan.rowSlots).toEqual([2, null, null]);
  });

  it("새 행 영역(startRow=null)에서는 전부 새 행이고 기준 날짜 열도 붙일 수 있다", () => {
    const built = buildPastePlan(base({ matrix: [["2026-04-01", "5"]], startRow: null, startColumn: 0 }));
    expect(built.ok).toBe(true);
    if (!built.ok) return;
    expect(built.plan.request.rows).toEqual([{ row_id: null, values: ["2026-04-01", "5"] }]);
  });

  it("칸 수가 모자란 줄: 새 행은 null로 채우고 기존 행은 거부(빈 칸 삭제 방지)", () => {
    const newRows = buildPastePlan(base({ matrix: [["2026-04-01", "5"], ["2026-05-01"]], startRow: null, startColumn: 0 }));
    expect(newRows.ok && newRows.plan.request.rows[1].values).toEqual(["2026-05-01", null]);
    const existing = buildPastePlan(base({ matrix: [["1", "x"], ["2"]], startRow: 0, startColumn: 1 }));
    expect(existing.ok).toBe(false);
    if (!existing.ok) expect(existing.problems[0]).toMatchObject({ line: 2 });
  });

  it("5,000행 초과와 1MiB 초과는 서버 호출 전에 거부", () => {
    const tooMany = buildPastePlan(base({ matrix: Array.from({ length: MAX_PASTE_ROWS + 1 }, () => ["1"]), startRow: null }));
    expect(tooMany.ok).toBe(false);
    const exactly = buildPastePlan(base({ matrix: Array.from({ length: MAX_PASTE_ROWS }, () => ["2026-01-01", "1"]), startRow: null, startColumn: 0 }));
    expect(exactly.ok).toBe(true);
    const big = buildPastePlan(base({ matrix: [["2026-01-01", "1", "가".repeat(400_000)]], startRow: null, startColumn: 0 }));
    expect(big.ok).toBe(false);
    if (!big.ok) expect(big.problems[0].message).toContain("1MiB");
  });

  it("계산 열·기존 행의 기준 날짜 열·열 부족·행 부족(마지막 쪽 아님)을 거부", () => {
    const formula = buildPastePlan(base({ matrix: [["1", "2", "3"]], startColumn: 3 })); // 등급, 합계(계산) -> 폭 3은 열 부족도 겹침
    expect(formula.ok).toBe(false);
    const formula2 = buildPastePlan(base({ matrix: [["1", "2"]], startColumn: 3 }));
    expect(formula2.ok).toBe(false);
    if (!formula2.ok) expect(formula2.problems[0].message).toContain("합계");
    const period = buildPastePlan(base({ matrix: [["2026-09-01"]], startColumn: 0 })); // 첫 기존 행은 2026-03-01
    expect(period.ok).toBe(false);
    if (!period.ok) expect(period.problems[0]).toMatchObject({ line: 1, column: "기준일" });
    const columns = buildPastePlan(base({ matrix: [["1", "2", "3", "4", "5", "6"]], startColumn: 0, startRow: null }));
    expect(columns.ok).toBe(false);
    const notLast = buildPastePlan(base({ matrix: [["1"], ["2"], ["3"], ["4"]], startRow: 2, isLastPage: false }));
    expect(notLast.ok).toBe(false);
    if (!notLast.ok) expect(notLast.problems[0].message).toContain("마지막 쪽");
  });

  it("모호한 값은 줄 번호와 열 이름으로 모아 최대 20건까지 보고하고 보내지 않는다", () => {
    const matrix = Array.from({ length: 30 }, () => ["2026-01-01", "1,000"]);
    const built = buildPastePlan(base({ matrix, startRow: null, startColumn: 0 }));
    expect(built.ok).toBe(false);
    if (built.ok) return;
    expect(built.problems).toHaveLength(20);
    expect(built.problems[0]).toMatchObject({ line: 1, column: "매출" });
  });

  it("빈 입력은 거부", () => {
    expect(buildPastePlan(base({ matrix: [] })).ok).toBe(false);
  });

  it("기준 날짜 열이 없는 데이터셋은 모든 입력 열을 붙일 수 있다", () => {
    const columns = [COL(1, "이름", "text"), COL(2, "수량", "number")];
    const built = buildPastePlan(base({ columns, baseDateColumnId: null, matrix: [["a", "1"]], startRow: 0, startColumn: 0, savedRows: [{ row_id: 7, cells: {} }] }));
    expect(built.ok && built.plan.request.rows[0]).toEqual({ row_id: 7, expected: [null, null], values: ["a", "1"] });
  });

  describe("기존 행의 기준 날짜 열(05 C4: 같은 값은 무시, 바꾸려 할 때만 거부)", () => {
    it("저장된 값과 같으면 통과하고 그대로 values에 싣는다(앞뒤 공백은 비교 전에 뺀다)", () => {
      const built = buildPastePlan(base({ matrix: [["2026-03-01", "31"], [" 2026-02-01 ", "21"]], startRow: 0, startColumn: 0 }));
      expect(built.ok).toBe(true);
      if (!built.ok) return;
      expect(built.plan.request.rows).toEqual([
        { row_id: 3, expected: ["2026-03-01", "30"], values: ["2026-03-01", "31"] },
        { row_id: 2, expected: ["2026-02-01", "20"], values: ["2026-02-01", "21"] },
      ]);
    });

    it("다르면 거부한다(빈 글자 포함). 같은 줄의 다른 칸 오류와 함께 모은다", () => {
      const different = buildPastePlan(base({ matrix: [["2026-03-01", "1"], ["2026-02-02", "2"], ["", "3"]], startRow: 0, startColumn: 0 }));
      expect(different.ok).toBe(false);
      if (different.ok) return;
      expect(different.problems.map((p) => p.line)).toEqual([2, 3]);
      expect(different.problems[0].message).toContain("기간");
    });

    it("기존 행 + 같은 기준월 + 새 행 혼합 붙여넣기는 계획까지 간다", () => {
      const built = buildPastePlan(base({ matrix: [["2026-01-01", "1"], ["2026-04-01", "2"]], startRow: 2, startColumn: 0 }));
      expect(built.ok).toBe(true);
      if (built.ok) expect(built.plan).toMatchObject({ existingRows: 1, newRows: 1 });
    });
  });

  describe("새 행의 기준 날짜 열(서버 REQUIRED와 같은 취지로 미리 안내)", () => {
    it("기준 날짜 열이 붙여넣는 열에 없으면 거부한다", () => {
      const built = buildPastePlan(base({ matrix: [["1"], ["2"], ["3"], ["4"]], startRow: 2, startColumn: 1 }));
      expect(built.ok).toBe(false);
      if (built.ok) return;
      expect(built.problems.map((p) => p.line)).toEqual([2, 3, 4]);
      expect(built.problems[0].message).toContain("새 행에는 기준 열 값이 필요합니다");
    });

    it("기준 날짜 칸이 비어 있어도 거부한다", () => {
      const built = buildPastePlan(base({ matrix: [["", "1"], ["  ", "2"]], startRow: null, startColumn: 0 }));
      expect(built.ok).toBe(false);
      if (!built.ok) expect(built.problems).toHaveLength(2);
    });

    it("기준 날짜 열이 없는 데이터셋에는 적용하지 않는다", () => {
      const built = buildPastePlan(base({ baseDateColumnId: null, matrix: [["1"]], startRow: null, startColumn: 1 }));
      expect(built.ok).toBe(true);
    });
  });
});
