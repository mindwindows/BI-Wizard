/** 04 부록 A: pending(등록 행이 없거나 갱신 필요) / registered / failed */
export type SyncStatus = "pending" | "registered" | "failed";

/** 05 E1 */
export interface SupersetDatasetStatus {
  dataset_id: number;
  superset_name: string;
  sync_status: SyncStatus;
  synced_at: string | null;
  /** 관리자에게만 값이 있고 다른 사용자는 null */
  last_error: string | null;
}

export const SYNC_LABELS: Record<SyncStatus, string> = {
  pending: "등록 대기",
  registered: "등록됨",
  failed: "등록 실패",
};
