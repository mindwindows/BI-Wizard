/** 05 E3~E5 대시보드 연결. */
export interface Dashboard {
  id: number;
  name: string;
  embedded_uuid: string;
  is_active: boolean;
}

export interface DashboardList {
  items: Dashboard[];
  total: number;
}

/** E6 실패의 분류. 화면은 이 분류와 retryAfter(초)만 상태로 갖는다. 토큰·응답 본문은 갖지 않는다. */
export type TokenProblemKind = "RATE" | "UNAVAILABLE" | "REJECTED" | "LOGGED_OUT" | "GONE" | "OTHER";

export interface TokenProblem {
  kind: TokenProblemKind;
  /** 429의 재시도 안내(초). 없으면 null */
  retryAfter: number | null;
  /** 요청 번호(문의용). 없으면 null */
  requestId: string | null;
}
