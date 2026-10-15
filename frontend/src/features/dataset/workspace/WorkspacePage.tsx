import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../../../api";
import { ErrorNotice, Loading } from "../../../components";
import { EntryGrid } from "../../entry/EntryGrid";
import type { SelectedCell } from "../../entry/selectedCell";
import { createFormula, updateFormula } from "../../formula/api";
import type { SaveInput, SaveOutcome } from "../../formula/FormulaEditor";
import { ArchiveAction, doneText } from "../ArchiveAction";
import { addColumn, getDataset, sortColumns, updateColumn, updateDataset } from "../api";
import { formatDate } from "../format";
import {
  COLUMN_KIND_LABELS,
  COLUMN_TYPE_LABELS,
  DATE_UNIT_LABELS,
  type Column,
  type ColumnRules,
  type DatasetDetail,
} from "../types";
import { Inspector, type Actions, type Feedback, type Selection } from "./Inspector";

/** 이동의 두 번째 호출이 실패했을 때(앞 호출은 이미 저장됨) 오류 문구 아래에 붙이는 안내 */
const MOVE_PARTIAL_NOTE = "순서를 다시 확인해 주세요";

/** S4 작업공간 골격(C 3분할). 라우트가 바뀌면 상태를 새로 시작한다. */
export function WorkspacePage() {
  const { datasetId } = useParams();
  return <Workspace key={datasetId} datasetId={Number(datasetId)} />;
}

type Loaded = { detail: DatasetDetail } | { error: unknown } | null;

