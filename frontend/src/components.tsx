import type { ReactNode } from "react";
import { ApiError } from "./api";
import { describeApiError } from "./errors";

export function Loading({ label = "불러오는 중" }: { label?: string }) {
  return (
    <p role="status" className="state state-loading">
      {label}…
    </p>
  );
}

/** error.code로 분기한 쉬운 한국어 문구(errors.ts). */
export function describeError(error: unknown): { message: string; requestId: string | null } {
  return { message: describeApiError(error), requestId: error instanceof ApiError ? error.requestId : null };
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
