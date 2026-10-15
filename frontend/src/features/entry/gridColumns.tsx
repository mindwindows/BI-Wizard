import type { CellClassParams, ColDef, ValueFormatterParams, ValueGetterParams } from "ag-grid-community";
import type { CustomCellRendererProps } from "ag-grid-react";
import { COLUMN_TYPE_LABELS, type Column } from "../dataset/types";
import { REFERENCE_MISSING_CODE, REFERENCE_MISSING_LABEL, cellErrorText } from "../formula/messages";
import type { GridRow } from "./model";
import { BOOL_FALSE, BOOL_TRUE, displayText, editorText, computedFormatOf, formatComputedNumber, isBlank, isComputedNumber } from "./values";

export const ROW_COLUMN_ID = "__row";

/** 계산 열 칸을 고치려 할 때 보이는 안내 */
export const FORMULA_EDIT_NOTICE = "계산 열은 수식으로 계산되어 직접 고칠 수 없습니다. 수식은 Inspector에서 고칠 수 있습니다.";

export interface ColumnDefsInput {
  columns: Column[];
  baseDateColumnId: number | null;
  canEnter: boolean;
  selectedColumnId: number | null;
  /** D1 `cell_errors`(셀 오류 코드 -> 쉬운 말). 못 받았으면 기본 문구(formula/messages.ts)를 쓴다. */
  cellErrors?: Record<string, string>;
}

const colKey = (column: Column) => String(column.id);

/** 칸 위에 올리는 설명(툴팁/접근성). 표시 규칙의 단일 출처. */
export function cellTitle(column: Column, row: GridRow | undefined, cellErrors?: Record<string, string>): string {
  if (!row) return "";
  const key = colKey(column);
  const mark = row.marks[key];
  if (mark?.kind === "invalid") return mark.message;
  if (mark?.kind === "conflict") return "다른 사람이 먼저 바꾼 칸입니다. 아래 충돌 목록에서 내 값과 서버 값 중 고를 수 있습니다.";
  if (mark?.kind === "pending") return "저장하는 중입니다.";
  const code = row.errors[key];
  if (code) return `계산 오류(${code}): ${cellErrorText(code, cellErrors)}`;
  if (isComputedNumber(column) && !isBlank(row.cells[key])) {
    const shown = formatComputedNumber(String(row.cells[key]), computedFormatOf(column));
    // 소수 6자리(또는 열의 표시 자릿수)를 넘어 줄여 보이는 칸만 전체 값을 알려 준다(결정 2026-10-12).
    if (shown.truncated) return `전체 값: ${shown.full}`;
  }
  if (column.kind === "formula") return "계산 열은 수식으로 채워지므로 직접 고칠 수 없습니다.";
  if (isBlank(row.cells[key])) return "빈 칸(아직 입력하지 않음)";
  return "";
}

function EntryCell(props: CustomCellRendererProps<GridRow> & { entryColumn?: Column; cellErrors?: Record<string, string> }) {
  const column = props.entryColumn;
  const row = props.data;
  if (!row || !column) return null;
  const key = colKey(column);
  const errorCode = row.errors[key];
  const text = displayText(column, row.cells[key], errorCode);
  const blank = !errorCode && isBlank(row.cells[key]);
  const mark = row.marks[key];
  return (
    <span className="cell-text" title={cellTitle(column, row, props.cellErrors)}>
      <span className="cell-value">
        {errorCode ? <span aria-label={`계산 오류 ${errorCode}: ${cellErrorText(errorCode, props.cellErrors)}`}>{errorCode === REFERENCE_MISSING_CODE ? REFERENCE_MISSING_LABEL : "오류"}</span> : blank ? <span className="cell-blank-mark" aria-label="빈 칸" /> : text}
      </span>
      {errorCode ? <span className="cell-errcode" aria-hidden="true"> {errorCode}</span> : null}
      {mark?.kind === "invalid" ? <span className="cell-flag" aria-hidden="true"> !</span> : null}
      {mark?.kind === "conflict" ? <span className="cell-flag" aria-hidden="true"> 충돌</span> : null}
      {mark?.kind === "pending" ? <span className="cell-flag muted" aria-hidden="true"> …</span> : null}
    </span>
  );
}

