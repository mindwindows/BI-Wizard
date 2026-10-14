import { useId, useState, type FormEvent, type ReactNode } from "react";
import { ErrorNotice } from "../../../components";
import type { SelectedCell } from "../../entry/selectedCell";
import { FormulaEditor, type SaveInput, type SaveOutcome } from "../../formula/FormulaEditor";
import { FormulaPanel } from "../../formula/FormulaPanel";
import {
  FORBIDDEN_HINT,
  RESERVED_HINT,
  draftFromRules,
  emptyDraft,
  rulesFromDraft,
  validateColumnName,
  validateTag,
  type RulesDraft,
} from "../rules";
import {
  COLUMN_KIND_LABELS,
  COLUMN_NAME_MAX,
  COLUMN_TYPES,
  COLUMN_TYPE_LABELS,
  DATASET_NAME_MAX,
  DATE_UNITS,
  DATE_UNIT_LABELS,
  TAG_MAX,
  type Column,
  type ColumnRules,
  type ColumnType,
  type DatasetDetail,
  type DateUnit,
} from "../types";

export type Selection = { kind: "dataset" } | { kind: "add" } | { kind: "addFormula" } | { kind: "column"; id: number };
export type Feedback = null | { kind: "ok"; text: string } | { kind: "error"; error: unknown };

/** 저장 동작. expected_version은 작업공간이 붙이고, 실패는 Feedback으로 올라가므로 여기서는 던지지 않는다. */
export interface Actions {
  addColumn: (body: {
    display_name: string;
    type: ColumnType;
    required: boolean;
    rules?: ColumnRules;
    tag?: string;
    position?: number;
  }) => Promise<void>;
  updateColumn: (
    columnId: number,
    body: { display_name?: string; required?: boolean; rules?: ColumnRules; tag?: string | null; position?: number },
  ) => Promise<void>;
  updateDataset: (body: { name?: string; date_unit?: DateUnit; base_date_column_id?: number | null }) => Promise<void>;
  /** 계산 열 만들기(D4)·수식 바꾸기(D5). 실패는 던지지 않고 수식 편집기가 오류 위치와 함께 보여 주도록 돌려준다. */
  saveFormula: (input: SaveInput) => Promise<SaveOutcome>;
}

const MIN_WIDTH = 280;
const MAX_WIDTH = 640;

interface InspectorProps {
  detail: DatasetDetail;
  columns: Column[];
  /** 역할 기준 정의 권한(permissions.define). 보관 여부는 archived로 따로 본다. */
  canDefine: boolean;
  /** 보관된 데이터셋: 편집은 모두 막고, 수식 보기·검사·미리보기는 그대로 둔다(FU-2b). */
  archived?: boolean;
  selection: Selection;
  feedback: Feedback;
  actions: Actions;
  onSelect: (selection: Selection) => void;
  /** 그리드에서 고른 계산 열 칸 */
  selectedCell?: SelectedCell | null;
}

