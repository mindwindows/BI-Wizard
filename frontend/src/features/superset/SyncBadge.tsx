import { SYNC_LABELS, type SyncStatus } from "./types";

/** 동기 상태 배지. 글자로도 구분되게 한다(색에만 의존하지 않음). */
export function SyncBadge({ status }: { status: SyncStatus }) {
  return (
    <span className={`badge sync-badge sync-${status}`} data-status={status}>
      {SYNC_LABELS[status]}
    </span>
  );
}
