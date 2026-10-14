import { useEffect, useId, useRef, useState } from "react";
import { ApiError } from "../../api";
import { describeError } from "../../components";
import { archiveDataset, restoreDataset } from "./api";
import type { DatasetDetail, DatasetStatus } from "./types";

/** 05 §2-2 B7·B8 확인창 문구(04 §4 S2, 03b 30-1 결정 1). 뜻과 한계를 쉬운 말로 적는다. */
export const ARCHIVE_CONFIRM_TEXT = "입력과 정의 변경이 멈추고 포털 목록에서 숨겨집니다. 복구하면 다시 고칠 수 있습니다.";
export const ARCHIVE_LIMIT_TEXT =
  "Superset 차트와 읽기 전용 데이터로는 계속 보입니다. 데이터를 아예 감추려면 영구 삭제가 따로 필요합니다(아직 없음).";
export const RESTORE_CONFIRM_TEXT = "다시 입력과 정의 변경을 할 수 있게 됩니다.";
export const FORBIDDEN_ARCHIVE_TEXT = "정의 담당자만 할 수 있습니다.";

export type ArchiveKind = "archive" | "restore";

export const archiveKindFor = (status: DatasetStatus): ArchiveKind => (status === "archived" ? "restore" : "archive");

/** 성공 안내 문구(목록·작업공간 공통) */
export const doneText = (kind: ArchiveKind, name: string): string =>
  kind === "archive" ? `'${name}' 데이터셋을 보관했습니다. 기본 목록에서는 숨겨지고 '보관됨' 보기에서 볼 수 있습니다.` : `'${name}' 데이터셋을 복구했습니다. 다시 입력과 정의 변경을 할 수 있습니다.`;

/** 실패 문구. 403은 권한 안내, 503 DEFINITION_BUSY는 다시 시도 안내(describeApiError가 retry_after까지 붙인다). */
function failureText(error: unknown): string {
  if (error instanceof ApiError && error.code === "FORBIDDEN") return FORBIDDEN_ARCHIVE_TEXT;
  return describeError(error).message;
}

interface Props {
  dataset: { id: number; name: string; status: DatasetStatus };
  /** 성공(200)하면 갱신된 상세와 함께 부른다. */
  onDone: (kind: ArchiveKind, detail: DatasetDetail) => void;
  /** 버튼에 붙일 접근성 이름 꼬리(목록의 여러 행 구별용) */
  className?: string;
}

/**
 * 보관/복구 버튼과 단순 확인창(이름 입력 없음, 취소/확인). 호출 쪽이 정의 담당자일 때만 그린다.
 * 실패하면 창을 닫지 않고 문구를 보이며 확인 버튼이 "다시 시도"가 된다.
 */
export function ArchiveAction({ dataset, onDone, className }: Props) {
  const kind = archiveKindFor(dataset.status);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const label = kind === "archive" ? "보관" : "복구";

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const detail = kind === "archive" ? await archiveDataset(dataset.id) : await restoreDataset(dataset.id);
      setBusy(false);
      setOpen(false);
      onDone(kind, detail);
    } catch (caught) {
      setBusy(false);
      setError(failureText(caught));
    }
  }

  return (
    <>
      <button
        type="button"
        className={className}
        aria-label={`${dataset.name} ${label}`}
        onClick={() => {
          setError(null);
          setOpen(true);
        }}
      >
        {label}
      </button>
      {open ? (
        <ConfirmDialog
          kind={kind}
          name={dataset.name}
          busy={busy}
          error={error}
          onConfirm={() => void confirm()}
          onCancel={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

function ConfirmDialog({
  kind,
  name,
  busy,
  error,
  onConfirm,
  onCancel,
}: {
  kind: ArchiveKind;
  name: string;
  busy: boolean;
  error: string | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => headingRef.current?.focus(), []);
  useEffect(() => {
    if (busy) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [busy, onCancel]);

  const archive = kind === "archive";
  return (
    <div className="modal-backdrop">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal modal-confirm">
        <h2 id={titleId} ref={headingRef} tabIndex={-1}>
          {archive ? `'${name}' 데이터셋을 보관할까요?` : `'${name}' 데이터셋을 복구할까요?`}
        </h2>
        {archive ? (
          <>
            <p>{ARCHIVE_CONFIRM_TEXT}</p>
            <p className="archive-limit">
              <strong>{ARCHIVE_LIMIT_TEXT}</strong>
            </p>
          </>
        ) : (
          <p>{RESTORE_CONFIRM_TEXT}</p>
        )}
        {error ? (
          <p role="alert" className="state-error-inline">
            {error}
          </p>
        ) : null}
        <div className="actions">
          <button type="button" className="primary" disabled={busy} onClick={onConfirm}>
            {busy ? "처리하는 중…" : error ? "다시 시도" : archive ? "보관하기" : "복구하기"}
          </button>
          <button type="button" disabled={busy} onClick={onCancel}>
            취소
          </button>
        </div>
      </div>
    </div>
  );
}