function Workspace({ datasetId }: { datasetId: number }) {
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [selection, setSelection] = useState<Selection>({ kind: "dataset" });
  const [feedback, setFeedback] = useState<Feedback>(null);
  // 가장 최근에 알게 된 정의 버전. 연속 저장이 낡은 값을 쓰지 않게 ref로도 들고 있다.
  const versionRef = useRef(0);
  // 수식을 저장하면 계산 열 값이 바뀌므로 그리드가 행을 다시 읽도록 올린다.
  const [gridRefresh, setGridRefresh] = useState(0);
  // 그리드에서 고른 계산 열 칸(전체 값을 Inspector 수식 보기에 보여 준다)
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);
  // 다른 사람이 방금 보관해서 쓰기가 409 DATASET_ARCHIVED로 돌아온 경우(재조회 전에도 읽기 전용으로 바꾼다)
  const [forcedArchived, setForcedArchived] = useState(false);
  const detail = loaded && "detail" in loaded ? loaded.detail : null;
  // 열 목록은 정의가 바뀔 때만 새 배열이 된다(그리드 열 정의가 불필요하게 다시 만들어지지 않게).
  const columns = useMemo(() => sortColumns(detail?.columns ?? []), [detail?.columns]);

  const apply = useCallback((next: DatasetDetail) => {
    // 더 오래된 응답(느린 재읽기)이 최신 상태를 덮어쓰지 않게 한다.
    if (next.def_version < versionRef.current) return;
    versionRef.current = next.def_version;
    setForcedArchived(false);
    setLoaded({ detail: next });
  }, []);

  /** 조용히 다시 읽는다(화면과 입력 중인 내용을 유지). 읽기에 실패하면 보던 화면을 그대로 둔다. */
  const refetch = useCallback(async () => {
    try {
      apply(await getDataset(datasetId));
    } catch {
      // 재읽기 실패는 무시한다. 다음 저장 때 서버가 버전 불일치를 다시 알려 준다.
    }
  }, [apply, datasetId]);

  /** 보관 중 쓰기 거부(409 DATASET_ARCHIVED): 읽기 전용으로 바꾸고 최신 상태(status)를 다시 읽는다. */
  const markArchived = useCallback(() => {
    setForcedArchived(true);
    void refetch();
  }, [refetch]);

  const getVersion = useCallback(() => versionRef.current, []);
  /** 서버가 알려 준 정의 버전이 내가 아는 것보다 크면 다른 사람이 정의를 바꾼 것이므로 정의를 다시 읽는다. */
  const noteVersion = useCallback(
    (version: number) => {
      if (version > versionRef.current) void refetch();
    },
    [refetch],
  );

  useEffect(() => {
    let active = true;
    if (!Number.isInteger(datasetId)) {
      queueMicrotask(() => {
        if (active) setLoaded({ error: new ApiError(404, { code: "NOT_FOUND", message: "", details: null, request_id: null }) });
      });
      return () => {
        active = false;
      };
    }
    getDataset(datasetId)
      .then((next) => {
        if (!active) return;
        versionRef.current = next.def_version;
        setLoaded({ detail: next });
      })
      .catch((error: unknown) => active && setLoaded({ error }));
    return () => {
      active = false;
    };
  }, [datasetId]);

  /** 저장 한 번: 성공하면 안내, 버전 충돌이면 최신 상태를 다시 읽는다. 실패는 Inspector 위에 문구로 보여 준다. */
  async function run(action: () => Promise<string>, noteOnError?: () => string | undefined) {
    setFeedback(null);
    try {
      setFeedback({ kind: "ok", text: await action() });
    } catch (error) {
      if (error instanceof ApiError && error.code === "DEFINITION_VERSION_MISMATCH") await refetch();
      if (error instanceof ApiError && error.code === "DATASET_ARCHIVED") markArchived();
      setFeedback({ kind: "error", error, note: noteOnError?.() });
    }
  }

  /** B6 한 건. 응답으로 로컬 목록과 정의 버전을 바로 갱신한다(연속 호출이 새 버전을 쓰게 ref도 올린다). */
  async function patchColumn(
    columnId: number,
    body: { display_name?: string; required?: boolean; rules?: ColumnRules; tag?: string | null; position?: number },
  ) {
    const saved = await updateColumn(datasetId, columnId, { expected_version: versionRef.current, ...body });
    versionRef.current = saved.def_version;
    setLoaded((previous) =>
      previous && "detail" in previous
        ? {
            detail: {
              ...previous.detail,
              def_version: saved.def_version,
              columns: previous.detail.columns.map((c) => (c.id === saved.column.id ? saved.column : c)),
            },
          }
        : previous,
    );
  }

  const actions: Actions = {
    addColumn: (body) =>
      run(async () => {
        const saved = await addColumn(datasetId, { expected_version: versionRef.current, ...body });
        versionRef.current = saved.def_version;
        setLoaded((previous) =>
          previous && "detail" in previous
            ? { detail: { ...previous.detail, def_version: saved.def_version, columns: [...previous.detail.columns, saved.column] } }
            : previous,
        );
        setSelection({ kind: "column", id: saved.column.id });
        void refetch();
        return "열을 추가했습니다.";
      }),
    updateColumn: (columnId, body) =>
      run(async () => {
        await patchColumn(columnId, body);
        void refetch();
        return "열을 저장했습니다.";
      }),
    moveColumn: (columnId, direction) => {
      let partial = false;
      return run(async () => {
        const order = columns.map((c) => c.id);
        const from = order.indexOf(columnId);
        const to = direction === "up" ? from - 1 : from + 1;
        if (from < 0 || to < 0 || to >= order.length) return "더 옮길 곳이 없습니다.";
        [order[from], order[to]] = [order[to], order[from]];
        const positions = new Map(columns.map((c) => [c.id, c.position]));
        let done = 0;
        try {
          // B6에는 한 번에 순서를 바꾸는 호출이 없다. 지금 쓰는 위치 번호 자리를 새 순서대로 다시 나눠 주고,
          // 번호가 달라지는 열만 한 건씩 고친다(번호가 모두 다르면 이웃한 두 열만 서로 바뀐다: 2회).
          // 같은 번호가 겹쳐 있으면(순서가 id로만 갈리는 상태) 0부터 차례로 다시 매긴다.
          const slots = columns.map((c) => c.position);
          const unique = new Set(slots).size === slots.length;
          for (const [index, id] of order.entries()) {
            const target = unique ? slots[index] : index;
            if (positions.get(id) !== target) {
              await patchColumn(id, { position: target });
              done += 1;
            }
          }
        } catch (error) {
          if (done > 0) {
            partial = true; // 앞선 호출은 이미 저장됐다(비원자적, 03b 33-1 6): 순서를 다시 확인하도록 안내한다.
            await refetch();
          } // 일부만 바뀌었으니 실제 순서를 다시 읽어 보여 준다(버전 충돌이면 run이 읽는다).
          throw error;
        }
        void refetch();
        return "열 순서를 바꿨습니다.";
      }, () => (partial ? MOVE_PARTIAL_NOTE : undefined));
    },
    saveFormula: async (input: SaveInput): Promise<SaveOutcome> => {
      setFeedback(null);
      try {
        const saved =
          input.mode === "create"
            ? await createFormula(datasetId, {
                expected_version: versionRef.current,
                display_name: input.display_name,
                expression: input.expression,
                ...(input.tag !== undefined ? { tag: input.tag } : {}),
                ...(input.position !== undefined ? { position: input.position } : {}),
              })
            : await updateFormula(datasetId, input.columnId, { expected_version: versionRef.current, expression: input.expression });
        versionRef.current = saved.def_version;
        setLoaded((previous) =>
          previous && "detail" in previous
            ? {
                detail: {
                  ...previous.detail,
                  def_version: saved.def_version,
                  columns: previous.detail.columns.some((c) => c.id === saved.column.id)
                    ? previous.detail.columns.map((c) => (c.id === saved.column.id ? saved.column : c))
                    : [...previous.detail.columns, saved.column],
                },
              }
            : previous,
        );
        setGridRefresh((value) => value + 1);
        if (input.mode === "create") setSelection({ kind: "column", id: saved.column.id });
        void refetch();
        setFeedback({
          kind: "ok",
          text:
            input.mode === "create"
              ? "계산 열을 추가했습니다."
              : saved.result_type_changed
                ? "수식을 저장했습니다. 결과 종류가 바뀌었습니다. 이 열을 쓰는 저장된 차트가 있으면 대시보드에서 차트가 그대로 보이는지 확인해 주세요."
                : "수식을 저장했습니다.",
        });
        return { ok: true };
      } catch (error) {
        // 정의가 바뀌었다면 최신 정의를 다시 읽는다. 입력 중인 수식은 편집기에 그대로 남는다.
        if (error instanceof ApiError && error.code === "DEFINITION_VERSION_MISMATCH") await refetch();
        if (error instanceof ApiError && error.code === "DATASET_ARCHIVED") markArchived();
        return { ok: false, error };
      }
    },
    updateDataset: (body) =>
      run(async () => {
        const next = await updateDataset(datasetId, { expected_version: versionRef.current, ...body });
        versionRef.current = Math.max(versionRef.current, next.def_version);
        apply(next);
        return "데이터셋 설정을 저장했습니다.";
      }),
  };

  function select(next: Selection) {
    setFeedback(null);
    setSelection(next);
  }

  if (!detail) {
    return (
      <section data-testid="screen-S4">
        <h1>S4 작업공간</h1>
        {loaded === null ? <Loading label="데이터셋을 불러오는 중" /> : null}
        {loaded && "error" in loaded ? <ErrorNotice error={loaded.error} /> : null}
      </section>
    );
  }

  // 권한(permissions)은 역할 기준 그대로 두고, 보관 상태는 status로 따로 판단한다(FU-2b).
  const archived = detail.status === "archived" || forcedArchived;
  const canDefine = detail.permissions.define;
  const baseColumn = columns.find((c) => c.id === detail.base_date_column_id);
  const selectedId = selection.kind === "column" ? selection.id : null;

  return (
    <section data-testid="screen-S4" className="workspace">
      <h1>S4 작업공간: {detail.name}</h1>
      {archived ? (
        <div className="archive-banner" role="status" data-testid="archived-banner">
          <p>
            보관된 데이터셋입니다. 입력과 정의 변경이 멈춰 있습니다. 복구하면 다시 고칠 수 있습니다.
            {canDefine ? "" : " 복구는 이 팀의 정의 담당자만 할 수 있습니다."}
          </p>
          {canDefine ? (
            <ArchiveAction
              dataset={{ id: detail.id, name: detail.name, status: "archived" }}
              onDone={(kind, next) => {
                apply(next);
                setForcedArchived(false);
                setGridRefresh((value) => value + 1);
                setFeedback({ kind: "ok", text: doneText(kind, next.name) });
              }}
            />
          ) : null}
        </div>
      ) : null}
      <div className="workspace-grid">
        <div className="workspace-left">
          <section aria-label="데이터셋 정보" className="panel">
            <h2>데이터셋 정보</h2>
            <dl className="info">
              <dt>팀</dt>
              <dd>{detail.team.name}</dd>
              <dt>날짜 단위</dt>
              <dd>{DATE_UNIT_LABELS[detail.date_unit] ?? detail.date_unit}</dd>
              <dt>기준 날짜 열</dt>
              <dd>{baseColumn ? baseColumn.display_name : "없음"}</dd>
              <dt>생성자</dt>
              <dd>{detail.created_by.display_name}</dd>
              <dt>생성일</dt>
              <dd>{formatDate(detail.created_at)}</dd>
              <dt>정의 버전</dt>
              <dd>{detail.def_version}</dd>
            </dl>
            <button type="button" onClick={() => select({ kind: "dataset" })}>
              데이터셋 설정
            </button>
          </section>
          <section aria-label="열 목록" className="panel">
            <h2>열 목록</h2>
            <ul className="column-list">
              {columns.map((column) => (
                <li key={column.id}>
                  <button
                    type="button"
                    className={column.id === selectedId ? "selected" : ""}
                    aria-pressed={column.id === selectedId}
                    onClick={() => select({ kind: "column", id: column.id })}
                  >
                    {column.display_name} <span className="muted">{columnSummary(column, detail.base_date_column_id)}</span>
                  </button>
                </li>
              ))}
            </ul>
            {canDefine ? (
              <div className="actions">
                <button type="button" disabled={archived} onClick={() => select({ kind: "add" })}>
                  열 추가
                </button>
                <button type="button" disabled={archived} onClick={() => select({ kind: "addFormula" })}>
                  계산 열 추가
                </button>
              </div>
            ) : null}
          </section>
        </div>

        <section aria-label="입력 그리드 영역" className="workspace-center">
          {columns.length === 0 ? (
            <p className="muted" data-testid="no-columns">
              {canDefine ? "아직 열이 없습니다. 오른쪽에서 열을 추가해 주세요." : "아직 정의된 열이 없습니다."}
            </p>
          ) : (
            <EntryGrid
              datasetId={datasetId}
              columns={columns}
              baseDateColumnId={detail.base_date_column_id}
              canEnter={detail.permissions.enter && !archived}
              archived={archived}
              onArchived={markArchived}
              selectedColumnId={selectedId}
              onSelectColumn={(id) => select({ kind: "column", id })}
              getVersion={getVersion}
              onVersion={noteVersion}
              onDefinitionStale={refetch}
              refreshToken={gridRefresh}
              onSelectedCell={setSelectedCell}
            />
          )}
        </section>

        <Inspector
          detail={detail}
          columns={columns}
          canDefine={canDefine}
          archived={archived}
          selection={selection}
          feedback={feedback}
          actions={actions}
          onSelect={select}
          selectedCell={selectedCell}
        />
      </div>
    </section>
  );
}

function columnSummary(column: Column, baseId: number | null): string {
  const parts: string[] = [COLUMN_TYPE_LABELS[column.type] ?? column.type];
  if (column.kind === "formula") parts.push(COLUMN_KIND_LABELS.formula);
  if (column.required) parts.push("필수");
  if (column.id === baseId) parts.push("기준 날짜");
  return parts.join(" · ");
}