/** 기간/행 번호 열의 글자 */
export function rowLabel(row: GridRow, columns: Column[], baseDateColumnId: number | null): string {
  if (row.entry) return "＋ 새 행 입력";
  if (row.draft) return "새 행(저장 전)";
  const base = baseDateColumnId === null ? undefined : columns.find((c) => c.id === baseDateColumnId);
  const period = base ? displayText(base, row.cells[colKey(base)]) : "";
  return period ? `${period} · #${row.rowId}` : `#${row.rowId}`;
}

export function buildColumnDefs(input: ColumnDefsInput): ColDef<GridRow>[] {
  const { columns, baseDateColumnId, canEnter, selectedColumnId, cellErrors } = input;
  const rowColumn: ColDef<GridRow> = {
    colId: ROW_COLUMN_ID,
    headerName: "기간 / 행 번호",
    pinned: "left",
    width: 170,
    editable: false,
    sortable: false,
    resizable: true,
    suppressMovable: true,
    valueGetter: (p: ValueGetterParams<GridRow>) => (p.data ? rowLabel(p.data, columns, baseDateColumnId) : ""),
    cellClass: (p: CellClassParams<GridRow>) => ["cell-rowlabel", p.data?.entry ? "cell-entry-label" : "", p.data?.draft && !p.data?.entry ? "cell-draft-label" : ""],
  };
  const dataColumns = columns.map<ColDef<GridRow>>((column) => {
    const key = colKey(column);
    const options = Array.isArray(column.rules?.options) ? (column.rules?.options as unknown[]).map(String) : [];
    const def: ColDef<GridRow> = {
      colId: key,
      headerName: column.id === baseDateColumnId ? `${column.display_name} (기간)` : column.display_name,
      headerTooltip: `${COLUMN_TYPE_LABELS[column.type] ?? column.type}${column.kind === "formula" ? " · 계산 열" : ""}${column.required ? " · 필수" : ""}`,
      headerClass: [column.id === selectedColumnId ? "header-selected" : "", column.kind === "formula" ? "header-formula" : ""],
      minWidth: 110,
      // 계산 열 값은 12~20자리까지 길어질 수 있어 기본 폭을 조금 넓힌다(값은 자르거나 반올림하지 않는다).
      ...(column.kind === "formula" ? { width: 190 } : {}),
      sortable: false,
      resizable: true,
      suppressMovable: true,
      editable: (p) => canEnter && column.kind === "raw" && !p.data?.saving && p.data?.marks[key]?.kind !== "pending",
      // 편집기에는 서식 없는 원래 값을 넣는다(표시 서식은 셀 렌더러가 만든다).
      valueGetter: (p: ValueGetterParams<GridRow>) => (p.data ? editorText(column, p.data.cells[key]) : ""),
      valueFormatter: (p: ValueFormatterParams<GridRow>) => (p.data ? displayText(column, p.data.cells[key], p.data.errors[key]) : ""),
      cellRenderer: EntryCell,
      cellRendererParams: { entryColumn: column, cellErrors },
      cellClass: (p: CellClassParams<GridRow>) => {
        const row = p.data;
        const mark = row?.marks[key];
        const classes = [`cell-${column.type}`];
        if (column.kind === "formula") classes.push("cell-formula");
        if (row?.errors[key]) classes.push("cell-error", ...(row.errors[key] === REFERENCE_MISSING_CODE ? ["cell-error-e4"] : []));
        else if (row && isBlank(row.cells[key])) classes.push("cell-blank");
        if (mark) classes.push(`cell-${mark.kind}`);
        if (row?.draft) classes.push("cell-draft");
        return classes;
      },
    };
    if (column.type === "choice") {
      def.cellEditor = "agSelectCellEditor";
      def.cellEditorParams = { values: ["", ...options] };
    } else if (column.type === "boolean") {
      def.cellEditor = "agSelectCellEditor";
      def.cellEditorParams = { values: ["", BOOL_TRUE, BOOL_FALSE] };
    }
    return def;
  });
  return [rowColumn, ...dataColumns];
}
