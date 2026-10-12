import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ApiError } from "../../api";
import { ErrorNotice } from "../../components";
import { truncationText } from "../../errors";
import { validateColumnName, validateTag } from "../dataset/rules";
import { COLUMN_NAME_MAX, TAG_MAX, type Column } from "../dataset/types";
import { checkFormula, previewFormula } from "./api";
import {
  applySuggestion,
  completionContext,
  errorRanges,
  insertColumnRef,
  markSegments,
  suggestionsFor,
  toUtf16Index,
  type Suggestion,
} from "./autocomplete";
import { useFunctionCatalog } from "./catalog";
import { FORMULA_RULES, cellErrorText, invalidErrorsOf, isCode, previewCell, resultTypeLabel, retryAfterOf } from "./messages";
import type { CheckResult, FormulaErrorItem, PreviewResult } from "./types";

/** 저장 요청. expected_version은 작업공간이 붙인다. */
export type SaveInput =
  | { mode: "create"; display_name: string; expression: string; tag?: string; position?: number }
  | { mode: "update"; columnId: number; expression: string };

export type SaveOutcome = { ok: true } | { ok: false; error: unknown };

export interface FormulaEditorProps {
  datasetId: number;
  /** 데이터셋의 모든 열(칩·자동완성에 쓴다) */
  columns: Column[];
  /** 고치는 계산 열. 없으면 새 계산 열 만들기 */
  editing: Column | null;
  /** 시작 수식. 고칠 때는 수식 보기(D6)의 text */
  initialExpression: string;
  save: (input: SaveInput) => Promise<SaveOutcome>;
  /** 입력이 멈춘 뒤 수식 검사(D2)를 부르기까지(ms). 07 §5 "입력 후 약 1초 뒤 자동 미리보기" = 검사 + 미리보기 지연 */
  checkDelayMs?: number;
  /** 검사가 통과한 뒤 미리보기(D3)를 자동으로 부르기까지(ms) */
  previewDelayMs?: number;
  /** 미리보기가 PREVIEW_BUSY일 때 자동으로 한 번 더 시도하기까지(ms). 생략하면 서버 retry_after(1~5초) */
  busyRetryMs?: number;
}

export const DEFAULT_CHECK_DELAY_MS = 400;
export const DEFAULT_PREVIEW_DELAY_MS = 600;

type CheckState = { expr: string; result?: CheckResult; error?: unknown } | null;
type PreviewStatus =
  | { expr: string; status: "loading" }
  | { expr: string; status: "ready" }
  | { expr: string; status: "busy"; error: unknown; retrying: boolean }
  | { expr: string; status: "error"; error: unknown };

/** S4 Inspector 안의 수식 편집기(계산 열 만들기·수정). 정의 권한이 있을 때만 올린다. */
/** 이 개수를 넘으면 목록 아래에 '스크롤/입력으로 좁히기' 안내를 보인다(목록은 항상 전체를 담는다). */
const SUGGEST_VISIBLE = 8;

