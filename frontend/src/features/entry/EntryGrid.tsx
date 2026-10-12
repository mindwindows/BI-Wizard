import {
  CellApiModule,
  CellStyleModule,
  ClientSideRowModelApiModule,
  ClientSideRowModelModule,
  CustomEditorModule,
  ModuleRegistry,
  PinnedRowModule,
  RenderApiModule,
  RowApiModule,
  RowStyleModule,
  ScrollApiModule,
  SelectEditorModule,
  TextEditorModule,
  TooltipModule,
  themeQuartz, type CellEditRequestEvent, type ColumnHeaderClickedEvent, type GridApi } from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useRef, type KeyboardEvent } from "react";
import { ErrorNotice, Loading } from "../../components";
import type { Column } from "../dataset/types";
import { ENTRY_ROW, type GridRow } from "./model";
import { PAGE_SIZES, useEntry, type EntryParams } from "./useEntry";
import { ROW_COLUMN_ID, buildColumnDefs } from "./gridColumns";
import { displayText } from "./values";

// AG Grid Community 모듈 중 이 화면이 쓰는 것만 등록한다(AllCommunityModule 대비 번들 약 20% 감소, ag-grid-enterprise는 설치하지 않는다).
// 모듈을 빠뜨리면 개발 모드에서 'AG Grid error #200'이 난다. 기능을 추가할 때는 ValidationModule을 잠깐 등록해 시험을 돌려 확인한다.
ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  ClientSideRowModelApiModule,
  PinnedRowModule,
  CellStyleModule,
  RowStyleModule,
  TextEditorModule,
  SelectEditorModule,
  CustomEditorModule,
  TooltipModule,
  RenderApiModule,
  RowApiModule,
  CellApiModule,
  ScrollApiModule,
]);

const theme = themeQuartz.withParams({ fontSize: 13, headerFontSize: 13, spacing: 4 });

export interface EntryGridProps extends Omit<EntryParams, "columns"> {
  columns: Column[];
  selectedColumnId: number | null;
  onSelectColumn: (columnId: number) => void;
  /** 그리드 API를 받는다(시험·자동화용: jsdom은 더블클릭으로 편집을 시작하지 못한다). */
  onGridApi?: (api: GridApi<GridRow>) => void;
}

const MAX_LISTED = 20;