/** S4 우측 Inspector. 접기·폭 조절이 되고, 정의 권한이 없으면 모든 입력칸이 읽기 전용이다. */
export function Inspector({ detail, columns, canDefine: canDefineByRole, archived = false, selection, feedback, actions, selectedCell }: InspectorProps) {
  const canDefine = canDefineByRole && !archived;
  const [open, setOpen] = useState(true);
  const [width, setWidth] = useState(360);
  const widthId = useId();

  const selected = selection.kind === "column" ? columns.find((c) => c.id === selection.id) : undefined;

  if (!open) {
    return (
      <aside aria-label="Inspector" className="inspector collapsed" style={{ width: "40px" }}>
        <button type="button" onClick={() => setOpen(true)} aria-label="Inspector 펼치기">
          ◀
        </button>
      </aside>
    );
  }

  return (
    <aside aria-label="Inspector" className="inspector" style={{ width: `${width}px` }}>
      <div className="inspector-bar">
        <label htmlFor={widthId} className="muted">
          폭
        </label>
        <input
          id={widthId}
          type="range"
          aria-label="Inspector 폭"
          min={MIN_WIDTH}
          max={MAX_WIDTH}
          step={10}
          value={width}
          onChange={(event) => setWidth(Number(event.target.value))}
        />
        <button type="button" onClick={() => setOpen(false)} aria-label="Inspector 접기">
          ▶
        </button>
      </div>
      {archived ? (
        <p className="muted" data-testid="archived-notice">
          보관된 데이터셋이라 지금은 읽기 전용입니다. 수식 보기와 검사·미리보기는 쓸 수 있습니다.
        </p>
      ) : canDefine ? null : (
        <p className="muted" data-testid="readonly-notice">
          이 데이터셋은 팀의 정의 담당자만 바꿀 수 있습니다. 지금은 읽기 전용입니다.
        </p>
      )}
      {feedback?.kind === "ok" ? (
        <p role="status" className="state state-ok">
          {feedback.text}
        </p>
      ) : null}
      {feedback?.kind === "error" ? <ErrorNotice error={feedback.error} /> : null}
      {selection.kind === "dataset" ? (
        <DatasetSettingsForm key={`d${detail.def_version}`} detail={detail} columns={columns} readOnly={!canDefine} archived={archived} actions={actions} />
      ) : null}
      {selection.kind === "add" && canDefine ? <ColumnForm key="add" mode="add" readOnly={false} actions={actions} /> : null}
      {selection.kind === "addFormula" && canDefine ? (
        <FormulaEditor key="addFormula" datasetId={detail.id} columns={columns} editing={null} initialExpression="" save={actions.saveFormula} />
      ) : null}
      {selected?.kind === "formula" ? (
        <>
          <FormulaPanel
            key={selected.id}
            datasetId={detail.id}
            column={selected}
            columns={columns}
            canDefine={canDefineByRole}
            archived={archived}
            version={detail.def_version}
            selectedCell={selectedCell}
            save={actions.saveFormula}
          />
          <details className="column-info">
            <summary>열 정보</summary>
            <ColumnForm key={`c${selected.id}:${JSON.stringify(selected)}`} mode="edit" column={selected} readOnly actions={actions} />
          </details>
        </>
      ) : null}
      {selected && selected.kind !== "formula" ? (
        <ColumnForm
          // 낡은 값이 남지 않게, 서버 값이 바뀌면 입력칸을 새 값으로 시작한다.
          key={`c${selected.id}:${JSON.stringify(selected)}`}
          mode="edit"
          column={selected}
          readOnly={!canDefine}
          archived={archived}
          actions={actions}
        />
      ) : null}
      {selection.kind === "column" && !selected ? <p className="muted">선택한 열을 찾을 수 없습니다. 열 목록에서 다시 골라 주세요.</p> : null}
    </aside>
  );
}

function Field({ label, htmlFor, error, hint, children }: { label: string; htmlFor: string; error?: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <label htmlFor={htmlFor}>{label}</label>
      {children}
      {hint ? <span className="muted hint">{hint}</span> : null}
      {error ? (
        <span role="alert" className="state-error-inline">
          {error}
        </span>
      ) : null}
    </div>
  );
}

/* ---------------- 데이터셋 설정 (B4) ---------------- */

