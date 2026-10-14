import { useId, useState, type FormEvent } from "react";
import { FORBIDDEN_HINT, RESERVED_HINT, validateColumnName, validateTag } from "../rules";
import { COLUMN_NAME_MAX, TAG_MAX, type Column } from "../types";

export type MoveDirection = "up" | "down";

/** 이름을 바꿔도 수식이 깨지지 않는 이유(07 §1·§8: 수식은 열 번호 참조 AST로 저장되고 수식 보기는 현재 이름으로 풀어 쓴다). */
export const RENAME_HINT =
  "이름을 바꿔도 이 열을 쓰는 다른 계산 열의 수식은 그대로 동작합니다. 수식은 이름이 아니라 열 번호로 저장되고, 수식 보기에는 새 이름으로 표시됩니다.";
export const TAG_HINT = `같은 태그의 숫자 열을 SUMTAG("태그")로 한 번에 더할 때 씁니다(${TAG_MAX}자 이하). 바꾸면 SUMTAG를 쓰는 수식의 값이 달라질 수 있고, 계산 열끼리 서로를 참조하는 순환이 생기면 저장되지 않습니다.`;
export const TAG_NUMBER_ONLY = "구분 태그는 결과가 숫자인 계산 열에만 쓸 수 있습니다.";

interface Props {
  column: Column;
  /** 위치 순으로 정렬된 데이터셋의 모든 열(이동 한계 판단용) */
  columns: Column[];
  /** 역할 기준 정의 권한(permissions.define) */
  canDefine: boolean;
  archived: boolean;
  onSave: (body: { display_name?: string; tag?: string | null }) => Promise<void>;
  onMove: (direction: MoveDirection) => Promise<void>;
}

/** S4 Inspector의 계산 열 관리: 이름 변경·구분 태그·위/아래 이동(B6). 수식 자체는 FormulaPanel이 맡는다. */
export function FormulaColumnSettings({ column, columns, canDefine, archived, onSave, onMove }: Props) {
  const ids = { name: useId(), tag: useId() };
  const [name, setName] = useState(column.display_name);
  const [tag, setTag] = useState(column.tag ?? "");
  const [busy, setBusy] = useState(false);
  const readOnly = !canDefine || archived;
  const isNumber = column.type === "number";

  const index = columns.findIndex((c) => c.id === column.id);
  const normalizedName = name.normalize("NFC").trim();
  const normalizedTag = tag.normalize("NFC").trim();
  const nameError = validateColumnName(name);
  const tagError = isNumber ? validateTag(tag) : null;
  const nameChanged = normalizedName !== column.display_name;
  const tagChanged = isNumber && normalizedTag !== (column.tag ?? "");
  const blocked = nameError !== null || tagError !== null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (readOnly || busy || blocked || !(nameChanged || tagChanged)) return;
    const body: { display_name?: string; tag?: string | null } = {};
    if (nameChanged) body.display_name = normalizedName;
    if (tagChanged) body.tag = normalizedTag === "" ? null : normalizedTag;
    setBusy(true);
    try {
      await onSave(body);
    } finally {
      setBusy(false);
    }
  }

  async function move(direction: MoveDirection) {
    if (readOnly || busy) return;
    setBusy(true);
    try {
      await onMove(direction);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="계산 열 관리" className="formula-column-settings">
      <h3>계산 열 이름·순서·태그</h3>
      <form className="inspector-form" aria-label="계산 열 이름·태그" onSubmit={(event) => void submit(event)} noValidate>
        <div className="field">
          <label htmlFor={ids.name}>열 이름</label>
          <input id={ids.name} value={name} maxLength={COLUMN_NAME_MAX} disabled={readOnly} onChange={(event) => setName(event.target.value)} />
          <span className="muted hint" data-testid="rename-hint">
            {COLUMN_NAME_MAX}자 이하. {FORBIDDEN_HINT} {RESERVED_HINT} {RENAME_HINT}
          </span>
          {nameError && name !== column.display_name ? (
            <span role="alert" className="state-error-inline" data-testid="name-error">
              {nameError}
            </span>
          ) : null}
        </div>
        {isNumber ? (
          <div className="field">
            <label htmlFor={ids.tag}>구분 태그</label>
            <input id={ids.tag} value={tag} maxLength={TAG_MAX} disabled={readOnly} onChange={(event) => setTag(event.target.value)} />
            <span className="muted hint">{TAG_HINT}</span>
            {tagError ? (
              <span role="alert" className="state-error-inline">
                {tagError}
              </span>
            ) : null}
          </div>
        ) : (
          <p className="muted" data-testid="tag-number-only">
            {TAG_NUMBER_ONLY}
          </p>
        )}
        {canDefine ? (
          <button type="submit" disabled={readOnly || blocked || busy || !(nameChanged || tagChanged)}>
            이름·태그 저장
          </button>
        ) : null}
      </form>
      <div className="column-move" role="group" aria-label="열 위치">
        <p data-testid="column-position">
          현재 위치: {index + 1}번째 / 전체 {columns.length}개 <span className="muted">(그리드의 열 순서와 같습니다)</span>
        </p>
        {canDefine ? (
          <div className="actions">
            <button type="button" disabled={readOnly || busy || index <= 0} onClick={() => void move("up")}>
              위로 이동
            </button>
            <button type="button" disabled={readOnly || busy || index < 0 || index >= columns.length - 1} onClick={() => void move("down")}>
              아래로 이동
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
