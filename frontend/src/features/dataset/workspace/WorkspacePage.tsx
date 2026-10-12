import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { ApiError } from "../../../api";
import { ErrorNotice, Loading } from "../../../components";
import { EntryGrid } from "../../entry/EntryGrid";
import { addColumn, getDataset, sortColumns, updateColumn, updateDataset } from "../api";
import { formatDate } from "../format";
import {
  COLUMN_KIND_LABELS,
  COLUMN_TYPE_LABELS,
  DATE_UNIT_LABELS,
  type Column,
  type DatasetDetail,
} from "../types";
import { Inspector, type Actions, type Feedback, type Selection } from "./Inspector";

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
  const detail = loaded && "detail" in loaded ? loaded.detail : null;
  // 열 목록은 정의가 바뀔 때만 새 배열이 된다(그리드 열 정의가 불필요하게 다시 만들어지지 않게).
  const columns = useMemo(() => sortColumns(detail?.columns ?? []), [detail?.columns]);

  const apply = useCallback((next: DatasetDetail) => {
    // 더 오래된 응답(느린 재읽기)이 최신 상태를 덮어쓰지 않게 한다.
    if (next.def_version < versionRef.current) return;
    versionRef.current = next.def_version;
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
  async function run(action: () => Promise<string>) {
    setFeedback(null);
    try {
      setFeedback({ kind: "ok", text: await action() });
    } catch (error) {
      if (error instanceof ApiError && error.code === "DEFINITION_VERSION_MISMATCH") await refetch();
      setFeedback({ kind: "error", error });
    }
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
        void refetch();
        return "열을 저장했습니다.";
      }),
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

  const canDefine = detail.permissions.define;
  const baseColumn = columns.find((c) => c.id === detail.base_date_column_id);
  const selectedId = selection.kind === "column" ? selection.id : null;

  return (
    <section data-testid="screen-S4" className="workspace">
      <h1>S4 작업공간: {detail.name}</h1>
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
              <button type="button" onClick={() => select({ kind: "add" })}>
                열 추가
              </button>
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
              canEnter={detail.permissions.enter}
              selectedColumnId={selectedId}
              onSelectColumn={(id) => select({ kind: "column", id })}
              getVersion={getVersion}
              onVersion={noteVersion}
              onDefinitionStale={refetch}
            />
          )}
        </section>

        <Inspector
          detail={detail}
          columns={columns}
          canDefine={canDefine}
          selection={selection}
          feedback={feedback}
          actions={actions}
          onSelect={select}
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