/** S4 중앙 입력 그리드: 조회(C1)·칸 편집(C3)·임시 행(C2)·엑셀 붙여넣기(C4)·충돌 표시. */
export function EntryGrid(props: EntryGridProps) {
  const { columns, canEnter, baseDateColumnId, selectedColumnId, onSelectColumn, onGridApi } = props;
  const entry = useEntry(props);
  const apiRef = useRef<GridApi<GridRow> | null>(null);

  const columnDefs = useMemo(
    () => buildColumnDefs({ columns, baseDateColumnId, canEnter, selectedColumnId }),
    [columns, baseDateColumnId, canEnter, selectedColumnId],
  );
  const rowData = useMemo(() => [...entry.rows, ...entry.drafts], [entry.rows, entry.drafts]);
  const pinnedBottom = useMemo(() => (canEnter ? [ENTRY_ROW] : []), [canEnter]);

  // 값은 그대로인데 표시(입력 오류·충돌·저장 중)만 바뀐 칸도 다시 그리도록, 바뀐 행의 칸을 강제로 갱신한다.
  // (AG Grid는 칸의 값이 바뀌지 않으면 칸 스타일을 다시 계산하지 않는다.)
  const previousRows = useRef<Map<string, GridRow>>(new Map());
  useEffect(() => {
    const api = apiRef.current;
    const changed = rowData.filter((r) => previousRows.current.has(r.key) && previousRows.current.get(r.key) !== r);
    previousRows.current = new Map(rowData.map((r) => [r.key, r]));
    if (!api || changed.length === 0) return;
    const nodes = changed.flatMap((r) => {
      const node = api.getRowNode(r.key);
      return node ? [node] : [];
    });
    if (nodes.length > 0) api.refreshCells({ rowNodes: nodes, force: true });
  }, [rowData]);

  // 새 행 추가 버튼: 새 임시 행의 첫 입력 칸으로 이동해 바로 편집을 시작한다.
  const focusTick = entry.focusRequest?.tick;
  const focusKey = entry.focusRequest?.rowKey;
  useEffect(() => {
    if (focusTick === undefined || !focusKey) return;
    const timer = setTimeout(() => {
      const api = apiRef.current;
      const index = rowData.findIndex((r) => r.key === focusKey);
      const first = columns.find((c) => c.kind === "raw");
      if (!api || index < 0 || !first) return;
      api.ensureIndexVisible(index);
      api.setFocusedCell(index, String(first.id));
      api.startEditingCell({ rowIndex: index, colKey: String(first.id) });
    }, 0);
    return () => clearTimeout(timer);
    // rowData는 일부러 뺀다: 새 행이 생긴 뒤 한 번만 이동한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusTick, focusKey]);

  const onEditRequest = useCallback(
    (event: CellEditRequestEvent<GridRow>) => {
      const colId = event.colDef.colId;
      const data = event.data;
      if (!colId || colId === ROW_COLUMN_ID || !data) return;
      const text = event.newValue == null ? "" : String(event.newValue);
      const columnId = Number(colId);
      if (data.entry) entry.editEntryCell(columnId, text);
      else entry.editDraftOrSaved(data.key, columnId, text);
    },
    [entry],
  );

  const onHeaderClicked = useCallback(
    (event: ColumnHeaderClickedEvent<GridRow>) => {
      const column = event.column;
      if (!("getColId" in column)) return;
      const id = column.getColId();
      if (id !== ROW_COLUMN_ID) onSelectColumn(Number(id));
    },
    [onSelectColumn],
  );

  // 붙여넣기는 document 수준에서 받는다. 래퍼 div의 onPaste만 쓰면, 그리드 밖 글자(안내 문단 등)가 선택된 채로 칸을 눌러도
  // 브라우저가 paste 대상을 '선택된 요소'로 정해 이벤트가 그리드에 닿지 않는다(QA F-1).
  // 처리 조건: 대상이 그리드 안이거나, 지금 DOM 포커스(activeElement)가 그리드 안일 때. 대상이 입력창·편집기면 기본 동작을 그대로 둔다.
  // jsdom은 선택된 글자 때문에 대상이 바뀌는 동작을 만들지 못하므로, 시험은 대상을 그리드 밖 요소로 보내 흉내 낸다.
  const gridRef = useRef<HTMLDivElement | null>(null);
  const pasteHandler = useRef<(event: globalThis.ClipboardEvent) => void>(() => undefined);
  const handlePaste = (event: globalThis.ClipboardEvent) => {
    const wrapper = gridRef.current;
    if (!wrapper) return;
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("input, textarea, select, [contenteditable]:not([contenteditable='false'])")) return;
    const active = document.activeElement;
    const inGrid = (target !== null && wrapper.contains(target)) || (active !== null && wrapper.contains(active));
    if (!inGrid) return;
    event.preventDefault();
    const text = event.clipboardData?.getData("text/plain") ?? "";
    const focused = apiRef.current?.getFocusedCell();
    if (!focused) {
      entry.requestPaste(text, null, -1);
      return;
    }
    const colId = focused.column.getColId();
    const startColumn = colId === ROW_COLUMN_ID ? 0 : columns.findIndex((c) => String(c.id) === colId);
    const inNewArea = focused.rowPinned === "bottom" || focused.rowIndex >= entry.rows.length;
    entry.requestPaste(text, inNewArea ? null : focused.rowIndex, startColumn);
  };
  useEffect(() => {
    pasteHandler.current = handlePaste; // 매 렌더 뒤 최신 상태(entry·columns)를 쓰는 처리기로 바꾼다
  });
  useEffect(() => {
    const listener = (event: globalThis.ClipboardEvent) => pasteHandler.current(event);
    document.addEventListener("paste", listener);
    return () => document.removeEventListener("paste", listener);
  }, []);

  function onPanelKey(event: KeyboardEvent<HTMLElement>, close: () => void) {
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    }
  }

  const conflicts = entry.rows.flatMap((row) =>
    Object.entries(row.marks).flatMap(([columnKey, mark]) => (mark.kind === "conflict" ? [{ row, columnId: Number(columnKey), mark }] : [])),
  );
  const invalids = [...entry.rows, ...entry.drafts].flatMap((row) =>
    Object.entries(row.marks).flatMap(([columnKey, mark]) => (mark.kind === "invalid" ? [{ row, columnId: Number(columnKey), message: mark.message }] : [])),
  );
  const columnName = (id: number) => columns.find((c) => c.id === id)?.display_name ?? "열";
  const rowName = (row: GridRow) => (row.rowId === null ? "새 행" : `행 #${row.rowId}`);
  const showText = (columnId: number, value: Parameters<typeof displayText>[1]) => {
    const column = columns.find((c) => c.id === columnId);
    const text = column ? displayText(column, value) : String(value ?? "");
    return text === "" ? "(빈 칸)" : text;
  };

  const lastShown = entry.offset + entry.rows.length;
  const hasPrev = entry.offset > 0;
  const hasNext = lastShown < entry.total;
  const firstLoad = entry.status === "loading" && entry.rows.length === 0 && entry.drafts.length === 0;

  return (
    <section aria-label="입력 그리드" className="entry">
      <div className="entry-toolbar">
        <label>
          정렬{" "}
          <select aria-label="정렬 순서" value={entry.order} onChange={(e) => entry.setOrder(e.target.value === "asc" ? "asc" : "desc")}>
            <option value="desc">최근 순</option>
            <option value="asc">과거 순</option>
          </select>
        </label>
        <label>
          한 쪽에{" "}
          <select aria-label="한 쪽 행 수" value={entry.limit} onChange={(e) => entry.setLimit(Number(e.target.value))}>
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}행
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => entry.goTo(entry.offset - entry.limit)} disabled={!hasPrev || entry.status === "loading"}>
          이전 쪽
        </button>
        <span aria-live="polite" className="entry-range">
          {entry.total === 0 ? "0행" : `${entry.offset + 1}–${lastShown} / 전체 ${entry.total}행`}
        </span>
        <button type="button" onClick={() => entry.goTo(entry.offset + entry.limit)} disabled={!hasNext || entry.status === "loading"}>
          다음 쪽
        </button>
        <button type="button" onClick={entry.reload} disabled={entry.status === "loading"}>
          새로 읽기
        </button>
        {canEnter ? (
          <button type="button" className="primary" onClick={() => entry.addDraft()}>
            새 행 추가
          </button>
        ) : null}
      </div>

      {canEnter ? (
        <p className="muted entry-help">
          칸을 두 번 누르거나 Enter를 눌러 고칩니다(Enter 저장, Esc 취소, Tab 다음 칸). 엑셀에서 복사한 표는 시작할 칸을 누르고 Ctrl+V로 붙여넣습니다. 맨 아래 &quot;새 행 입력&quot; 줄에
          입력하면 임시 행이 되고, 필수 칸을 모두 채우면 저장됩니다. 저장 전 임시 행은 새로고침하면 사라집니다.
        </p>
      ) : (
        <p className="state-readonly" role="note">
          읽기 전용입니다. 이 팀의 입력 권한이 없어 값을 볼 수만 있습니다.
        </p>
      )}

      <div className="entry-notices">
        {entry.notices.map((notice) => (
          <div key={notice.id} role={notice.kind === "error" ? "alert" : "status"} className={`notice notice-${notice.kind}`}>
            <span>{notice.text}</span>
            {notice.retry ? (
              <button type="button" onClick={() => { notice.retry?.(); entry.dismissNotice(notice.id); }}>
                다시 시도
              </button>
            ) : null}
            <button type="button" onClick={() => entry.dismissNotice(notice.id)} aria-label="안내 닫기">
              닫기
            </button>
          </div>
        ))}
      </div>

      {conflicts.length > 0 ? (
        <section aria-label="충돌 목록" role="alert" className="panel panel-conflict">
          <h3>다른 사람이 먼저 바꾼 칸 {conflicts.length}건</h3>
          <ul>
            {conflicts.map(({ row, columnId, mark }) => (
              <li key={`${row.key}:${columnId}`}>
                {rowName(row)} · {columnName(columnId)} — 내 값 &quot;{mark.mine === "" ? "(빈 칸)" : mark.mine}&quot;, 서버 값 &quot;{showText(columnId, mark.current)}&quot;{" "}
                <button type="button" onClick={() => entry.resolveConflict(row.key, columnId, "mine")}>
                  내 값으로 저장
                </button>{" "}
                <button type="button" onClick={() => entry.resolveConflict(row.key, columnId, "server")}>
                  서버 값 유지
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {invalids.length > 0 ? (
        <section aria-label="확인이 필요한 칸" role="alert" className="panel panel-invalid">
          <h3>확인이 필요한 칸 {invalids.length}건</h3>
          <ul>
            {invalids.map(({ row, columnId, message }) => (
              <li key={`${row.key}:${columnId}`}>
                {rowName(row)} · {columnName(columnId)}: {message}{" "}
                <button type="button" onClick={() => entry.dismissMark(row.key, columnId)}>
                  닫기
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {entry.drafts.length > 0 ? (
        <section aria-label="저장 전 새 행" className="panel panel-draft">
          <h3>저장 전 새 행 {entry.drafts.length}개</h3>
          <p className="muted">서버에는 아직 저장되지 않았습니다. 필수 칸을 모두 채우면 저장되며, 새로고침하면 사라집니다.</p>
          <ul>
            {entry.drafts.map((draft, index) => {
              const missing = entry.missingFor(draft);
              const ready = entry.saveableDraftKeys.includes(draft.key);
              return (
                <li key={draft.key}>
                  임시 행 {index + 1}:{" "}
                  {draft.saving
                    ? "저장하는 중…"
                    : draft.issue
                      ? draft.issue
                      : missing.length > 0
                        ? `채워야 할 필수 칸 — ${missing.map((c) => c.display_name).join(", ")}`
                        : "저장할 준비가 됐습니다."}{" "}
                  {ready && !draft.saving ? (
                    <button type="button" onClick={() => void entry.saveDraft(draft.key)}>
                      다시 저장
                    </button>
                  ) : null}{" "}
                  <button type="button" onClick={() => entry.discardDraft(draft.key)} disabled={draft.saving}>
                    버리기
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <PastePanel entry={entry} onKey={onPanelKey} />

      {entry.status === "error" && rowData.length === 0 ? (
        <ErrorNotice error={entry.loadError}>
          <button type="button" onClick={entry.reload}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {firstLoad ? <Loading label="행을 불러오는 중" /> : null}
      {entry.status === "ready" && entry.total === 0 && entry.drafts.length === 0 ? (
        <p className="muted" data-testid="no-rows">
          {canEnter ? "아직 입력된 행이 없습니다. 맨 아래 줄에 입력하거나 엑셀에서 복사해 붙여넣어 보세요." : "아직 입력된 행이 없습니다."}
        </p>
      ) : null}
      {entry.status === "loading" && !firstLoad ? <Loading label="행을 불러오는 중" /> : null}

      {firstLoad || (entry.status === "error" && rowData.length === 0) ? null : (
        <div className="entry-grid" role="group" aria-label="입력 그리드 표" ref={gridRef}>
          <AgGridReact<GridRow>
            theme={theme}
            columnDefs={columnDefs}
            rowData={rowData}
            pinnedBottomRowData={pinnedBottom}
            getRowId={(p) => p.data.key}
            readOnlyEdit
            onCellEditRequest={onEditRequest}
            onColumnHeaderClicked={onHeaderClicked}
            onGridReady={(e) => {
              apiRef.current = e.api;
              onGridApi?.(e.api);
            }}
            stopEditingWhenCellsLoseFocus
            enterNavigatesVertically
            enterNavigatesVerticallyAfterEdit
            suppressNoRowsOverlay
            suppressColumnVirtualisation
            suppressMovableColumns
            getRowClass={(p) => (p.data?.draft ? "row-draft" : undefined)}
          />
        </div>
      )}
    </section>
  );
}

function PastePanel({ entry, onKey }: { entry: ReturnType<typeof useEntry>; onKey: (event: KeyboardEvent<HTMLElement>, close: () => void) => void }) {
  const paste = entry.paste;
  if (!paste) return null;
  if (paste.stage === "sending") {
    return (
      <p role="status" className="state state-loading">
        붙여넣는 중…
      </p>
    );
  }
  if (paste.stage === "problems") {
    const listed = paste.problems.slice(0, MAX_LISTED);
    return (
      <section aria-label="붙여넣기 오류" role="alert" className="panel panel-invalid" onKeyDown={(e) => onKey(e, entry.cancelPaste)}>
        <h3>붙여넣을 수 없습니다</h3>
        <p className="muted">아무것도 저장하지 않았습니다.</p>
        <ul>
          {listed.map((problem, index) => (
            <li key={index}>
              {problem.line ? `${problem.line}번째 줄 · ` : ""}
              {problem.column ? `${problem.column}: ` : ""}
              {problem.message}
            </li>
          ))}
        </ul>
        <button type="button" onClick={entry.cancelPaste} autoFocus>
          닫기
        </button>
      </section>
    );
  }
  if (paste.stage === "confirm") {
    const { plan } = paste;
    const first = plan.columnNames[0];
    const last = plan.columnNames[plan.columnNames.length - 1];
    return (
      <section aria-label="붙여넣기 확인" role="dialog" className="panel panel-confirm" onKeyDown={(e) => onKey(e, entry.cancelPaste)}>
        <h3>붙여넣기 확인</h3>
        <p>
          {plan.request.rows.length}줄 × {plan.columnNames.length}열을 &quot;{first}&quot;
          {plan.columnNames.length > 1 ? ` ~ "${last}"` : ""} 칸에 붙여넣습니다.
        </p>
        <p>
          기존 행 {plan.existingRows}개의 값을 덮어쓰고, 새 행 {plan.newRows}개를 추가합니다. 충돌이 하나라도 있으면 전부 취소됩니다.
        </p>
        <button type="button" className="primary" onClick={() => void entry.applyPaste(plan)} autoFocus>
          붙여넣기 적용
        </button>{" "}
        <button type="button" onClick={entry.cancelPaste}>
          취소
        </button>
      </section>
    );
  }
  const listed = paste.items.slice(0, MAX_LISTED);
  return (
    <section
      aria-label="붙여넣기 결과"
      role={paste.kind === "ok" ? "status" : "alert"}
      className={`panel ${paste.kind === "ok" ? "panel-ok" : "panel-invalid"}`}
      onKeyDown={(e) => onKey(e, entry.cancelPaste)}
    >
      <p>{paste.headline}</p>
      {listed.length > 0 ? (
        <ul>
          {listed.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      ) : null}
      {paste.items.length > MAX_LISTED ? <p className="muted">외 {paste.items.length - MAX_LISTED}건</p> : null}
      {paste.kind === "conflict" && paste.canRetry ? (
        <button type="button" onClick={entry.replanPaste}>
          서버 값 기준으로 다시 붙여넣기
        </button>
      ) : null}{" "}
      {paste.retry ? (
        <button type="button" onClick={paste.retry}>
          다시 시도
        </button>
      ) : null}{" "}
      <button type="button" onClick={entry.cancelPaste}>
        닫기
      </button>
    </section>
  );
}
