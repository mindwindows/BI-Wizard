import type { ReactNode } from "react";
import { ApiError } from "./api";

export function Loading({ label = "불러오는 중" }: { label?: string }) {
  return (
    <p role="status" className="state state-loading">
      {label}…
    </p>
  );
}

/** error.code로 분기하는 자리. 코드별 안내는 화면 단위에서 늘린다. 문구는 서버 message를 우선한다. */
export function describeError(error: unknown): { message: string; requestId: string | null } {
  if (error instanceof ApiError) {
    return { message: error.message, requestId: error.requestId };
  }
  return { message: "화면을 표시하는 중 오류가 발생했습니다.", requestId: null };
}

export function ErrorNotice({ error, children }: { error: unknown; children?: ReactNode }) {
  const { message, requestId } = describeError(error);
  return (
    <div role="alert" className="state state-error">
      <p>{message}</p>
      {requestId ? <p className="muted">문의 번호: {requestId}</p> : null}
      {children}
    </div>
  );
}