function DatasetSettingsForm({
  detail,
  columns,
  readOnly,
  archived = false,
  actions,
}: {
  detail: DatasetDetail;
  columns: Column[];
  readOnly: boolean;
  archived?: boolean;
  actions: Actions;
}) {
  const ids = { name: useId(), unit: useId(), base: useId() };
  const [name, setName] = useState(detail.name);
  const [unit, setUnit] = useState<DateUnit>(detail.date_unit);
  const [base, setBase] = useState<string>(detail.base_date_column_id === null ? "" : String(detail.base_date_column_id));
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const trimmed = name.normalize("NFC").trim();
  const baseValue = base === "" ? null : Number(base);
  const dirty = trimmed !== detail.name || unit !== detail.date_unit || baseValue !== detail.base_date_column_id;
  const dateColumns = columns.filter((c) => c.kind === "raw" && c.type === "date");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (readOnly || busy || !dirty) return;
    if (trimmed === "" || trimmed.length > DATASET_NAME_MAX) {
      setMessage(`데이터셋 이름은 1~${DATASET_NAME_MAX}자로 입력해 주세요.`);
      return;
    }
    setMessage(null);
    const body: { name?: string; date_unit?: DateUnit; base_date_column_id?: number | null } = {};
    if (trimmed !== detail.name) body.name = trimmed;
    if (unit !== detail.date_unit) body.date_unit = unit;
    if (baseValue !== detail.base_date_column_id) body.base_date_column_id = baseValue;
    setBusy(true);
    await actions.updateDataset(body);
    setBusy(false);
  }

  return (
    <form className="inspector-form" aria-label="데이터셋 설정" onSubmit={(event) => void submit(event)} noValidate>
      <h2>데이터셋 설정</h2>
      <Field label="이름" htmlFor={ids.name}>
        <input id={ids.name} value={name} maxLength={DATASET_NAME_MAX} disabled={readOnly} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field
        label="날짜 단위"
        htmlFor={ids.unit}
        hint="행이 한 건이라도 입력된 데이터셋은 날짜 단위와 기준 날짜 열을 바꿀 수 없습니다."
      >
        <select id={ids.unit} value={unit} disabled={readOnly} onChange={(event) => setUnit(event.target.value as DateUnit)}>
          {DATE_UNITS.map((u) => (
            <option key={u} value={u}>
              {DATE_UNIT_LABELS[u]}
            </option>
          ))}
        </select>
      </Field>
      <Field label="기준 날짜 열" htmlFor={ids.base} hint="한 기간에 한 행만 들어가도록 기간을 정하는 날짜 열입니다. 입력 열 중 날짜 열만 고를 수 있습니다.">
        <select id={ids.base} value={base} disabled={readOnly} onChange={(event) => setBase(event.target.value)}>
          <option value="">없음</option>
          {dateColumns.map((column) => (
            <option key={column.id} value={column.id}>
              {column.display_name}
            </option>
          ))}
        </select>
      </Field>
      {message ? (
        <p role="alert" className="state-error-inline">
          {message}
        </p>
      ) : null}
      {readOnly && !archived ? null : (
        <button type="submit" disabled={readOnly || !dirty || busy}>
          저장
        </button>
      )}
    </form>
  );
}

/* ---------------- 열 추가·수정 (B5·B6) ---------------- */

type ColumnFormProps =
  | { mode: "add"; readOnly: boolean; archived?: boolean; actions: Actions }
  | { mode: "edit"; column: Column; readOnly: boolean; archived?: boolean; actions: Actions };

