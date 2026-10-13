import { embedDashboard, type EmbeddedDashboard } from "@superset-ui/embedded-sdk";
import { useEffect, useRef, useState } from "react";
import { supersetDomain } from "../../config";
import { requestGuestToken, tokenProblemOf, tokenProblemText } from "./guestToken";
import type { Dashboard, TokenProblem } from "./types";

/** iframe이 뜬 뒤 이 시간이 지나도 안이 비어 있으면 임베드 허용 도메인 설정을 의심하는 안내를 보여 준다(ms). */
export const EMPTY_CHECK_MS = 15_000;

type Phase = "loading" | "ready" | "failed";

/**
 * 같은 출처(origin)의 iframe 안이 비어 있는지 본다. Superset 임베드 화면은 `#app` 안에 React가 그린다.
 * 허용 도메인이 맞지 않으면 Superset이 JSON 403만 돌려주어 `#app`이 없다.
 * SDK는 iframe load만 보고 성공으로 끝나므로(허용 도메인 불일치를 감지하지 못함) 이 휴리스틱으로 보완한다.
 * 안을 읽을 수 없으면(다른 출처) 판단하지 않는다(false).
 */
export function looksEmpty(iframe: HTMLIFrameElement | null): boolean {
  if (!iframe) return false;
  let doc: Document | null;
  try {
    doc = iframe.contentDocument;
  } catch {
    return false;
  }
  if (!doc || !doc.body) return false;
  const app = doc.getElementById("app");
  return !app || app.childElementCount === 0;
}

interface InstanceProps {
  dashboard: Dashboard;
  onRetry: () => void;
}

/**
 * 대시보드 한 개를 Superset Embedded SDK로 마운트한다. 입장권(guest token)은 fetchGuestToken 콜백의
 * 반환값으로만 SDK에 건네며, 상태·ref·저장소·URL·로그·오류 메시지에 두지 않는다.
 *
 * 정리 규칙(프로브 확인, docs/research/fu1e-probes.md 5-3): SDK는 embedDashboard의 Promise가 풀리기 전에는
 * unmount 핸들이 없고, 정리하지 않으면 갱신 타이머가 10초마다 영구히 남는다. 그래서 Promise가 풀린 뒤에 늦게라도
 * unmount()를 부른다(언마운트·대시보드 전환·엄격 모드 이중 마운트 공통).
 */
function EmbedInstance({ dashboard, onRetry }: InstanceProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [problem, setProblem] = useState<TokenProblem | null>(null);
  const [looksBlank, setLooksBlank] = useState(false);

  const dashboardId = dashboard.id;
  const embeddedUuid = dashboard.embedded_uuid;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let disposed = false;
    let handle: EmbeddedDashboard | null = null;
    let emptyTimer: ReturnType<typeof setTimeout> | undefined;
    // 인스턴스마다 새 마운트 칸을 쓴다. SDK의 unmount()가 칸 전체를 비우므로, 칸을 공유하면
    // 엄격 모드의 이전 인스턴스 정리가 새 인스턴스의 iframe을 지울 수 있다.
    const mountPoint = document.createElement("div");
    mountPoint.className = "embed-mount";
    container.appendChild(mountPoint);

    const fetchGuestToken = async (): Promise<string> => {
      if (disposed) throw new Error("종료됨");
      try {
        const token = await requestGuestToken(dashboardId);
        if (!disposed) setProblem(null);
        return token;
      } catch (error) {
        if (!disposed) setProblem(tokenProblemOf(error));
        throw error;
      }
    };

    // 엄격 모드의 즉시 정리(같은 커밋 안)에서는 시작하지 않아 입장권 요청이 낭비되지 않는다.
    queueMicrotask(() => {
      if (disposed) return;
      embedDashboard({
        id: embeddedUuid,
        supersetDomain: supersetDomain(),
        mountPoint,
        fetchGuestToken,
        dashboardUiConfig: { hideTitle: false },
        iframeTitle: "대시보드",
      }).then(
        (embedded) => {
          if (disposed) {
            embedded.unmount();
            return;
          }
          handle = embedded;
          setPhase("ready");
          emptyTimer = setTimeout(() => {
            if (!disposed && looksEmpty(mountPoint.querySelector("iframe"))) setLooksBlank(true);
          }, EMPTY_CHECK_MS);
        },
        (error: unknown) => {
          if (disposed) return;
          // 첫 입장권 요청 실패는 SDK가 재시도하지 않고 iframe을 지운 채 거부한다 -> "다시 시도" 버튼.
          setProblem((current) => current ?? tokenProblemOf(error));
          setPhase("failed");
        },
      );
    });

    return () => {
      disposed = true;
      if (emptyTimer !== undefined) clearTimeout(emptyTimer);
      handle?.unmount();
      handle = null;
      mountPoint.remove();
    };
  }, [dashboardId, embeddedUuid]);

  return (
    <div className="embed-wrap" data-testid="dashboard-embed">
      {phase === "failed" ? (
        <div role="alert" className="state state-error" data-testid="embed-failed">
          <p>대시보드를 열지 못했습니다. {problem ? tokenProblemText(problem) : "잠시 뒤 다시 시도해 주세요."}</p>
          {problem?.requestId ? <p className="muted">문의 번호: {problem.requestId}</p> : null}
          <button type="button" onClick={onRetry}>
            다시 시도
          </button>
        </div>
      ) : null}
      {phase === "loading" ? (
        <p role="status" className="state state-loading">
          대시보드를 불러오는 중…
        </p>
      ) : null}
      {phase === "ready" && problem ? (
        <div role="alert" className="state state-error" data-testid="embed-refresh-problem">
          <p>접속 허가를 갱신하지 못했습니다. {tokenProblemText(problem)} 잠시 뒤 자동으로 다시 시도합니다.</p>
          {problem.requestId ? <p className="muted">문의 번호: {problem.requestId}</p> : null}
        </div>
      ) : null}
      {phase === "ready" && looksBlank ? (
        <div role="status" className="state state-error" data-testid="embed-blank-hint">
          <p>대시보드 화면이 비어 있습니다. 관리자라면 Superset에서 이 대시보드의 임베드 허용 도메인 설정을 확인하세요. 허용 도메인에는 이 포털의 주소({window.location.origin})가 들어 있어야 합니다.</p>
        </div>
      ) : null}
      <div ref={containerRef} className="embed-frame" hidden={phase === "failed"} />
    </div>
  );
}

/**
 * 대시보드 임베드. "다시 시도"는 인스턴스를 새로 마운트한다(key). 대시보드마다 별도 마운트이므로
 * 호출하는 쪽에서 key={dashboard.id}를 준다.
 */
export function DashboardEmbed({ dashboard }: { dashboard: Dashboard }) {
  const [attempt, setAttempt] = useState(0);
  return <EmbedInstance key={`${dashboard.id}:${dashboard.embedded_uuid}:${attempt}`} dashboard={dashboard} onRetry={() => setAttempt((value) => value + 1)} />;
}
