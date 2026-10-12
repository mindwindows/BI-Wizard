import { useCallback, useEffect, useRef, useState } from "react";
import { describeApiError, truncationText } from "../../errors";
import type { Column } from "../dataset/types";
import { createRow, listRows, pasteRows, patchRow } from "./api";
import { conflictsOf, describeFieldCode, describePasteError, fieldIssuesOf, isCode } from "./messages";
import {
  type GridRow,
  type Mark,
  cellOf,
  createCells,
  draftReady,
  emptyDraft,
  fromServerRow,
  missingRequired,
  withCell,
  withMark,
} from "./model";
import { buildPastePlan, type PasteProblem, type PastePlan } from "./paste/plan";
import { parsePaste } from "./paste/parser";
import type { CellValue, Row, RowOrder, RowsPage } from "./types";
import { displayText, parseEditInput, sameValue } from "./values";

export interface EntryParams {
  datasetId: number;
  /** 화면에 보이는 열(위치 순) */
  columns: Column[];
  baseDateColumnId: number | null;
  canEnter: boolean;
  /** 가장 최근에 알게 된 정의 버전(expected_version) */
  getVersion: () => number;
  /** 서버가 알려 준 버전(C1·C2~C4 응답). 더 크면 정의가 바뀐 것이다. */
  onVersion: (version: number) => void;
  /** 정의를 다시 읽는다(DEFINITION_VERSION_MISMATCH) */
  onDefinitionStale: () => Promise<void>;
}

export interface Notice {
  id: number;
  kind: "ok" | "error" | "info";
  text: string;
  retry?: () => void;
}

export type PasteUi =
  | null
  | { stage: "problems"; problems: PasteProblem[] }
  | { stage: "confirm"; plan: PastePlan }
  | { stage: "sending" }
  | { stage: "result"; kind: "ok" | "conflict" | "invalid" | "error"; headline: string; items: string[]; canRetry: boolean; retry?: () => void; truncated?: string };

export type LoadStatus = "loading" | "ready" | "error";

interface PasteMemo {
  matrix: string[][];
  startRow: number | null;
  startColumn: number;
}

export const PAGE_SIZES = [50, 100, 200] as const;

