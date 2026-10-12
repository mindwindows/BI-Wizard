import { describe, expect, it } from "vitest";
import { COL } from "../dataset/test-server";
import { createCells, draftReady, missingRequired } from "./model";
import { buildColumnDefs, rowLabel } from "./gridColumns";
import { emptyDraft, fromServerRow } from "./model";

const COLUMNS = [
  COL(1, "기준일", "date"),
  COL(2, "매출", "number", { required: true }),
  COL(3, "메모", "text"),
  COL(4, "합계", "number", { kind: "formula", required: true }),
];

describe("임시 행 준비 판정", () => {
  it("기준 날짜 열은 required가 아니어도 필수로 본다(05 C2), 계산 열은 필수에서 제외", () => {
    expect(missingRequired(COLUMNS, 1, {}).map((c) => c.display_name)).toEqual(["기준일", "매출"]);
    expect(missingRequired(COLUMNS, null, {}).map((c) => c.display_name)).toEqual(["매출"]);
  });

  it("필수 칸이 모두 차고 값이 있으면 준비됨, 빈 임시 행은 준비되지 않음", () => {
    expect(draftReady(COLUMNS, 1, { "1": "2026-01-01" })).toBe(false);
    expect(draftReady(COLUMNS, 1, { "1": "2026-01-01", "2": "0" })).toBe(true); // 값 0도 채워진 칸
    expect(draftReady(COLUMNS, 1, { "1": null, "2": null })).toBe(false);
    expect(draftReady([COL(5, "메모", "text")], null, {})).toBe(false); // 필수 없음 + 값 없음
    expect(draftReady([COL(5, "메모", "text")], null, { "5": "a" })).toBe(true);
  });

  it("C2 cells는 입력 열의 값 있는 칸만", () => {
    expect(createCells(COLUMNS, { "1": "2026-01-01", "2": "5", "3": null, "4": "9" })).toEqual({ "1": "2026-01-01", "2": "5" });
  });
});

describe("열 정의(AG Grid)", () => {
  const defs = buildColumnDefs({ columns: COLUMNS, baseDateColumnId: 1, canEnter: true, selectedColumnId: 2 });

  it("맨 앞은 고정된 기간/행 번호 열이고 편집 불가", () => {
    expect(defs[0]).toMatchObject({ colId: "__row", pinned: "left", editable: false, headerName: "기간 / 행 번호" });
    expect(defs.slice(1).map((d) => d.colId)).toEqual(["1", "2", "3", "4"]);
    expect(defs[1].headerName).toBe("기준일 (기간)");
  });

  it("편집 가능 여부: 입력 열만, 계산 열·저장 중 칸·읽기 전용은 불가", () => {
    const editable = (colIndex: number, data: unknown, list = defs) => (list[colIndex].editable as (p: { data: unknown }) => boolean)({ data });
    const row = fromServerRow({ row_id: 1, cells: {} });
    expect(editable(2, row)).toBe(true);
    expect(editable(4, row)).toBe(false); // 계산 열
    expect(editable(2, { ...row, marks: { "2": { kind: "pending" } } })).toBe(false);
    expect(editable(2, { ...row, saving: true })).toBe(false);
    const readOnly = buildColumnDefs({ columns: COLUMNS, baseDateColumnId: 1, canEnter: false, selectedColumnId: null });
    expect(editable(2, row, readOnly)).toBe(false);
  });

  it("선택 목록·예/아니오는 선택 편집기(빈 항목 포함)", () => {
    const choice = buildColumnDefs({ columns: [COL(9, "등급", "choice", { rules: { options: ["상", "중"] } }), COL(8, "승인", "boolean")], baseDateColumnId: null, canEnter: true, selectedColumnId: null });
    expect(choice[1]).toMatchObject({ cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", "상", "중"] } });
    expect(choice[2]).toMatchObject({ cellEditor: "agSelectCellEditor", cellEditorParams: { values: ["", "예", "아니오"] } });
  });

  it("선택된 열 머리글에 표시 클래스", () => {
    expect(defs[2].headerClass).toContain("header-selected");
    expect(defs[1].headerClass).not.toContain("header-selected");
  });
});

describe("기간/행 번호 열의 글자", () => {
  it("기준 날짜가 있으면 '기간 · #번호', 없으면 '#번호', 임시 행은 '새 행'", () => {
    const saved = fromServerRow({ row_id: 12, cells: { "1": "2026-03-01" } });
    expect(rowLabel(saved, COLUMNS, 1)).toBe("2026-03-01 · #12");
    expect(rowLabel(saved, COLUMNS, null)).toBe("#12");
    expect(rowLabel(emptyDraft(1), COLUMNS, 1)).toBe("새 행(저장 전)");
  });
});
