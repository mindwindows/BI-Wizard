import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ErrorNotice, Loading } from "../../components";
import { listFormulaErrorCells, listFormulaErrorSummaries } from "../formula/api";
import { cellErrorText } from "../formula/messages";
import type { FormulaErrorCell, FormulaErrorSummary, ListPage } from "../formula/types";

const PAGE_SIZE = 50;
const CELL_PAGE_SIZE = 50;

interface Loaded<T> {
  key: string;
  page?: ListPage<T>;
  error?: unknown;
}

const rowKey = (item: { dataset_id: number; column_id: number }) => `${item.dataset_id}:${item.column_id}`;

/**
 * S5 점검(콘솔형). 계산 오류 칸이 있는 열 목록(D7)과 열을 펼치면 오류 칸 목록(D8).
 * 오류 칸은 값이 빈 값이 되고 입력 그리드에서도 붉게 표시된다. 고치려면 데이터셋 작업공간에서 수식이나 입력 값을 바꾼다.
 * 주소의 `?dataset=<번호>&column=<열 번호>`는 그 열을 처음부터 펼쳐 둔다(수식 보기의 "점검 화면에서 보기").
 */
export function ChecksPage() {
  const [params] = useSearchParams();
  const initial = params.get("dataset") && params.get("column") ? `${params.get("dataset")}:${params.get("column")}` : null;
  const [openKey, setOpenKey] = useState<string | null>(initial);
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<Loaded<FormulaErrorSummary> | null>(null);

  const requestKey = `${reloadKey}|${offset}`;
  useEffect(() => {
    const controller = new AbortController();
    listFormulaErrorSummaries({ limit: PAGE_SIZE, offset }, controller.signal)
      .then((page) => !controller.signal.aborted && setResult({ key: requestKey, page }))
      .catch((error: unknown) => !controller.signal.aborted && setResult({ key: requestKey, error }));
    return () => controller.abort();
  }, [requestKey, offset]);

  const loading = result?.key !== requestKey;
  const items = result?.page?.items ?? [];
  const total = result?.page?.total ?? 0;

  return (
    <section data-testid="screen-S5" className="console">
      <h1>S5 점검</h1>
      <p className="muted">
        수식을 계산할 수 없는 칸(오류 칸)이 있는 열의 목록입니다. 오류 칸은 빈 값이 되어 입력 그리드에 붉게 표시됩니다. 원인이 되는 입력 값이나 수식을 데이터셋 작업공간에서 고쳐 주세요.
      </p>
      <div className="toolbar">
        <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
          새로 읽기
        </button>
      </div>

      {loading ? <Loading label="오류 칸을 찾는 중" /> : null}
      {!loading && result?.error !== undefined ? (
        <ErrorNotice error={result.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}
      {!loading && result?.page ? (
        <>
          {items.length === 0 ? (
            <p className="muted" data-testid="no-formula-errors">
              {offset > 0 ? "이 쪽에는 항목이 없습니다. 이전 쪽으로 돌아가 주세요." : "계산 오류 칸이 없습니다. 모든 계산 열이 정상입니다."}
            </p>
          ) : (
            <table aria-label="계산 오류 칸이 있는 열" className="list-table">
              <thead>
                <tr>
                  <th scope="col">데이터셋</th>
                  <th scope="col">팀</th>
                  <th scope="col">계산 열</th>
                  <th scope="col">오류 칸 수</th>
                  <th scope="col">
                    <span className="visually-hidden">동작</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const key = rowKey(item);
                  const opened = openKey === key;
                  return (
                    <ChecksRow
                      key={key}
                      item={item}
                      opened={opened}
                      onToggle={() => setOpenKey(opened ? null : key)}
                    />
                  );
                })}
              </tbody>
            </table>
          )}
          {total > PAGE_SIZE || offset > 0 ? (
            <div className="pager">
              <span>
                전체 {total}개 중 {Math.min(offset + 1, total)}–{Math.min(offset + PAGE_SIZE, total)}
              </span>
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                이전
              </button>
              <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                다음
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function ChecksRow({ item, opened, onToggle }: { item: FormulaErrorSummary; opened: boolean; onToggle: () => void }) {
  return (
    <>
      <tr>
        <td>
          <Link to={`/datasets/${item.dataset_id}`}>{item.dataset_name}</Link>
        </td>
        <td>{item.team_name}</td>
        <td>{item.column_name}</td>
        <td className="num">{item.error_count.toLocaleString("en-US")}</td>
        <td>
          <button type="button" aria-expanded={opened} onClick={onToggle}>
            {opened ? "오류 칸 닫기" : "오류 칸 보기"}
          </button>{" "}
          <Link to={`/datasets/${item.dataset_id}`}>작업공간 열기</Link>
        </td>
      </tr>
      {opened ? (
        <tr>
          <td colSpan={5}>
            <ErrorCells datasetId={item.dataset_id} columnId={item.column_id} columnName={item.column_name} />
          </td>
        </tr>
      ) : null}
    </>
  );
}

function ErrorCells({ datasetId, columnId, columnName }: { datasetId: number; columnId: number; columnName: string }) {
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<Loaded<FormulaErrorCell> | null>(null);
  const requestKey = `${datasetId}|${columnId}|${offset}|${reloadKey}`;

  useEffect(() => {
    const controller = new AbortController();
    listFormulaErrorCells(datasetId, { column_id: columnId, limit: CELL_PAGE_SIZE, offset }, controller.signal)
      .then((page) => !controller.signal.aborted && setResult({ key: requestKey, page }))
      .catch((error: unknown) => !controller.signal.aborted && setResult({ key: requestKey, error }));
    return () => controller.abort();
  }, [datasetId, columnId, offset, requestKey]);

  const loading = result?.key !== requestKey;
  const items = result?.page?.items ?? [];
  const total = result?.page?.total ?? 0;
  return (
    <div aria-label={`${columnName} 오류 칸`} role="group" className="error-cells">
      {loading ? <Loading label="오류 칸을 불러오는 중" /> : null}
      {!loading && result?.error !== undefined ? (
        <ErrorNotice error={result.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}
      {!loading && result?.page ? (
        items.length === 0 ? (
          <p className="muted">지금은 이 열에 오류 칸이 없습니다. 이미 고쳐졌을 수 있습니다.</p>
        ) : (
          <>
            <table aria-label={`${columnName} 오류 칸 목록`} className="list-table">
              <thead>
                <tr>
                  <th scope="col">기간</th>
                  <th scope="col">행</th>
                  <th scope="col">코드</th>
                  <th scope="col">이유</th>
                </tr>
              </thead>
              <tbody>
                {items.map((cell) => (
                  <tr key={`${cell.row_id}:${cell.column_id}`}>
                    <td>{cell.period ?? ""}</td>
                    <td>#{cell.row_id}</td>
                    <td>{cell.error}</td>
                    <td>{cell.message || cellErrorText(cell.error, undefined)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {total > CELL_PAGE_SIZE || offset > 0 ? (
              <div className="pager">
                <span>
                  전체 {total}개 중 {Math.min(offset + 1, total)}–{Math.min(offset + CELL_PAGE_SIZE, total)}
                </span>
                <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - CELL_PAGE_SIZE))}>
                  이전
                </button>
                <button type="button" disabled={offset + CELL_PAGE_SIZE >= total} onClick={() => setOffset(offset + CELL_PAGE_SIZE)}>
                  다음
                </button>
              </div>
            ) : null}
          </>
        )
      ) : null}
    </div>
  );
}