function ColumnForm(props: ColumnFormProps) {
  const column = props.mode === "edit" ? props.column : null;
  const readOnly = props.readOnly;
  const ids = {
    name: useId(),
    type: useId(),
    required: useId(),
    min: useId(),
    max: useId(),
    decimals: useId(),
    maxLength: useId(),
    dateMin: useId(),
    dateMax: useId(),
    options: useId(),
    tag: useId(),
    position: useId(),
  };
  const initialType: ColumnType = column?.type ?? "text";
  const initialDraft = column ? draftFromRules(column.type, column.rules) : emptyDraft();
  const [name, setName] = useState(column?.display_name ?? "");
  const [nameTouched, setNameTouched] = useState(false);
  const [type, setType] = useState<ColumnType>(initialType);
  const [required, setRequired] = useState(column?.required ?? false);
  const [draft, setDraft] = useState<RulesDraft>(initialDraft);
  const [tag, setTag] = useState(column?.tag ?? "");
  const [position, setPosition] = useState(column ? String(column.position) : "");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  const nameError = validateColumnName(name);
  const tagError = type === "number" ? validateTag(tag) : null;
  const positionTrim = position.trim();
  const positionError = positionTrim !== "" && !/^\d+$/.test(positionTrim) ? "위치는 0 이상의 정수로 입력해 주세요." : null;
  const setField = (key: keyof RulesDraft, value: string) => setDraft((previous) => ({ ...previous, [key]: value }));

  const normalizedName = name.normalize("NFC").trim();
  const normalizedTag = tag.normalize("NFC").trim();
  const dirty = column
    ? normalizedName !== column.display_name ||
      required !== column.required ||
      JSON.stringify(draft) !== JSON.stringify(initialDraft) ||
      (type === "number" && normalizedTag !== (column.tag ?? "")) ||
      (positionTrim !== "" && Number(positionTrim) !== column.position)
    : true;
  const blocked = nameError !== null || tagError !== null || positionError !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (readOnly || busy || blocked || !dirty) return;
    const parsed = rulesFromDraft(type, draft);
    if (!parsed.ok) {
      setErrors(parsed.errors);
      return;
    }
    setErrors({});
    setBusy(true);
    try {
      if (!column) {
        await props.actions.addColumn({
          display_name: normalizedName,
          type,
          required,
          ...(Object.keys(parsed.rules).length > 0 ? { rules: parsed.rules } : {}),
          ...(type === "number" && normalizedTag !== "" ? { tag: normalizedTag } : {}),
          ...(positionTrim !== "" ? { position: Number(positionTrim) } : {}),
        });
      } else {
        const body: Parameters<Actions["updateColumn"]>[1] = {};
        if (normalizedName !== column.display_name) body.display_name = normalizedName;
        if (required !== column.required) body.required = required;
        if (JSON.stringify(draft) !== JSON.stringify(initialDraft)) body.rules = parsed.rules;
        if (type === "number" && normalizedTag !== (column.tag ?? "")) body.tag = normalizedTag === "" ? null : normalizedTag;
        if (positionTrim !== "" && Number(positionTrim) !== column.position) body.position = Number(positionTrim);
        await props.actions.updateColumn(column.id, body);
      }
    } finally {
      setBusy(false);
    }
  }

  const title = column ? `열 수정: ${column.display_name}` : "열 추가";
  return (
    <form className="inspector-form" aria-label={title} onSubmit={(event) => void submit(event)} noValidate>
      <h2>{title}</h2>
      <Field
        label="열 이름"
        htmlFor={ids.name}
        hint={
          <span data-testid="name-hint">
            {COLUMN_NAME_MAX}자 이하. {FORBIDDEN_HINT} {RESERVED_HINT}
          </span>
        }
      >
        <input
          id={ids.name}
          value={name}
          maxLength={COLUMN_NAME_MAX}
          disabled={readOnly}
          onChange={(event) => {
            setName(event.target.value);
            setNameTouched(true);
          }}
        />
      </Field>
      {nameError && (nameTouched || name !== "") ? (
        <p role="alert" className="state-error-inline" data-testid="name-error">
          {nameError}
        </p>
      ) : null}

      {column ? (
        <>
          <p data-testid="type-locked">
            타입: {COLUMN_TYPE_LABELS[column.type] ?? column.type} <span className="muted">(바꿀 수 없습니다. 다른 타입이 필요하면 새 열을 추가하세요.)</span>
          </p>
          <p data-testid="kind-locked">
            종류: {COLUMN_KIND_LABELS[column.kind] ?? column.kind} <span className="muted">(바꿀 수 없습니다)</span>
          </p>
        </>
      ) : (
        <Field label="타입" htmlFor={ids.type} hint="열을 만든 뒤에는 타입을 바꿀 수 없습니다.">
          <select
            id={ids.type}
            value={type}
            onChange={(event) => {
              setType(event.target.value as ColumnType);
              setDraft(emptyDraft());
              setErrors({});
            }}
          >
            {COLUMN_TYPES.map((t) => (
              <option key={t} value={t}>
                {COLUMN_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </Field>
      )}

      <div className="field inline">
        <input id={ids.required} type="checkbox" checked={required} disabled={readOnly} onChange={(event) => setRequired(event.target.checked)} />
        <label htmlFor={ids.required}>필수 입력</label>
      </div>

      {type === "number" ? (
        <>
          <Field label="최솟값" htmlFor={ids.min} error={errors.min} hint="저장하면 서버가 숫자 표기를 정리합니다(예: -5.50은 -5.5). 저장 뒤 입력칸이 정리된 값으로 바뀌어도 같은 값입니다.">
            <input id={ids.min} inputMode="decimal" value={draft.min} disabled={readOnly} onChange={(event) => setField("min", event.target.value)} />
          </Field>
          <Field label="최댓값" htmlFor={ids.max} error={errors.max}>
            <input id={ids.max} inputMode="decimal" value={draft.max} disabled={readOnly} onChange={(event) => setField("max", event.target.value)} />
          </Field>
          <Field label="소수 자릿수" htmlFor={ids.decimals} error={errors.decimals}>
            <input id={ids.decimals} inputMode="numeric" value={draft.decimals} disabled={readOnly} onChange={(event) => setField("decimals", event.target.value)} />
          </Field>
          <Field label="구분 태그" htmlFor={ids.tag} error={tagError ?? undefined} hint={`같은 태그의 숫자 열을 수식에서 한 번에 합칠 때 씁니다(${TAG_MAX}자 이하).`}>
            <input id={ids.tag} value={tag} maxLength={TAG_MAX} disabled={readOnly} onChange={(event) => setTag(event.target.value)} />
          </Field>
        </>
      ) : null}
      {type === "text" ? (
        <Field label="최대 글자 수" htmlFor={ids.maxLength} error={errors.maxLength}>
          <input id={ids.maxLength} inputMode="numeric" value={draft.maxLength} disabled={readOnly} onChange={(event) => setField("maxLength", event.target.value)} />
        </Field>
      ) : null}
      {type === "date" ? (
        <>
          <Field label="가장 이른 날짜" htmlFor={ids.dateMin} error={errors.dateMin} hint="예: 2026-01-31">
            <input id={ids.dateMin} value={draft.dateMin} placeholder="YYYY-MM-DD" disabled={readOnly} onChange={(event) => setField("dateMin", event.target.value)} />
          </Field>
          <Field label="가장 늦은 날짜" htmlFor={ids.dateMax} error={errors.dateMax}>
            <input id={ids.dateMax} value={draft.dateMax} placeholder="YYYY-MM-DD" disabled={readOnly} onChange={(event) => setField("dateMax", event.target.value)} />
          </Field>
        </>
      ) : null}
      {type === "choice" ? (
        <Field label="선택 목록 (한 줄에 하나)" htmlFor={ids.options} error={errors.options}>
          <textarea id={ids.options} rows={5} value={draft.options} disabled={readOnly} onChange={(event) => setField("options", event.target.value)} />
        </Field>
      ) : null}

      <Field
        label="위치"
        htmlFor={ids.position}
        error={positionError ?? undefined}
        hint={column ? "열이 놓이는 순서입니다." : "비워 두면 맨 뒤에 놓입니다."}
      >
        <input id={ids.position} inputMode="numeric" value={position} disabled={readOnly} onChange={(event) => setPosition(event.target.value)} />
      </Field>

      {readOnly && !(props.archived && column?.kind !== "formula") ? (
        column?.kind === "formula" ? (
          <p className="muted">계산 열의 이름·위치는 여기서 고칠 수 없습니다. 수식은 아래에서 확인하고 고칩니다.</p>
        ) : null
      ) : (
        <button type="submit" disabled={readOnly || blocked || !dirty || busy}>
          {column ? "저장" : "열 추가"}
        </button>
      )}
    </form>
  );
}