export function useEntry(params: EntryParams) {
  const [order, setOrderState] = useState<RowOrder>("desc");
  const [limit, setLimitState] = useState<number>(50);
  const [offset, setOffset] = useState(0);
  const [reloadToken, setReloadToken] = useState(0);
  const [result, setResult] = useState<{ key: string; page?: RowsPage; error?: unknown } | null>(null);
  const [rows, setRows] = useState<GridRow[]>([]);
  const [drafts, setDrafts] = useState<GridRow[]>([]);
  const [notices, setNotices] = useState<Notice[]>([]);
  const [paste, setPaste] = useState<PasteUi>(null);
  const [focusRequest, setFocusRequest] = useState<{ rowKey: string; tick: number } | null>(null);

  const rowsRef = useRef<GridRow[]>([]);
  const draftsRef = useRef<GridRow[]>([]);
  const paramsRef = useRef(params);
  const nextId = useRef(1);
  const pasteMemo = useRef<PasteMemo | null>(null);
  // 다시 시도 버튼이 최신 함수를 부르도록 자기 자신을 ref로 들고 있는다(useCallback 안에서 자기 참조를 피함).
  const retryRef = useRef<{
    editCell: (rowKey: string, columnId: number, text: string) => Promise<void>;
    saveDraft: (draftKey: string) => Promise<void>;
    applyPaste: (plan: PastePlan) => Promise<void>;
  } | null>(null);
  useEffect(() => {
    paramsRef.current = params;
  });

  const updateRows = useCallback((change: (current: GridRow[]) => GridRow[]) => {
    rowsRef.current = change(rowsRef.current);
    setRows(rowsRef.current);
  }, []);
  const updateDrafts = useCallback((change: (current: GridRow[]) => GridRow[]) => {
    draftsRef.current = change(draftsRef.current);
    setDrafts(draftsRef.current);
  }, []);
  const patchRowByKey = useCallback(
    (key: string, change: (row: GridRow) => GridRow) => {
      updateRows((current) => current.map((row) => (row.key === key ? change(row) : row)));
    },
    [updateRows],
  );
  const patchDraftByKey = useCallback(
    (key: string, change: (row: GridRow) => GridRow) => {
      updateDrafts((current) => current.map((row) => (row.key === key ? change(row) : row)));
    },
    [updateDrafts],
  );

  const notify = useCallback((kind: Notice["kind"], text: string, retry?: () => void) => {
    const id = nextId.current++;
    setNotices((current) => [...current.filter((n) => n.text !== text), { id, kind, text, retry }].slice(-5));
  }, []);
  const dismissNotice = useCallback((id: number) => setNotices((current) => current.filter((n) => n.id !== id)), []);
  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  // ---- C1 읽기 -------------------------------------------------------------------------------------------------
  const key = `${params.datasetId}:${order}:${limit}:${offset}:${reloadToken}`;
  useEffect(() => {
    const controller = new AbortController();
    listRows(params.datasetId, { order, limit, offset }, controller.signal)
      .then((page) => {
        if (controller.signal.aborted) return;
        rowsRef.current = page.items.map(fromServerRow);
        setRows(rowsRef.current);
        setResult({ key, page });
        paramsRef.current.onVersion(page.def_version);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setResult({ key, error });
      });
    return () => controller.abort();
  }, [key, params.datasetId, order, limit, offset]);

  const status: LoadStatus = result?.key === key ? (result.error !== undefined ? "error" : "ready") : "loading";
  const page = result?.page;
  const total = page?.total ?? 0;
  const loadError = result?.key === key ? result.error : undefined;

  const setOrder = useCallback((next: RowOrder) => {
    setOrderState(next);
    setOffset(0);
    setPaste(null);
  }, []);
  const setLimit = useCallback((next: number) => {
    setLimitState(next);
    setOffset(0);
    setPaste(null);
  }, []);
  const goTo = useCallback((next: number) => {
    setOffset(Math.max(0, next));
    setPaste(null);
  }, []);

  const columnById = useCallback((id: number): Column | undefined => paramsRef.current.columns.find((c) => c.id === id), []);

  // ---- 공통 오류 처리 ------------------------------------------------------------------------------------------
  /** 정의가 바뀌었다: 정의를 다시 읽고 행도 다시 읽는다. */
  const handleStale = useCallback(
    async (error: unknown) => {
      notify("error", describeApiError(error));
      await paramsRef.current.onDefinitionStale();
      reload();
    },
    [notify, reload],
  );

  // ---- C3 칸 편집 ----------------------------------------------------------------------------------------------
  const editCell = useCallback(
    async (rowKey: string, columnId: number, text: string): Promise<void> => {
      const column = columnById(columnId);
      const row = rowsRef.current.find((r) => r.key === rowKey);
      if (!column || !row || row.rowId === null) return;
      const rowId = row.rowId;
      const parsed = parseEditInput(column, text);
      if (!parsed.ok) {
        patchRowByKey(rowKey, (r) => withMark(r, columnId, { kind: "invalid", message: parsed.message }));
        return;
      }
      const before = cellOf(row, columnId);
      if (sameValue(before, parsed.value)) {
        patchRowByKey(rowKey, (r) => withMark(r, columnId, null));
        return;
      }
      const value = parsed.value;
      // 낙관적 표시: 값을 바꿔 보이고 저장 중 표시를 단다. 실패하면 아래에서 되돌린다.
      patchRowByKey(rowKey, (r) => withMark(withCell(r, columnId, value), columnId, { kind: "pending" }));
      const revert = () => patchRowByKey(rowKey, (r) => withMark(withCell(r, columnId, before), columnId, null));
      try {
        const saved = await patchRow(paramsRef.current.datasetId, rowId, {
          expected_version: paramsRef.current.getVersion(),
          changes: [{ column_id: columnId, expected: before, value }],
        });
        paramsRef.current.onVersion(saved.def_version);
        patchRowByKey(rowKey, (r) => mergeServerRow(r, saved.row, columnId));
      } catch (error) {
        if (isCode(error, "CELL_CONFLICT")) {
          const hit = conflictsOf(error).find((c) => c.column_id === columnId) ?? conflictsOf(error)[0];
          const current: CellValue = hit ? hit.current : before;
          // 화면에는 서버의 현재 값을 보이고, 내 값은 충돌 표시에 남겨 둔다.
          patchRowByKey(rowKey, (r) => withMark(withCell(r, columnId, current), columnId, { kind: "conflict", mine: text, current, source: "edit" }));
          return;
        }
        revert();
        if (isCode(error, "PERIOD_CONFLICT")) {
          patchRowByKey(rowKey, (r) => withMark(r, columnId, { kind: "invalid", message: "이미 같은 기간의 행이 있습니다." }));
        } else if (isCode(error, "VALIDATION_ERROR")) {
          markFieldIssues(error, rowKey, columnId, column, patchRowByKey, undefined, paramsRef.current.columns);
        } else if (isCode(error, "DEFINITION_VERSION_MISMATCH")) {
          await handleStale(error);
        } else if (isCode(error, "WRITE_BUSY") || isCode(error, "DEFINITION_BUSY")) {
          notify("error", describeApiError(error), () => void retryRef.current?.editCell(rowKey, columnId, text));
        } else if (isCode(error, "ROW_NOT_FOUND")) {
          notify("error", describeApiError(error));
          reload();
        } else {
          notify("error", describeApiError(error));
        }
      }
    },
    [columnById, handleStale, notify, patchRowByKey, reload],
  );

  /** 충돌 해결: 내 값으로 다시 저장(기대값은 방금 본 서버 값) 또는 서버 값 유지. */
  const resolveConflict = useCallback(
    (rowKey: string, columnId: number, choice: "mine" | "server") => {
      const row = rowsRef.current.find((r) => r.key === rowKey);
      const mark = row?.marks[String(columnId)];
      if (!row || mark?.kind !== "conflict") return;
      patchRowByKey(rowKey, (r) => withMark(r, columnId, null));
      if (choice === "mine") void editCell(rowKey, columnId, mark.mine);
    },
    [editCell, patchRowByKey],
  );

  // ---- C2 임시 행 ---------------------------------------------------------------------------------------------
  const saveDraft = useCallback(
    async (draftKey: string): Promise<void> => {
      const draft = draftsRef.current.find((d) => d.key === draftKey);
      if (!draft || draft.saving) return;
      const { columns, baseDateColumnId } = paramsRef.current;
      if (!draftReady(columns, baseDateColumnId, draft.cells)) return;
      patchDraftByKey(draftKey, (d) => ({ ...d, saving: true, issue: null }));
      try {
        const saved = await createRow(paramsRef.current.datasetId, {
          expected_version: paramsRef.current.getVersion(),
          cells: createCells(columns, draft.cells),
        });
        paramsRef.current.onVersion(saved.def_version);
        updateDrafts((current) => current.filter((d) => d.key !== draftKey));
        notify("ok", "새 행을 저장했습니다.");
        reload();
      } catch (error) {
        patchDraftByKey(draftKey, (d) => ({ ...d, saving: false }));
        if (isCode(error, "PERIOD_CONFLICT")) {
          const message = "이미 같은 기간의 행이 있습니다. 기간을 바꾸거나 기존 행을 고쳐 주세요.";
          patchDraftByKey(draftKey, (d) => ({ ...d, issue: message }));
          if (baseDateColumnId !== null) patchDraftByKey(draftKey, (d) => withMark(d, baseDateColumnId, { kind: "invalid", message }));
        } else if (isCode(error, "VALIDATION_ERROR")) {
          markFieldIssues(error, draftKey, null, undefined, patchDraftByKey, (text) => patchDraftByKey(draftKey, (d) => ({ ...d, issue: text })), columns);
        } else if (isCode(error, "DEFINITION_VERSION_MISMATCH")) {
          patchDraftByKey(draftKey, (d) => ({ ...d, issue: "정의가 바뀌었습니다. 다시 읽었으니 확인한 뒤 '다시 저장'을 눌러 주세요." }));
          await handleStale(error);
        } else if (isCode(error, "WRITE_BUSY") || isCode(error, "DEFINITION_BUSY")) {
          patchDraftByKey(draftKey, (d) => ({ ...d, issue: "다른 작업이 진행 중입니다. '다시 저장'을 눌러 주세요." }));
          notify("error", describeApiError(error), () => void retryRef.current?.saveDraft(draftKey));
        } else {
          const message = describeApiError(error);
          patchDraftByKey(draftKey, (d) => ({ ...d, issue: message }));
        }
      }
    },
    [handleStale, notify, patchDraftByKey, reload, updateDrafts],
  );

  const addDraft = useCallback((): string => {
    const draft = emptyDraft(nextId.current++);
    updateDrafts((current) => [...current, draft]);
    setFocusRequest((previous) => ({ rowKey: draft.key, tick: (previous?.tick ?? 0) + 1 }));
    return draft.key;
  }, [updateDrafts]);

  /** 칸 옆 안내(입력 오류 표시)를 닫는다. */
  const dismissMark = useCallback(
    (rowKey: string, columnId: number) => {
      if (rowKey.startsWith("d")) patchDraftByKey(rowKey, (r) => withMark(r, columnId, null));
      else patchRowByKey(rowKey, (r) => withMark(r, columnId, null));
    },
    [patchDraftByKey, patchRowByKey],
  );

  const discardDraft = useCallback((draftKey: string) => updateDrafts((current) => current.filter((d) => d.key !== draftKey)), [updateDrafts]);

  const applyDraftEdit = useCallback(
    (draftKey: string, columnId: number, text: string) => {
      const column = columnById(columnId);
      const draft = draftsRef.current.find((d) => d.key === draftKey);
      if (!column || !draft || draft.saving) return;
      const parsed = parseEditInput(column, text);
      if (!parsed.ok) {
        patchDraftByKey(draftKey, (d) => withMark(d, columnId, { kind: "invalid", message: parsed.message }));
        return;
      }
      patchDraftByKey(draftKey, (d) => ({ ...withMark(withCell(d, columnId, parsed.value), columnId, null), issue: null }));
      const next = { ...draft.cells, [String(columnId)]: parsed.value };
      if (draftReady(paramsRef.current.columns, paramsRef.current.baseDateColumnId, next)) void saveDraft(draftKey);
    },
    [columnById, patchDraftByKey, saveDraft],
  );

  /** 맨 아래 '새 행 입력' 줄에 입력하면 임시 행이 만들어진다. */
  const editEntryCell = useCallback(
    (columnId: number, text: string) => {
      const column = columnById(columnId);
      if (!column || text === "") return;
      const parsed = parseEditInput(column, text);
      const draft = emptyDraft(nextId.current++);
      updateDrafts((current) => [...current, draft]);
      if (!parsed.ok) {
        patchDraftByKey(draft.key, (d) => withMark(d, columnId, { kind: "invalid", message: parsed.message }));
        return;
      }
      applyDraftEdit(draft.key, columnId, text);
    },
    [applyDraftEdit, columnById, patchDraftByKey, updateDrafts],
  );

  const editDraftOrSaved = useCallback(
    (rowKey: string, columnId: number, text: string) => {
      if (rowKey.startsWith("d")) applyDraftEdit(rowKey, columnId, text);
      else void editCell(rowKey, columnId, text);
    },
    [applyDraftEdit, editCell],
  );

  // ---- C4 붙여넣기 ----------------------------------------------------------------------------------------------
  const planPaste = useCallback((memo: PasteMemo) => {
    const { columns, baseDateColumnId, getVersion } = paramsRef.current;
    const built = buildPastePlan({
      matrix: memo.matrix,
      columns,
      savedRows: rowsRef.current.map((r) => ({ row_id: r.rowId as number, cells: r.cells })),
      startRow: memo.startRow,
      startColumn: memo.startColumn,
      isLastPage: offset + rowsRef.current.length >= (page?.total ?? 0),
      baseDateColumnId,
      expectedVersion: getVersion(),
    });
    pasteMemo.current = memo;
    setPaste(built.ok ? { stage: "confirm", plan: built.plan } : { stage: "problems", problems: built.problems });
  }, [offset, page?.total]);

  /** 붙여넣기 이벤트의 text/plain을 받는다. startColumn < 0 이면 시작 칸이 없다는 뜻이다. */
  const requestPaste = useCallback(
    (text: string, startRow: number | null, startColumn: number) => {
      if (!paramsRef.current.canEnter) {
        setPaste({ stage: "problems", problems: [{ message: "이 데이터셋은 읽기 전용이라 붙여넣을 수 없습니다. 입력 권한이 필요합니다." }] });
        return;
      }
      if (startColumn < 0) {
        setPaste({ stage: "problems", problems: [{ message: "붙여넣기를 시작할 칸을 먼저 눌러 선택해 주세요." }] });
        return;
      }
      const parsed = parsePaste(text);
      if (!parsed.ok) {
        setPaste({ stage: "problems", problems: [{ message: parsed.message }] });
        return;
      }
      planPaste({ matrix: parsed.rows, startRow, startColumn });
    },
    [planPaste],
  );

  const cancelPaste = useCallback(() => setPaste(null), []);

  const applyPaste = useCallback(
    async (plan: PastePlan): Promise<void> => {
      setPaste({ stage: "sending" });
      const request = { ...plan.request, expected_version: paramsRef.current.getVersion() };
      const retry = () => void retryRef.current?.applyPaste(plan);
      try {
        const done = await pasteRows(paramsRef.current.datasetId, request);
        paramsRef.current.onVersion(done.def_version);
        setPaste({
          stage: "result",
          kind: "ok",
          headline: `붙여넣기를 마쳤습니다. ${done.updated}행을 고치고 ${done.created}행을 새로 추가했습니다.`,
          items: [],
          canRetry: false,
        });
        reload();
      } catch (error) {
        if (isCode(error, "PASTE_CONFLICT")) {
          const items: string[] = [];
          for (const conflict of conflictsOf(error)) {
            const column = conflict.column_id === null ? undefined : columnById(conflict.column_id);
            const name = column?.display_name ?? "열";
            const line = conflict.row_index === undefined ? "" : `${conflict.row_index + 1}번째 줄 · `;
            if (conflict.kind === "period") {
              items.push(`${line}새 행의 기간이 이미 있습니다.`);
            } else if (conflict.kind === "row_missing") {
              items.push(`${line}행 #${conflict.row_id ?? "?"}이(가) 사라졌습니다(다른 사람이 지웠을 수 있습니다).`);
            } else {
              items.push(`${line}행 #${conflict.row_id ?? "?"} · ${name}: 서버에는 "${column ? displayText(column, conflict.current) : String(conflict.current ?? "")}" 값이 있습니다.`);
              if (conflict.row_id !== null && conflict.column_id !== null && column) {
                const columnId = conflict.column_id;
                const pasted = conflict.row_index === undefined ? undefined : request.rows[conflict.row_index]?.values[request.column_ids.indexOf(columnId)];
                patchRowByKey(`r${conflict.row_id}`, (r) =>
                  withMark(withCell(r, columnId, conflict.current), columnId, {
                    kind: "conflict",
                    mine: pasted ?? "",
                    current: conflict.current,
                    source: "paste",
                  }),
                );
              }
            }
          }
          setPaste({
            stage: "result",
            kind: "conflict",
            headline: "다른 사람이 먼저 바꾼 내용이 있어 붙여넣기를 취소했습니다. 일부만 반영되는 일은 없으며 아무것도 저장되지 않았습니다.",
            items,
            canRetry: pasteMemo.current !== null,
            truncated: truncationText(error) || undefined,
          });
        } else if (isCode(error, "VALIDATION_ERROR")) {
          const items = fieldIssuesOf(error).map((issue) => {
            const column = issue.column_id === undefined ? undefined : columnById(issue.column_id);
            const where = issue.row_index === undefined ? "" : `${issue.row_index + 1}번째 줄 · `;
            return `${where}${column?.display_name ?? issue.field ?? "값"}: ${describeFieldCode(issue.code, column)}`;
          });
          for (const issue of fieldIssuesOf(error)) {
            if (issue.row_index === undefined || issue.column_id === undefined) continue;
            const rowId = request.rows[issue.row_index]?.row_id;
            const column = columnById(issue.column_id);
            if (rowId === null || rowId === undefined || !column) continue;
            const columnId = column.id;
            const message = describeFieldCode(issue.code, column);
            patchRowByKey(`r${rowId}`, (r) => withMark(r, columnId, { kind: "invalid", message }));
          }
          setPaste({ stage: "result", kind: "invalid", headline: "붙여넣은 값 중 고쳐야 할 곳이 있어 아무것도 저장하지 않았습니다.", items, canRetry: false, truncated: truncationText(error) || undefined });
        } else if (isCode(error, "DEFINITION_VERSION_MISMATCH")) {
          setPaste({
            stage: "result",
            kind: "error",
            headline: `${describeApiError(error)} 붙여넣기는 저장되지 않았습니다. 다시 붙여넣어 주세요.`,
            items: [],
            canRetry: false,
          });
          await paramsRef.current.onDefinitionStale();
          reload();
        } else if (isCode(error, "WRITE_BUSY") || isCode(error, "DEFINITION_BUSY")) {
          setPaste({ stage: "result", kind: "error", headline: describeApiError(error), items: [], canRetry: true, retry });
        } else {
          setPaste({ stage: "result", kind: "error", headline: describePasteError(error), items: [], canRetry: false });
        }
      }
    },
    [columnById, patchRowByKey, reload],
  );

  /** 충돌 뒤: 화면에 반영된 서버 값을 기준으로 같은 붙여넣기를 다시 계획한다(확인창부터). */
  const replanPaste = useCallback(() => {
    if (pasteMemo.current) planPaste(pasteMemo.current);
  }, [planPaste]);

  useEffect(() => {
    retryRef.current = { editCell, saveDraft, applyPaste };
  });

  const saveableDraftKeys = drafts.filter((d) => draftReady(params.columns, params.baseDateColumnId, d.cells)).map((d) => d.key);

  return {
    order,
    limit,
    offset,
    total,
    status,
    loadError,
    rows,
    drafts,
    notices,
    paste,
    focusRequest,
    saveableDraftKeys,
    setOrder,
    setLimit,
    goTo,
    reload,
    dismissNotice,
    editDraftOrSaved,
    editEntryCell,
    resolveConflict,
    addDraft,
    discardDraft,
    dismissMark,
    saveDraft,
    requestPaste,
    cancelPaste,
    applyPaste,
    replanPaste,
    missingFor: (draft: GridRow) => missingRequired(params.columns, params.baseDateColumnId, draft.cells),
  };
}

