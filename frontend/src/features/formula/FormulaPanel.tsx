import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { COLUMN_KIND_LABELS, COLUMN_TYPE_LABELS, type Column } from "../dataset/types";
import { getFormulaView } from "./api";
import { FormulaEditor, type SaveInput, type SaveOutcome } from "./FormulaEditor";
import type { FormulaView } from "./types";

interface FormulaPanelProps {
  datasetId: number;
  /** 선택한 계산 열 */
  column: Column;
  /** 데이터셋의 모든 열 */
  columns: Column[];
  canDefine: boolean;
  /** 정의 버전. 바뀌면(다른 열 이름 변경, 수식 저장) 수식 보기를 다시 읽는다 */
  version: number;
  save: (input: SaveInput) => Promise<SaveOutcome>;
}

type Loaded = { key: string; view?: FormulaView; error?: unknown } | null;

/** S4 Inspector의 계산 열: 수식 보기(D6, 누구나 읽기 전용) + 정의 담당자의 수식 고치기(D5). */
export function FormulaPanel({ datasetId, column, columns, canDefine, version, save }: FormulaPanelProps) {
  const [loaded, setLoaded] = useState<Loaded>(null);
  const [reload, setReload] = useState(0);
  const [editorOpen, setEditorOpen] = useState(false);
  const key = `${column.id}:${version}:${reload}`;

  useEffect(() => {
    const controller = new AbortController();
    getFormulaView(datasetId, column.id, controller.signal)
      .then((view) => !controller.signal.aborted && setLoaded({ key, view }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key, error }));
    return () => controller.abort();
  }, [datasetId, column.id, key]);

  const ready = loaded?.key === key ? loaded : null;
  // 새 정의 버전을 읽는 동안에는 이전 수식 보기를 흐리게 유지한다(깜빡임 방지).
  const view = ready?.view ?? loaded?.view;

  return (
    <div className="formula-panel">
      <section aria-label="수식 보기" className="formula-view">
        <h3>수식 보기 <span className="muted">(읽기 전용)</span></h3>
        {!ready && !view ? <Loading label="수식을 불러오는 중" /> : null}
        {ready?.error !== undefined ? (
          <ErrorNotice error={ready.error}>
            <button type="button" onClick={() => setReload((value) => value + 1)}>
              다시 불러오기
            </button>
          </ErrorNotice>
        ) : null}
        {view && ready?.error === undefined ? <FormulaViewBody datasetId={datasetId} column={column} view={view} /> : null}
      </section>
      {canDefine ? (
        editorOpen ? (
          view ? (
            <FormulaEditor
              // 열이 바뀌면 입력 내용을 새로 시작한다. 같은 열의 정의 버전이 바뀌어도 입력 중인 수식은 유지한다.
              key={column.id}
              datasetId={datasetId}
              columns={columns}
              editing={column}
              initialExpression={view.text}
              save={save}
            />
          ) : (
            <Loading label="수식을 불러오는 중" />
          )
        ) : (
          <button type="button" disabled={!view} onClick={() => setEditorOpen(true)}>
            수식 고치기
          </button>
        )
      ) : (
        <p className="muted" data-testid="formula-readonly">
          수식은 팀의 정의 담당자만 고칠 수 있습니다.
        </p>
      )}
    </div>
  );
}

function FormulaViewBody({ datasetId, column, view }: { datasetId: number; column: Column; view: FormulaView }) {
  return (
    <>
      <pre className="formula-text" aria-label="수식 전체" data-testid="formula-text">
        {view.text}
      </pre>
      <dl className="info formula-info">
        <dt>결과 종류</dt>
        <dd>{COLUMN_TYPE_LABELS[column.type] ?? column.type}</dd>
        <dt>쓰는 열</dt>
        <dd data-testid="formula-refs">
          {view.refs.length === 0
            ? "없음"
            : view.refs.map((ref, index) => (
                <span key={ref.column_id}>
                  {index > 0 ? ", " : ""}
                  {ref.display_name}
                  <span className="muted"> ({COLUMN_KIND_LABELS[ref.kind] ?? ref.kind})</span>
                </span>
              ))}
        </dd>
        {view.tag_columns.length > 0 ? (
          <>
            <dt>태그로 더하는 열</dt>
            <dd data-testid="formula-tag-columns">{view.tag_columns.join(", ")}</dd>
          </>
        ) : null}
        <dt>오류 칸</dt>
        <dd data-testid="formula-error-count">
          {view.error_count === 0 ? (
            "없음"
          ) : (
            <>
              <strong className="state-error-inline">{view.error_count.toLocaleString("en-US")}개</strong>{" "}
              <Link to={`/checks?dataset=${datasetId}&column=${column.id}`}>점검 화면에서 보기</Link>
            </>
          )}
        </dd>
      </dl>
    </>
  );
}