export function FormulaEditor(props: FormulaEditorProps) {
  const { datasetId, columns, editing, initialExpression, save } = props;
  const checkDelay = props.checkDelayMs ?? DEFAULT_CHECK_DELAY_MS;
  const previewDelay = props.previewDelayMs ?? DEFAULT_PREVIEW_DELAY_MS;
  const ids = { name: useId(), expr: useId(), list: useId(), errors: useId(), tag: useId(), position: useId() };

  const [name, setName] = useState("");
  const [tag, setTag] = useState("");
  const [position, setPosition] = useState("");
  const [expression, setExpression] = useState(initialExpression);
  const [baseline, setBaseline] = useState(initialExpression);
  const [caret, setCaret] = useState(initialExpression.length);
  const [dismissedKey, setDismissedKey] = useState("");
  const [activeState, setActiveState] = useState<{ key: string; index: number }>({ key: "", index: 0 });
  const [check, setCheck] = useState<CheckState>(null);
  const [invalid, setInvalid] = useState<{ expr: string; errors: FormulaErrorItem[] } | null>(null);
  const [preview, setPreview] = useState<PreviewStatus | null>(null);
  const [previewResult, setPreviewResult] = useState<{ expr: string; result: PreviewResult } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [saveExpr, setSaveExpr] = useState("");

  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const pendingCaret = useRef<number | null>(null);
  const previewAbort = useRef<AbortController | null>(null);
  const retryTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const latest = useRef<{ start: (expr: string, attempt: number) => void; cancel: () => void }>({ start: () => undefined, cancel: () => undefined });

  const catalogState = useFunctionCatalog(true);
  const catalog = catalogState.status === "ready" ? catalogState.catalog : null;
  const editingId = editing?.id;
  // 자기 자신을 참조하면 순환이므로 칩·자동완성에서 뺀다.
  const refColumns = useMemo(() => columns.filter((c) => c.id !== editingId), [columns, editingId]);

  // ---- 미리보기(D3): 사용자당 동시 1건이므로 새 요청 전에 이전 요청을 취소하고 낡은 결과는 무시한다 -------------
  const cancelPreview = useCallback(() => {
    previewAbort.current?.abort();
    previewAbort.current = null;
    clearTimeout(retryTimer.current);
    retryTimer.current = undefined;
  }, []);

  const startPreview = useCallback(
    (expr: string, attempt: number) => {
      cancelPreview();
      const controller = new AbortController();
      previewAbort.current = controller;
      setPreview({ expr, status: "loading" });
      previewFormula(datasetId, { expression: expr, ...(editingId !== undefined ? { column_id: editingId } : {}) }, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setPreviewResult({ expr, result });
          setPreview({ expr, status: "ready" });
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          if (isCode(error, "PREVIEW_BUSY")) {
            if (attempt < 1) {
              // 내가 방금 취소한 이전 요청이 서버에서 아직 끝나지 않았을 수 있어 한 번은 자동으로 다시 시도한다.
              setPreview({ expr, status: "busy", error, retrying: true });
              const wait = props.busyRetryMs ?? Math.min(5, Math.max(1, retryAfterOf(error) ?? 2)) * 1000;
              retryTimer.current = setTimeout(() => latest.current.start(expr, attempt + 1), wait);
            } else {
              setPreview({ expr, status: "busy", error, retrying: false });
            }
            return;
          }
          if (isCode(error, "FORMULA_INVALID")) setInvalid({ expr, errors: invalidErrorsOf(error) });
          setPreview({ expr, status: "error", error });
        });
    },
    [cancelPreview, datasetId, editingId, props.busyRetryMs],
  );

  useEffect(() => {
    latest.current = { start: startPreview, cancel: cancelPreview };
  }, [startPreview, cancelPreview]);

  // ---- 수식 검사(D2) 디바운스 -> 통과하면 미리보기 자동 호출 ---------------------------------------------------
  useEffect(() => {
    if (expression.trim() === "") return;
    const controller = new AbortController();
    let previewTimer: ReturnType<typeof setTimeout> | undefined;
    const timer = setTimeout(() => {
      checkFormula(datasetId, { expression, ...(editingId !== undefined ? { column_id: editingId } : {}) }, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setCheck({ expr: expression, result });
          if (result.ok) previewTimer = setTimeout(() => latest.current.start(expression, 0), previewDelay);
        })
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          setCheck({ expr: expression, error });
        });
    }, checkDelay);
    return () => {
      clearTimeout(timer);
      clearTimeout(previewTimer);
      controller.abort();
      latest.current.cancel();
    };
  }, [expression, datasetId, editingId, checkDelay, previewDelay]);

  useEffect(
    () => () => {
      latest.current.cancel();
    },
    [],
  );

  // ---- 자동완성 --------------------------------------------------------------------------------------------------
  const context = useMemo(() => completionContext(expression, caret), [expression, caret]);
  const suggestions = useMemo(() => suggestionsFor(context, catalog?.functions ?? [], refColumns), [context, catalog, refColumns]);
  const contextKey = context ? `${context.kind}:${context.from}:${context.query}` : "";
  const open = suggestions.length > 0 && dismissedKey !== contextKey;
  const activeIndex = activeState.key === contextKey ? Math.min(activeState.index, suggestions.length - 1) : 0;
  const activeSuggestion: Suggestion | undefined = open ? suggestions[activeIndex] : undefined;

  useLayoutEffect(() => {
    const target = pendingCaret.current;
    const node = textarea.current;
    if (target === null || !node) return;
    pendingCaret.current = null;
    node.focus();
    node.setSelectionRange(target, target);
  });

  function edit(next: { text: string; caret: number }) {
    pendingCaret.current = next.caret;
    setExpression(next.text);
    setCaret(next.caret);
  }

  function accept(suggestion: Suggestion) {
    if (!context) return;
    edit(applySuggestion(expression, context, suggestion));
  }

  function syncCaret() {
    const node = textarea.current;
    if (node) setCaret(node.selectionStart);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (!open) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const step = event.key === "ArrowDown" ? 1 : -1;
      const next = (activeIndex + step + suggestions.length) % suggestions.length;
      setActiveState({ key: contextKey, index: next });
      // 8개를 넘는 후보도 키보드로 따라가도록 고른 항목을 목록 안에서 보이게 한다(jsdom에는 없을 수 있다).
      document.getElementById(`${ids.list}-${next}`)?.scrollIntoView?.({ block: "nearest" });
    } else if ((event.key === "Enter" || event.key === "Tab") && activeSuggestion) {
      event.preventDefault();
      accept(activeSuggestion);
    } else if (event.key === "Escape") {
      event.preventDefault();
      setDismissedKey(contextKey);
    }
  }

  function insertChip(column: Column) {
    const node = textarea.current;
    const start = node ? node.selectionStart : expression.length;
    const end = node ? node.selectionEnd : expression.length;
    edit(insertColumnRef(expression, start, end, column.display_name));
  }

  // ---- 오류 위치 -------------------------------------------------------------------------------------------------
  const checkNow = check && check.expr === expression ? check : null;
  const checkResult = checkNow?.result;
  const invalidNow = invalid && invalid.expr === expression ? invalid : null;
  const checkErrors = checkResult && !checkResult.ok ? checkResult.errors : null;
  const invalidErrors = invalidNow?.errors;
  const shownErrors = useMemo<FormulaErrorItem[]>(() => checkErrors ?? invalidErrors ?? [], [checkErrors, invalidErrors]);
  const segments = useMemo(() => markSegments(expression, shownErrors), [expression, shownErrors]);

  function showPosition(error: FormulaErrorItem) {
    const node = textarea.current;
    if (!node) return;
    const { ranges } = errorRanges(expression, [error]);
    const start = ranges[0]?.start ?? Math.min(toUtf16Index(expression, error.start), expression.length);
    const end = ranges[0]?.end ?? start;
    node.focus();
    node.setSelectionRange(start, end);
    setCaret(start);
  }

  // ---- 저장 ------------------------------------------------------------------------------------------------------
  const nameError = editing ? null : validateColumnName(name);
  const isNumber = (checkResult?.ok ? checkResult.result_type : null) === "number";
  const tagError = !editing && isNumber ? validateTag(tag) : null;
  const positionTrim = position.trim();
  const positionError = positionTrim !== "" && !/^\d+$/.test(positionTrim) ? "위치는 0 이상의 정수로 입력해 주세요." : null;
  const dirty = editing ? expression !== baseline : true;
  const blockedByCheck = checkResult !== undefined && !checkResult.ok;
  const canSave = !saving && expression.trim() !== "" && dirty && !blockedByCheck && nameError === null && tagError === null && positionError === null;

  async function submit() {
    if (!canSave) return;
    const expr = expression;
    setSaving(true);
    setSaveError(null);
    const outcome = await save(
      editing
        ? { mode: "update", columnId: editing.id, expression: expr }
        : {
            mode: "create",
            display_name: name.normalize("NFC").trim(),
            expression: expr,
            ...(isNumber && tag.trim() !== "" ? { tag: tag.normalize("NFC").trim() } : {}),
            ...(positionTrim !== "" ? { position: Number(positionTrim) } : {}),
          },
    );
    setSaving(false);
    if (outcome.ok) {
      setBaseline(expr);
      return;
    }
    setSaveError(outcome.error);
    setSaveExpr(expr);
    if (isCode(outcome.error, "FORMULA_INVALID")) setInvalid({ expr, errors: invalidErrorsOf(outcome.error) });
  }

  const cellErrors = catalog?.cell_errors;
  const trimmedEmpty = expression.trim() === "";
  const title = editing ? `수식 고치기: ${editing.display_name}` : "계산 열 추가";
  const previewShown = previewResult;
  const previewStale = previewShown !== null && (previewShown.expr !== expression || preview?.status === "loading");

  return (
    <form
      className="inspector-form formula-editor"
      aria-label={title}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
      noValidate
    >
      <h2>{title}</h2>

      {editing ? null : (
        <>
          <div className="field">
            <label htmlFor={ids.name}>계산 열 이름</label>
            <input id={ids.name} value={name} maxLength={COLUMN_NAME_MAX} onChange={(event) => setName(event.target.value)} />
            {name !== "" && nameError ? (
              <span role="alert" className="state-error-inline" data-testid="formula-name-error">
                {nameError}
              </span>
            ) : null}
          </div>
        </>
      )}

      <div className="field">
        <span id={`${ids.expr}-chips`}>열 이름 칩 (누르면 [열 이름]이 수식에 들어갑니다)</span>
        <div role="group" aria-labelledby={`${ids.expr}-chips`} className="formula-chips">
          {refColumns.length === 0 ? <span className="muted">쓸 수 있는 열이 없습니다.</span> : null}
          {refColumns.map((column) => (
            <button
              key={column.id}
              type="button"
              className={`chip${column.kind === "formula" ? " chip-formula" : ""}`}
              title={column.kind === "formula" ? "계산 열" : "입력 열"}
              onClick={() => insertChip(column)}
            >
              {column.display_name}
            </button>
          ))}
        </div>
      </div>

      <div className="field formula-input">
        <label htmlFor={ids.expr}>수식</label>
        <textarea
          id={ids.expr}
          ref={textarea}
          rows={5}
          spellCheck={false}
          autoComplete="off"
          value={expression}
          placeholder={'예: [매출] - [비용]   (글자는 "큰따옴표", 함수는 IF(...) 처럼 씁니다)'}
          aria-invalid={shownErrors.length > 0}
          aria-describedby={shownErrors.length > 0 ? ids.errors : undefined}
          aria-autocomplete="list"
          aria-controls={open ? ids.list : undefined}
          aria-activedescendant={open ? `${ids.list}-${activeIndex}` : undefined}
          onChange={(event) => {
            setExpression(event.target.value);
            setCaret(event.target.selectionStart);
          }}
          onKeyDown={onKeyDown}
          onKeyUp={syncCaret}
          onClick={syncCaret}
          onSelect={syncCaret}
        />
        {open ? (
          <ul id={ids.list} role="listbox" aria-label="자동완성 후보" className="suggest">
            {suggestions.map((suggestion, index) => (
              <li
                key={`${suggestion.kind}:${suggestion.label}`}
                id={`${ids.list}-${index}`}
                role="option"
                aria-selected={index === activeIndex}
                className={index === activeIndex ? "active" : ""}
                // 마우스로 누를 때 수식 입력창의 커서를 잃지 않게 한다.
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => accept(suggestion)}
              >
                <strong>{suggestion.label}</strong> <span className="muted">{suggestion.detail}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {open && suggestions.length > SUGGEST_VISIBLE ? (
          <p className="muted suggest-more" data-testid="suggest-more">
            후보 {suggestions.length}개 — 목록을 스크롤하거나 ↑↓로 끝까지 고르고, 계속 입력해 좁힐 수 있습니다.
          </p>
        ) : null}
        {activeSuggestion?.fn ? (
          <p className="muted hint" data-testid="suggest-help">
            {activeSuggestion.fn.help_ko}
            {activeSuggestion.fn.excel_diff ? ` (엑셀과 차이: ${activeSuggestion.fn.excel_diff})` : ""}
          </p>
        ) : (
          <span className="muted hint">↑↓로 고르고 Enter 또는 Tab으로 넣습니다. Esc로 닫습니다.</span>
        )}
      </div>

      {shownErrors.length > 0 ? (
        <div id={ids.errors} className="formula-errors" role="alert" aria-label="수식 오류">
          <pre className="formula-marked" aria-label="오류 위치 표시">
            {segments.map((segment, index) =>
              segment.bad ? (
                <mark key={index} className="formula-bad" data-placeholder={segment.placeholder ? "true" : undefined}>
                  {segment.text}
                </mark>
              ) : (
                <span key={index}>{segment.text}</span>
              ),
            )}
          </pre>
          <ul>
            {shownErrors.map((error, index) => (
              <li key={index}>
                {error.message}{" "}
                <button type="button" className="link-button" onClick={() => showPosition(error)}>
                  위치 보기
                </button>
              </li>
            ))}
          </ul>
          {truncatedNote(saveError, invalidNow !== null && saveExpr === expression)}
        </div>
      ) : null}

      <p className="muted" role="status" data-testid="check-status">
        {trimmedEmpty
          ? "수식을 입력하면 자동으로 확인합니다."
          : checkNow?.error !== undefined
            ? "수식을 확인하지 못했습니다. 잠시 뒤 다시 입력하거나 저장해서 확인해 주세요."
            : !checkResult
              ? "수식을 확인하는 중…"
              : checkResult.ok
                ? `수식에 문제가 없습니다. 결과는 ${resultTypeLabel(checkResult.result_type)}입니다.${
                    checkResult.refs.length > 0 ? ` 쓰는 열: ${checkResult.refs.map((r) => r.display_name).join(", ")}` : ""
                  }`
                : "수식에 고칠 곳이 있습니다."}
      </p>

      {!editing && isNumber ? (
        <div className="field">
          <label htmlFor={ids.tag}>구분 태그 (선택)</label>
          <input id={ids.tag} value={tag} maxLength={TAG_MAX} onChange={(event) => setTag(event.target.value)} />
          <span className="muted hint">같은 태그의 숫자 열을 SUMTAG("태그")로 한 번에 더할 때 씁니다.</span>
          {tagError ? (
            <span role="alert" className="state-error-inline">
              {tagError}
            </span>
          ) : null}
        </div>
      ) : null}
      {editing ? null : (
        <div className="field">
          <label htmlFor={ids.position}>위치 (선택)</label>
          <input id={ids.position} inputMode="numeric" value={position} onChange={(event) => setPosition(event.target.value)} />
          <span className="muted hint">비워 두면 맨 뒤에 놓입니다.</span>
          {positionError ? (
            <span role="alert" className="state-error-inline">
              {positionError}
            </span>
          ) : null}
        </div>
      )}

      {saveError !== null ? <SaveFailure error={saveError} /> : null}

      <div className="actions">
        <button type="submit" className="primary" disabled={!canSave}>
          {saving ? "저장하는 중…" : editing ? "수식 저장" : "계산 열 추가"}
        </button>
        <button
          type="button"
          disabled={trimmedEmpty}
          onClick={() => {
            cancelPreview();
            startPreview(expression, 0);
          }}
        >
          미리보기
        </button>
      </div>

      <PreviewPanel
        trimmedEmpty={trimmedEmpty}
        status={preview && preview.expr === expression ? preview : null}
        shown={previewShown}
        stale={previewStale}
        cellErrors={cellErrors}
        onRetry={() => {
          cancelPreview();
          startPreview(expression, 0);
        }}
      />

      <details className="formula-help">
        <summary>수식 도움말</summary>
        <ul>
          {FORMULA_RULES.map((rule) => (
            <li key={rule.title}>
              <strong>{rule.title}</strong>: {rule.text}
            </li>
          ))}
        </ul>
        <h3>함수 목록</h3>
        {catalogState.status === "loading" ? <p className="muted">함수 목록을 불러오는 중…</p> : null}
        {catalogState.status === "error" ? (
          <p role="alert" className="state-error-inline">
            함수 목록을 불러오지 못했습니다. 함수 이름 자동완성은 쓸 수 없지만 열 이름 자동완성과 칩은 쓸 수 있습니다.{" "}
            <button type="button" className="link-button" onClick={catalogState.reload}>
              다시 불러오기
            </button>
          </p>
        ) : null}
        {catalog ? (
          <dl className="function-list">
            {catalog.functions.map((fn) => (
              <div key={fn.name}>
                <dt>
                  <code>{fn.signature || fn.name}</code>
                  {fn.returns ? <span className="muted"> → {fn.returns}</span> : null}
                </dt>
                <dd>
                  {fn.help_ko}
                  {fn.excel_diff ? <span className="muted"> (엑셀과 차이: {fn.excel_diff})</span> : null}
                </dd>
              </div>
            ))}
          </dl>
        ) : null}
      </details>
    </form>
  );
}

function truncatedNote(error: unknown, relevant: boolean) {
  const note = relevant ? truncationText(error) : "";
  return note ? <p className="muted">{note}</p> : null;
}

/** 저장 실패 안내. 위치가 있는 수식 오류는 입력창 아래 표시가 맡고 여기서는 한 줄 머리말만 쓴다. */
function SaveFailure({ error }: { error: unknown }) {
  if (error instanceof ApiError && error.code === "DEFINITION_VERSION_MISMATCH") {
    return (
      <ErrorNotice error={error}>
        <p>입력한 수식은 그대로 남아 있습니다. 내용을 확인한 뒤 다시 저장하면 최신 정의에 반영됩니다.</p>
      </ErrorNotice>
    );
  }
  if (error instanceof ApiError && error.code === "DEFINITION_BUSY") {
    return (
      <ErrorNotice error={error}>
        <p>입력한 수식은 그대로 남아 있습니다. 잠시 뒤 다시 저장해 주세요.</p>
      </ErrorNotice>
    );
  }
  return <ErrorNotice error={error} />;
}

interface PreviewPanelProps {
  trimmedEmpty: boolean;
  status: PreviewStatus | null;
  shown: { expr: string; result: PreviewResult } | null;
  stale: boolean;
  cellErrors: Record<string, string> | undefined;
  onRetry: () => void;
}

function PreviewPanel({ trimmedEmpty, status, shown, stale, cellErrors, onRetry }: PreviewPanelProps) {
  return (
    <section aria-label="미리보기" className="formula-preview" aria-busy={status?.status === "loading"}>
      <h3>미리보기</h3>
      {trimmedEmpty ? <p className="muted">수식을 입력하면 최근 20행으로 계산해 보여 줍니다. 저장하기 전에는 아무것도 바뀌지 않습니다.</p> : null}
      {status?.status === "loading" ? (
        <p role="status" className="muted">
          미리보기를 계산하는 중…
        </p>
      ) : null}
      {status?.status === "busy" ? (
        <div role="alert" className="state state-error">
          <p>
            {status.retrying
              ? "지금 계산 요청이 많아 잠시 뒤 자동으로 다시 시도합니다…"
              : "지금 계산 요청이 많아 미리보기를 계산하지 못했습니다. 잠시 뒤 다시 시도해 주세요."}
          </p>
          {status.retrying ? null : (
            <button type="button" onClick={onRetry}>
              다시 시도
            </button>
          )}
        </div>
      ) : null}
      {status?.status === "error" ? (
        isCode(status.error, "FORMULA_INVALID") ? (
          <p role="status" className="muted">
            수식에 고칠 곳이 있어 미리보기를 계산하지 않았습니다. 위의 안내를 확인해 주세요.
            {truncationText(status.error) ? ` (${truncationText(status.error)})` : ""}
          </p>
        ) : isCode(status.error, "FORMULA_RUNTIME_ERROR") ? (
          <div role="alert" className="state state-error">
            <p>수식을 계산할 수 없습니다. 시간이 너무 오래 걸렸거나 계산이 불가능한 수식일 수 있습니다. 수식을 단순하게 고쳐 다시 시도해 주세요.</p>
            <button type="button" onClick={onRetry}>
              다시 시도
            </button>
          </div>
        ) : (
          <ErrorNotice error={status.error}>
            <button type="button" onClick={onRetry}>
              다시 시도
            </button>
          </ErrorNotice>
        )
      ) : null}
      {shown ? (
        <div className={stale ? "preview-stale" : undefined}>
          <p data-testid="preview-summary">
            결과: {resultTypeLabel(shown.result.result_type)} · 전체 {shown.result.total_rows.toLocaleString("en-US")}행 중 오류 칸 {shown.result.error_count.toLocaleString("en-US")}개 · 빈 값{" "}
            {shown.result.empty_count.toLocaleString("en-US")}개
            {stale ? " (수식이 바뀌어 다시 계산하는 중입니다)" : ""}
          </p>
          {shown.result.rows.length === 0 ? (
            <p className="muted">아직 입력된 행이 없어 보여 줄 값이 없습니다.</p>
          ) : (
            <table className="list-table preview-table" aria-label="미리보기 결과">
              <caption className="muted">기준 날짜 최근 순 최대 20행 (오류 칸은 붉게, 빈 값은 빗금으로 표시됩니다)</caption>
              <thead>
                <tr>
                  <th scope="col">기간</th>
                  <th scope="col">행</th>
                  <th scope="col">값</th>
                </tr>
              </thead>
              <tbody>
                {shown.result.rows.map((row) => {
                  const cell = previewCell(row, shown.result.result_type);
                  return (
                    <tr key={row.row_id}>
                      <td>{row.period ?? ""}</td>
                      <td>#{row.row_id}</td>
                      <td
                        className={`preview-${cell.kind}`}
                        title={cell.kind === "error" ? `계산 오류(${cell.code}): ${cellErrorText(cell.code, cellErrors)}` : cell.kind === "empty" ? "빈 값: 계산에 쓴 칸 중 비어 있는 칸이 있습니다." : cell.kind === "value" && cell.truncated ? `전체 값: ${cell.full}` : undefined}
                      >
                        {cell.kind === "error" ? (
                          <>
                            오류 <span className="muted">{cell.code}</span> {cellErrorText(cell.code, cellErrors)}
                          </>
                        ) : (
                          cell.text
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </section>
  );
}