/** 저장 응답의 행으로 바꾼다. 다른 칸이 아직 저장 중이면 그 칸의 화면 값과 표시는 유지한다. */
function mergeServerRow(local: GridRow, saved: Row, editedColumnId: number): GridRow {
  const server = fromServerRow(saved);
  const cells = { ...server.cells };
  const marks: Record<string, Mark> = {};
  for (const [columnKey, mark] of Object.entries(local.marks)) {
    if (columnKey === String(editedColumnId)) continue;
    if (mark.kind === "pending") {
      cells[columnKey] = local.cells[columnKey] ?? null;
      marks[columnKey] = mark;
    } else {
      marks[columnKey] = mark;
    }
  }
  return { ...server, cells, marks };
}

/** 422 필드 오류를 칸 표시로 옮긴다. column_id가 없으면 편집한 칸에 단다. */
function markFieldIssues(
  error: unknown,
  rowKey: string,
  editedColumnId: number | null,
  editedColumn: Column | undefined,
  patch: (key: string, change: (row: GridRow) => GridRow) => void,
  setRowIssue?: (text: string) => void,
  columns: Column[] = editedColumn ? [editedColumn] : [],
): void {
  const issues = fieldIssuesOf(error);
  const lines: string[] = [];
  for (const issue of issues) {
    const columnId = issue.column_id ?? editedColumnId;
    const column = columnId === null ? undefined : columns.find((c) => c.id === columnId) ?? editedColumn;
    const message = describeFieldCode(issue.code, column);
    lines.push(`${column?.display_name ?? issue.field ?? "값"}: ${message}`);
    if (columnId !== null && column) patch(rowKey, (row) => withMark(row, column.id, { kind: "invalid", message }));
  }
  if (issues.length === 0 && editedColumnId !== null) {
    patch(rowKey, (row) => withMark(row, editedColumnId, { kind: "invalid", message: describeApiError(error) }));
  }
  const cut = truncationText(error);
  if (cut && lines.length > 0) lines.push(cut);
  if (setRowIssue) setRowIssue(lines.length > 0 ? lines.join(" / ") : describeApiError(error));
}
