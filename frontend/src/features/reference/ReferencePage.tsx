import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../../api";
import { ErrorNotice, Loading } from "../../components";
import { describeApiError, fieldCodePhrase } from "../../errors";
import { useMe } from "../access/MeContext";
import { fieldIssuesOf } from "../entry/messages";
import { addReferenceValue, correctReferenceValue, createReferenceItem, getReferenceUsage, listReferenceItems, listReferenceValues } from "./api";
import { defaultYear, normalizeValue, validateDescription, validateItemName, validateValue, validateYear } from "./rules";
import { REFERENCE_DESCRIPTION_MAX, REFERENCE_NAME_MAX, YEAR_MAX, YEAR_MIN, type ReferenceItem, type ReferenceUsage, type ReferenceValue } from "./types";

const ITEM_PAGE = 50;
const VALUE_PAGE = 50;

/** 05 §2-8·04 §4 S11 안내문(Skill과 같은 문구). */
export const GUIDE_TEXT =
  "기준값은 숫자만 쓸 수 있고, 같은 연도에는 일괄 적용됩니다. 글자 기준값(예: '1월')은 없습니다. 시기를 고르는 일은 기준 날짜와 대시보드 기간 필터가 맡습니다.";
export const GUIDE_REF_TEXT =
  '수식에서는 REF("이름")으로 씁니다. 그 행의 기준 날짜가 속한 연도의 값을 가져오며(전년 값을 이월하지 않습니다), 연도 값이 없는 행은 빈 값 + 오류 E4로 점검 화면에 나옵니다. 기준 날짜 열이 있는 데이터셋에서만 쓸 수 있습니다.';
export const NAME_RULE_TEXT = "팀마다 다른 값이 필요하면 이름에 팀을 붙이세요(예 전기요금_A팀). 이름은 나중에 바꾸거나 지울 수 없습니다.";
export const DESCRIPTION_HINT = "설명(선택): 무엇에 쓰는 값인지 적어 두세요. 수식 편집기의 자동완성에 함께 보입니다.";
export const READ_ONLY_TEXT = "기준값은 관리자만 추가하거나 정정할 수 있습니다. 누구나 값을 볼 수 있습니다.";
export const ADMIN_ONLY_TEXT = "관리자만 할 수 있습니다.";
export const IMPACT_TEXT = "이 연도의 결과와 차트가 바뀝니다";
export const IMPACT_DETAIL_TEXT = "(이미 입력된 행과 Superset 차트에 모두 반영됩니다)";
export const AUDIT_NOTE_TEXT = "정정 내용은 감사 기록에 남습니다.";
export const duplicateYearText = (year: number | string): string => `${year}년 값이 이미 있습니다. 값을 바꾸려면 정정을 쓰세요.`;
export const usageFailedText = (year: number): string => `이 값을 쓰는 데이터셋을 확인하지 못했습니다. 이 항목을 쓰는 모든 데이터셋의 ${year}년 결과가 바뀝니다.`;

/** R6 조회가 이 시간(ms)을 넘기면 일반 경고로 바꾼다(정정은 막지 않는다). 시험이 줄여 쓴다. */
export const usageTimeout = { ms: 5000 };

interface Loaded<T> {
  key: string;
  page?: { items: T[]; total: number };
  error?: unknown;
}

/** 서버의 필드 오류(422)를 필드별 문구로 모은다. 문구는 쉬운 말이며 서버가 준 message는 쓰지 않는다. */
function fieldMessages(error: unknown): Record<string, string> {
  const out: Record<string, string> = {};
  for (const issue of fieldIssuesOf(error)) {
    if (!issue.field) continue;
    let phrase = fieldCodePhrase(issue.code) ?? "값을 확인해 주세요";
    if (issue.field === "year" && issue.code === "OUT_OF_RANGE") phrase = `${phrase}(${YEAR_MIN}~${YEAR_MAX})`;
    if (issue.field === "value" && issue.code === "OUT_OF_RANGE") phrase = `${phrase}(숫자 38자리 이하)`;
    if (issue.field === "value" && issue.code === "BAD_FORMAT") phrase = "숫자만 입력해 주세요(쉼표·글자 없이)";
    if (issue.field === "name" && issue.code === "BAD_FORMAT") phrase = '이름에는 [ ] " 와 제어문자 등 쓸 수 없는 글자가 있습니다';
    if (issue.field === "name" && issue.code === "TOO_LONG") phrase = `이름은 ${REFERENCE_NAME_MAX}자 이하여야 합니다`;
    if (issue.field === "description" && issue.code === "TOO_LONG") phrase = `설명은 ${REFERENCE_DESCRIPTION_MAX}자 이하여야 합니다`;
    out[issue.field] = `${phrase}${phrase.endsWith(".") ? "" : "."}`;
  }
  return out;
}

const alreadyExistsField = (error: unknown): string =>
  error instanceof ApiError && error.code === "ALREADY_EXISTS" && typeof error.details === "object" && error.details !== null && typeof (error.details as Record<string, unknown>).field === "string"
    ? ((error.details as Record<string, unknown>).field as string)
    : "";

/** 쓰기 실패 문구. 403은 관리자 안내, 나머지는 공통 문구(503은 다시 시도 안내). */
function failureText(error: unknown): string {
  if (error instanceof ApiError && error.code === "FORBIDDEN") return ADMIN_ONLY_TEXT;
  return describeApiError(error);
}

/**
 * S11 기준값(FU-3, 04 §4). 읽기는 모든 사용자, 추가·정정은 관리자만(편집 UI는 관리자에게만 그린다).
 * 숨김은 보안 경계가 아니며 서버가 403으로 막는다(05 R2·R4·R5).
 */
export function ReferencePage() {
  const { state } = useMe();
  const isAdmin = state.status === "ready" && state.me.is_admin;
  const [itemOffset, setItemOffset] = useState(0);
  const [itemReload, setItemReload] = useState(0);
  const [items, setItems] = useState<Loaded<ReferenceItem> | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const itemKey = `${itemReload}|${itemOffset}`;
  useEffect(() => {
    const controller = new AbortController();
    listReferenceItems({ limit: ITEM_PAGE, offset: itemOffset }, controller.signal)
      .then((page) => !controller.signal.aborted && setItems({ key: itemKey, page }))
      .catch((error: unknown) => !controller.signal.aborted && setItems({ key: itemKey, error }));
    return () => controller.abort();
  }, [itemKey, itemOffset]);

  // 다시 읽는 동안에는 직전 목록을 그대로 보여 준다(정정 뒤 안내가 사라지지 않게). 처음 읽을 때만 불러오는 중 표시를 쓴다.
  const itemsLoading = items === null || (items.key !== itemKey && items.page === undefined);
  const itemsError = items !== null && items.key === itemKey ? items.error : undefined;
  const itemList = items?.page?.items ?? [];
  const itemTotal = items?.page?.total ?? 0;
  // 고른 항목이 없거나 이 쪽에 없으면 첫 항목을 보여 준다(파생 값, 상태 동기화 없음).
  const selected = itemList.find((item) => item.id === selectedId) ?? itemList[0];

  const reloadItems = useCallback(() => setItemReload((value) => value + 1), []);

  return (
    <section data-testid="screen-S11" className="console">
      <h1>S11 기준값</h1>
      <div className="panel ref-guide" data-testid="reference-guide">
        <p>{GUIDE_TEXT}</p>
        <p>{GUIDE_REF_TEXT}</p>
        {!isAdmin ? (
          <p className="muted" data-testid="reference-readonly">
            {READ_ONLY_TEXT}
          </p>
        ) : null}
      </div>

      <div className="ref-layout">
        <div className="ref-left">
          <h2>기준값 항목</h2>
          {itemsLoading ? <Loading label="기준값 항목을 불러오는 중" /> : null}
          {itemsError !== undefined ? (
            <ErrorNotice error={itemsError}>
              <button type="button" onClick={reloadItems}>
                다시 시도
              </button>
            </ErrorNotice>
          ) : null}
          {items?.page ? (
            itemList.length === 0 ? (
              <p className="muted" data-testid="no-reference-items">
                {itemOffset > 0 ? "이 쪽에는 항목이 없습니다. 이전 쪽으로 돌아가 주세요." : isAdmin ? "아직 기준값 항목이 없습니다. 아래에서 추가해 주세요." : "아직 등록된 기준값 항목이 없습니다."}
              </p>
            ) : (
              <table aria-label="기준값 항목 목록" className="list-table">
                <thead>
                  <tr>
                    <th scope="col">이름</th>
                    <th scope="col">설명</th>
                    <th scope="col">값 개수</th>
                    <th scope="col">연도 범위</th>
                  </tr>
                </thead>
                <tbody>
                  {itemList.map((item) => (
                    <tr key={item.id} className={item.id === selected?.id ? "ref-selected" : undefined}>
                      <td>
                        <button type="button" className="link" aria-current={item.id === selected?.id ? "true" : undefined} onClick={() => setSelectedId(item.id)}>
                          {item.name}
                        </button>
                      </td>
                      <td>{item.description ?? <span className="muted">-</span>}</td>
                      <td className="num">{item.value_count.toLocaleString("en-US")}</td>
                      <td>{item.year_min === null || item.year_max === null ? <span className="muted">값 없음</span> : item.year_min === item.year_max ? `${item.year_min}년` : `${item.year_min}~${item.year_max}년`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : null}
          {itemTotal > ITEM_PAGE || itemOffset > 0 ? (
            <div className="pager">
              <span>
                전체 {itemTotal}개 중 {Math.min(itemOffset + 1, itemTotal)}–{Math.min(itemOffset + ITEM_PAGE, itemTotal)}
              </span>
              <button type="button" disabled={itemOffset === 0} onClick={() => setItemOffset(Math.max(0, itemOffset - ITEM_PAGE))}>
                이전
              </button>
              <button type="button" disabled={itemOffset + ITEM_PAGE >= itemTotal} onClick={() => setItemOffset(itemOffset + ITEM_PAGE)}>
                다음
              </button>
            </div>
          ) : null}
          {isAdmin ? (
            <AddItemForm
              onCreated={(created) => {
                setItemOffset(0);
                setSelectedId(created.id);
                reloadItems();
              }}
            />
          ) : null}
        </div>

        <div className="ref-right">{selected ? <ItemDetail key={selected.id} item={selected} isAdmin={isAdmin} onChanged={reloadItems} /> : <p className="muted">왼쪽에서 항목을 고르면 연도별 값이 보입니다.</p>}</div>
      </div>
    </section>
  );
}

/* ---------------- 항목 추가 (R2) ---------------- */

function AddItemForm({ onCreated }: { onCreated: (item: ReferenceItem) => void }) {
  const ids = { name: useId(), description: useId() };
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  const [done, setDone] = useState<string | null>(null);

  const nameProblem = name === "" ? null : validateItemName(name);
  const descProblem = validateDescription(description);
  const canSubmit = !busy && validateItemName(name) === null && descProblem === null;
  const fields = fieldMessages(error);
  const conflictField = alreadyExistsField(error);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(undefined);
    setDone(null);
    try {
      const body = { name: name.normalize("NFC").trim(), ...(description.trim() !== "" ? { description: description.normalize("NFC").trim() } : {}) };
      const created = await createReferenceItem(body);
      setName("");
      setDescription("");
      setDone(`'${created.name}' 항목을 추가했습니다. 이제 연도별 값을 추가해 주세요.`);
      onCreated(created);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel panel-form" aria-label="기준값 항목 추가" onSubmit={(event) => void submit(event)} noValidate>
      <h2>항목 추가</h2>
      <p className="muted" data-testid="name-rule">
        {NAME_RULE_TEXT}
      </p>
      <label htmlFor={ids.name}>이름 (수식에서 REF(&quot;이름&quot;)으로 씁니다. 예: 전기요금_A팀)</label>
      <input id={ids.name} value={name} maxLength={REFERENCE_NAME_MAX} onChange={(event) => setName(event.target.value)} aria-invalid={nameProblem !== null || fields.name !== undefined} />
      {nameProblem ? (
        <p role="alert" className="state-error-inline">
          {nameProblem}
        </p>
      ) : null}
      {fields.name ? (
        <p role="alert" className="state-error-inline">
          {fields.name}
        </p>
      ) : null}
      {conflictField === "name" ? (
        <p role="alert" className="state-error-inline">
          {describeApiError(error)}
        </p>
      ) : null}
      <label htmlFor={ids.description}>설명 (선택, {REFERENCE_DESCRIPTION_MAX}자 이하)</label>
      <input id={ids.description} value={description} onChange={(event) => setDescription(event.target.value)} placeholder="예: A팀 사무실의 연도별 전기요금 단가" />
      <span className="muted hint">{DESCRIPTION_HINT}</span>
      {descProblem ? (
        <p role="alert" className="state-error-inline">
          {descProblem}
        </p>
      ) : null}
      {fields.description ? (
        <p role="alert" className="state-error-inline">
          {fields.description}
        </p>
      ) : null}
      {error !== undefined && conflictField !== "name" && Object.keys(fields).length === 0 ? (
        <p role="alert" className="state state-error">
          {failureText(error)}
        </p>
      ) : null}
      {done ? (
        <p role="status" className="state state-ok" data-testid="item-created">
          {done}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" className="primary" disabled={!canSubmit}>
          {busy ? "추가하는 중…" : "항목 추가"}
        </button>
      </div>
    </form>
  );
}

/* ---------------- 항목 상세: 연도별 값 표 (R3), 값 추가 (R4), 정정 (R5·R6) ---------------- */

function ItemDetail({ item, isAdmin, onChanged }: { item: ReferenceItem; isAdmin: boolean; onChanged: () => void }) {
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<ReferenceValue> | null>(null);
  const [correcting, setCorrecting] = useState<{ id: number; text: string } | null>(null);
  const [confirming, setConfirming] = useState<{ value: ReferenceValue; next: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [rowError, setRowError] = useState<unknown>(undefined);

  const key = `${item.id}|${offset}|${reload}`;
  useEffect(() => {
    const controller = new AbortController();
    listReferenceValues(item.id, { limit: VALUE_PAGE, offset }, controller.signal)
      .then((page) => !controller.signal.aborted && setLoaded({ key, page }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key, error }));
    return () => controller.abort();
  }, [item.id, offset, key]);

  const loading = loaded === null || (loaded.key !== key && loaded.page === undefined);
  const loadError = loaded !== null && loaded.key === key ? loaded.error : undefined;
  const values = loaded?.page?.items ?? [];
  const total = loaded?.page?.total ?? 0;
  const refresh = () => {
    setReload((value) => value + 1);
    onChanged();
  };

  return (
    <div data-testid="reference-detail">
      <h2>
        {item.name} <span className="muted">의 연도별 값</span>
      </h2>
      <p className="muted">{item.description ?? "설명이 없습니다."}</p>
      <p className="muted">
        수식에서는 <code>REF(&quot;{item.name}&quot;)</code> 으로 씁니다.
      </p>

      {notice ? (
        <p role="status" className="state state-ok" data-testid="reference-notice">
          {notice}
        </p>
      ) : null}
      {rowError !== undefined ? (
        <p role="alert" className="state state-error" data-testid="reference-row-error">
          {failureText(rowError)}
        </p>
      ) : null}

      {loading ? <Loading label="연도별 값을 불러오는 중" /> : null}
      {loadError !== undefined ? (
        <ErrorNotice error={loadError}>
          <button type="button" onClick={() => setReload((value) => value + 1)}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}
      {loaded?.page ? (
        values.length === 0 ? (
          <p className="muted" data-testid="no-reference-values">
            {offset > 0 ? "이 쪽에는 값이 없습니다. 이전 쪽으로 돌아가 주세요." : "아직 연도별 값이 없습니다. 이 항목을 쓰는 수식은 모든 행에서 E4(기준값 없음)가 됩니다."}
          </p>
        ) : (
          <table aria-label={`${item.name} 연도별 값`} className="list-table">
            <thead>
              <tr>
                <th scope="col">연도</th>
                <th scope="col">값</th>
                <th scope="col">처음 입력한 사람</th>
                <th scope="col">입력일</th>
                {isAdmin ? (
                  <th scope="col">
                    <span className="visually-hidden">동작</span>
                  </th>
                ) : null}
              </tr>
            </thead>
            <tbody>
              {values.map((value) => {
                const editing = correcting?.id === value.id ? correcting : null;
                const problem = editing ? validateValue(editing.text) : null;
                const same = editing ? normalizeValue(editing.text) === value.value : false;
                return (
                  <tr key={value.id}>
                    <td>{value.year}년</td>
                    <td className="num">
                      {editing ? (
                        <span className="inline-edit">
                          <input aria-label={`${value.year}년 새 값`} inputMode="decimal" value={editing.text} onChange={(event) => setCorrecting({ id: value.id, text: event.target.value })} />
                          <button
                            type="button"
                            disabled={problem !== null || same}
                            onClick={() => {
                              setNotice(null);
                              setRowError(undefined);
                              setConfirming({ value, next: normalizeValue(editing.text) });
                            }}
                          >
                            정정 확인
                          </button>
                          <button type="button" onClick={() => setCorrecting(null)}>
                            취소
                          </button>
                          {problem && editing.text !== "" ? <span className="state-error-inline">{problem}</span> : null}
                        </span>
                      ) : (
                        value.value
                      )}
                    </td>
                    <td>{value.created_by.display_name}</td>
                    <td>{value.created_at.slice(0, 10)}</td>
                    {isAdmin ? (
                      <td>
                        {editing ? null : (
                          <button
                            type="button"
                            aria-label={`${value.year}년 값 정정`}
                            onClick={() => {
                              setNotice(null);
                              setRowError(undefined);
                              setCorrecting({ id: value.id, text: value.value });
                            }}
                          >
                            정정
                          </button>
                        )}
                      </td>
                    ) : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )
      ) : null}
      {total > VALUE_PAGE || offset > 0 ? (
        <div className="pager">
          <span>
            전체 {total}개 중 {Math.min(offset + 1, total)}–{Math.min(offset + VALUE_PAGE, total)}
          </span>
          <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - VALUE_PAGE))}>
            이전
          </button>
          <button type="button" disabled={offset + VALUE_PAGE >= total} onClick={() => setOffset(offset + VALUE_PAGE)}>
            다음
          </button>
        </div>
      ) : null}

      {isAdmin ? (
        <AddValueForm
          item={item}
          onAdded={(added) => {
            setNotice(`'${item.name}' ${added.year}년 값 ${added.value}을(를) 추가했습니다.`);
            setOffset(0);
            refresh();
          }}
        />
      ) : null}

      {confirming ? (
        <CorrectionDialog
          item={item}
          value={confirming.value}
          next={confirming.next}
          onCancel={() => setConfirming(null)}
          onDone={(result) => {
            setConfirming(null);
            setCorrecting(null);
            setNotice(
              result.changed
                ? `'${item.name}' ${result.value.year}년 값을 ${result.previous_value} → ${result.value.value}(으)로 정정했습니다. 감사 기록에 남았습니다.`
                : `'${item.name}' ${result.value.year}년 값은 이미 ${result.value.value}이라 바꾸지 않았습니다(감사 기록 없음).`,
            );
            refresh();
          }}
          onGone={(error) => {
            setConfirming(null);
            setCorrecting(null);
            setRowError(error);
            refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function AddValueForm({ item, onAdded }: { item: ReferenceItem; onAdded: (value: ReferenceValue) => void }) {
  const ids = { year: useId(), value: useId() };
  const [year, setYear] = useState(() => defaultYear(item.year_max));
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(undefined);
  // 항목을 다시 읽어 연도 범위가 바뀌어도 사용자가 이미 고친 연도는 건드리지 않는다. 추가 직후에만 기본 연도로 되돌린다.

  const yearProblem = year === "" ? null : validateYear(year);
  const valueProblem = value === "" ? null : validateValue(value);
  const canSubmit = !busy && validateYear(year) === null && validateValue(value) === null;
  const fields = fieldMessages(error);
  const conflictField = alreadyExistsField(error);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(undefined);
    try {
      const added = await addReferenceValue(item.id, { year: Number(year.trim()), value: normalizeValue(value) });
      setValue("");
      setYear(defaultYear(Math.max(added.year, item.year_max ?? added.year)));
      onAdded(added);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel panel-form" aria-label="연도 값 추가" onSubmit={(event) => void submit(event)} noValidate>
      <h2>연도 값 추가</h2>
      <p className="muted">같은 연도 값은 한 번만 추가할 수 있습니다. 이미 입력한 연도의 값을 바꾸려면 위 표에서 &quot;정정&quot;을 쓰세요.</p>
      <label htmlFor={ids.year}>연도 ({YEAR_MIN}~{YEAR_MAX}, 숫자만)</label>
      <input id={ids.year} inputMode="numeric" value={year} maxLength={4} onChange={(event) => setYear(event.target.value)} aria-invalid={yearProblem !== null || fields.year !== undefined || conflictField === "year"} />
      {yearProblem ? (
        <p role="alert" className="state-error-inline">
          {yearProblem}
        </p>
      ) : null}
      {fields.year ? (
        <p role="alert" className="state-error-inline">
          {fields.year}
        </p>
      ) : null}
      {conflictField === "year" ? (
        <p role="alert" className="state-error-inline" data-testid="year-conflict">
          {duplicateYearText(year.trim())}
        </p>
      ) : null}
      <label htmlFor={ids.value}>값 (숫자만, 예: 12.5)</label>
      <input id={ids.value} inputMode="decimal" value={value} onChange={(event) => setValue(event.target.value)} aria-invalid={valueProblem !== null || fields.value !== undefined} />
      {valueProblem ? (
        <p role="alert" className="state-error-inline">
          {valueProblem}
        </p>
      ) : null}
      {fields.value ? (
        <p role="alert" className="state-error-inline">
          {fields.value}
        </p>
      ) : null}
      {error !== undefined && conflictField !== "year" && Object.keys(fields).length === 0 ? (
        <p role="alert" className="state state-error">
          {failureText(error)}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" className="primary" disabled={!canSubmit}>
          {busy ? "추가하는 중…" : "값 추가"}
        </button>
      </div>
    </form>
  );
}

/* ---------------- 정정 확인창 (R5, 영향 목록 R6) ---------------- */

type UsageState = { status: "loading" } | { status: "ready"; usage: ReferenceUsage } | { status: "failed" };

/**
 * 정정 확인창. 열릴 때 R6으로 이 항목을 쓰는 데이터셋을 읽는다. R6가 실패하거나 늦으면 일반 경고로 바꾸고 정정은 막지 않는다.
 * 쓰는 데이터셋이 없으면 영향 줄을 생략한다.
 */
function CorrectionDialog({
  item,
  value,
  next,
  onCancel,
  onDone,
  onGone,
}: {
  item: ReferenceItem;
  value: ReferenceValue;
  next: string;
  onCancel: () => void;
  onDone: (result: Awaited<ReturnType<typeof correctReferenceValue>>) => void;
  onGone: (error: unknown) => void;
}) {
  const titleId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [usage, setUsage] = useState<UsageState>({ status: "loading" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => {
      controller.abort();
      setUsage({ status: "failed" });
    }, usageTimeout.ms);
    getReferenceUsage(item.id, controller.signal)
      .then((result) => {
        if (controller.signal.aborted) return;
        clearTimeout(timer);
        setUsage({ status: "ready", usage: result });
      })
      .catch(() => {
        if (controller.signal.aborted) return;
        clearTimeout(timer);
        setUsage({ status: "failed" });
      });
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [item.id]);
  useEffect(() => {
    if (busy) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [busy, onCancel]);

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      onDone(await correctReferenceValue(item.id, value.id, { value: next }));
    } catch (caught) {
      setBusy(false);
      // 대상이 사라졌거나 다른 사람이 지운 경우(404)는 창을 닫고 목록을 다시 읽는다.
      if (caught instanceof ApiError && caught.code === "NOT_FOUND") {
        onGone(caught);
        return;
      }
      const fields = fieldMessages(caught);
      setError(fields.value ?? failureText(caught));
    }
  }

  return (
    <div className="modal-backdrop">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal modal-confirm" data-testid="correction-dialog">
        <h2 id={titleId} ref={headingRef} tabIndex={-1}>
          {value.year}년 값을 정정할까요?
        </h2>
        <p data-testid="correction-text">
          &apos;{item.name}&apos;의 {value.year}년 값을 <strong>{value.value}</strong>에서 <strong>{next}</strong>(으)로 바꿉니다. <strong>{IMPACT_TEXT}</strong>
          {IMPACT_DETAIL_TEXT}.
        </p>
        <div data-testid="correction-usage" aria-live="polite">
          {usage.status === "loading" ? <p className="muted">이 값을 쓰는 데이터셋을 확인하는 중…</p> : null}
          {usage.status === "failed" ? <p className="archive-limit">{usageFailedText(value.year)}</p> : null}
          {usage.status === "ready" && usage.usage.items.length > 0 ? (
            <div className="ref-affected">
              <p>이 값을 쓰는 데이터셋: {usage.usage.total.toLocaleString("en-US")}개</p>
              <ul>
                {usage.usage.items.map((dataset) => (
                  <li key={dataset.dataset_id}>
                    {dataset.dataset_name} <span className="muted">({dataset.team_name}, 계산 열 {dataset.column_count}개)</span>
                    {dataset.status === "archived" ? <span className="badge badge-archived">보관됨</span> : null}
                  </li>
                ))}
              </ul>
              {usage.usage.truncated ? <p className="muted">일부만 표시됨(전체 {usage.usage.total.toLocaleString("en-US")}개 중 {usage.usage.items.length}개)</p> : null}
            </div>
          ) : null}
        </div>
        <p className="muted">{AUDIT_NOTE_TEXT}</p>
        {error ? (
          <p role="alert" className="state-error-inline" data-testid="correction-error">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <button type="button" className="primary" disabled={busy} onClick={() => void confirm()}>
            {busy ? "정정하는 중…" : error ? "다시 시도" : "정정하기"}
          </button>
          <button type="button" disabled={busy} onClick={onCancel}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}
