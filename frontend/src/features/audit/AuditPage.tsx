import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api";
import { ErrorNotice, Loading } from "../../components";
import { useMe } from "../access/MeContext";
import type { User } from "../access/types";
import { listAllUsers, listAuditLogs } from "./api";
import { summarize } from "./summary";
import {
  ACTION_LABELS,
  AUDIT_ACTIONS,
  EMPTY_FILTERS,
  PAGE_SIZE,
  TARGET_TYPES,
  TARGET_TYPE_LABELS,
  isAuditAction,
  isTargetType,
  type AuditFilters,
  type AuditItem,
  type AuditPageData,
} from "./types";

const FORBIDDEN_TEXT = "관리자만 볼 수 있습니다";
const SERVER_ACTOR = "서버 명령";

interface Loaded {
  key: string;
  page?: AuditPageData;
  error?: unknown;
}

const sameFilters = (a: AuditFilters, b: AuditFilters) =>
  a.from === b.from && a.to === b.to && a.actor === b.actor && a.targetType === b.targetType && a.targetId === b.targetId && a.action === b.action;

const isEmptyFilters = (f: AuditFilters) => sameFilters(f, EMPTY_FILTERS);

/** 필터 입력 확인. 서버(422)에 가기 전에 알 수 있는 것만 알려 준다. 통과하면 null. */
export function validateFilters(f: AuditFilters): string | null {
  if (f.from && f.to && f.from > f.to) return "시작일이 종료일보다 늦습니다. 기간을 확인해 주세요.";
  if (f.targetType && f.targetId && !/^[1-9][0-9]{0,17}$/.test(f.targetId)) return "대상 번호는 1 이상의 정수로 입력해 주세요.";
  return null;
}

/** 시각 ISO 8601(`+09:00`, 서버가 한국 시간으로 준다)에서 초까지 보여 준다. */
const formatSecond = (iso: unknown): string => (typeof iso === "string" && iso.length >= 19 ? iso.slice(0, 19).replace("T", " ") : String(iso ?? ""));

function ForbiddenNotice() {
  return (
    <p role="alert" className="state state-error" data-testid="audit-forbidden">
      {FORBIDDEN_TEXT}
    </p>
  );
}

/** S10 감사 기록 목록(읽기 전용, 관리자 전용). 서버 권한 검사가 최종 방어선이며 화면도 직접 접속 때 한 번 더 막는다. */
export function AuditPage() {
  const { state } = useMe();
  if (state.status !== "ready") return null;
  if (!state.me.is_admin) {
    return (
      <section data-testid="screen-S10">
        <h1>S10 감사 기록</h1>
        <ForbiddenNotice />
      </section>
    );
  }
  return <AuditConsole />;
}

function AuditConsole() {
  const [draft, setDraft] = useState<AuditFilters>(EMPTY_FILTERS);
  const [applied, setApplied] = useState<AuditFilters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [formError, setFormError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [users, setUsers] = useState<User[] | null>(null);
  const [usersFailed, setUsersFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    listAllUsers(controller.signal)
      .then((list) => !controller.signal.aborted && setUsers(list))
      .catch(() => !controller.signal.aborted && setUsersFailed(true));
    return () => controller.abort();
  }, []);

  const requestKey = `${reloadKey}|${offset}|${JSON.stringify(applied)}`;
  useEffect(() => {
    const controller = new AbortController();
    listAuditLogs(applied, offset, controller.signal)
      .then((page) => !controller.signal.aborted && setLoaded({ key: requestKey, page }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key: requestKey, error }));
    return () => controller.abort();
    // requestKey가 applied·offset·reloadKey를 모두 담는다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey]);

  const userNames = useMemo(() => new Map((users ?? []).map((u) => [u.id, u.display_name])), [users]);
  const resolveUser = (id: number) => userNames.get(id);

  const loading = loaded?.key !== requestKey;
  const error = !loading ? loaded?.error : undefined;
  if (error instanceof ApiError && error.status === 403) {
    return (
      <section data-testid="screen-S10">
        <h1>S10 감사 기록</h1>
        <ForbiddenNotice />
      </section>
    );
  }

  const setField = (patch: Partial<AuditFilters>) => setDraft((current) => ({ ...current, ...patch }));
  const search = () => {
    const problem = validateFilters(draft);
    setFormError(problem);
    if (problem) return;
    setApplied(draft);
    setOffset(0);
    setReloadKey((value) => value + 1);
  };
  const clear = () => {
    setDraft(EMPTY_FILTERS);
    setApplied(EMPTY_FILTERS);
    setFormError(null);
    setOffset(0);
    setReloadKey((value) => value + 1);
  };

  const page = !loading ? loaded?.page : undefined;
  const items = page?.items ?? [];
  const total = page?.total ?? 0;
  const filtered = !isEmptyFilters(applied);
  const hasDraftChange = !sameFilters(draft, applied);

  return (
    <section data-testid="screen-S10" className="console">
      <h1>S10 감사 기록</h1>
      <p className="muted">
        데이터셋·열·수식 정의, 팀·소속·사용자, 대시보드 연결, 기준값의 변경 기록입니다. 읽기 전용이며 최신 기록부터 보입니다. 입력한 행 값과 수식 원문은 기록되지 않습니다.
      </p>

      <form
        className="toolbar audit-filters"
        aria-label="감사 기록 필터"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          search();
        }}
      >
        <label>
          시작일
          <input type="date" value={draft.from} max={draft.to || undefined} onChange={(e) => setField({ from: e.target.value })} />
        </label>
        <label>
          종료일
          <input type="date" value={draft.to} min={draft.from || undefined} onChange={(e) => setField({ to: e.target.value })} />
        </label>
        <label>
          행위자
          <select value={draft.actor} disabled={usersFailed || users === null} onChange={(e) => setField({ actor: e.target.value })}>
            <option value="">전체</option>
            {(users ?? []).map((user) => (
              <option key={user.id} value={String(user.id)}>
                {user.display_name}
                {user.is_active ? "" : " (사용 중지)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          대상 종류
          <select value={draft.targetType} onChange={(e) => setField({ targetType: e.target.value, targetId: "" })}>
            <option value="">전체</option>
            {TARGET_TYPES.map((type) => (
              <option key={type} value={type}>
                {TARGET_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </label>
        <label>
          대상 번호
          <input
            type="text"
            inputMode="numeric"
            size={16}
            value={draft.targetId}
            disabled={draft.targetType === ""}
            placeholder={draft.targetType === "" ? "종류를 먼저 선택" : "번호"}
            onChange={(e) => setField({ targetId: e.target.value.trim() })}
          />
        </label>
        <label>
          행위
          <select value={draft.action} onChange={(e) => setField({ action: e.target.value })}>
            <option value="">전체</option>
            {AUDIT_ACTIONS.map((action) => (
              <option key={action} value={action}>
                {ACTION_LABELS[action]}
              </option>
            ))}
          </select>
        </label>
        <button type="submit">조회</button>
        <button type="button" onClick={clear} disabled={isEmptyFilters(draft) && !filtered}>
          필터 지우기
        </button>
      </form>
      {usersFailed ? (
        <p className="muted" role="status">
          사용자 목록을 읽지 못해 행위자를 고를 수 없습니다. 다른 조건으로는 조회할 수 있습니다.
        </p>
      ) : null}
      {formError ? (
        <p role="alert" className="state state-error" data-testid="audit-form-error">
          {formError}
        </p>
      ) : null}
      {hasDraftChange && !formError && !loading ? (
        <p className="muted" data-testid="audit-draft-hint">
          조건을 바꿨습니다. &quot;조회&quot;를 눌러 목록에 반영하세요.
        </p>
      ) : null}

      {loading ? <Loading label="감사 기록을 불러오는 중" /> : null}
      {error !== undefined ? (
        <ErrorNotice error={error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 시도
          </button>
        </ErrorNotice>
      ) : null}

      {page ? (
        <>
          {items.length === 0 ? (
            <div data-testid="audit-empty">
              {offset > 0 ? (
                <>
                  <p className="muted">이 쪽에는 기록이 없습니다. 첫 쪽으로 돌아가 주세요.</p>
                  <button type="button" onClick={() => setOffset(0)}>
                    첫 쪽으로
                  </button>
                </>
              ) : filtered ? (
                <>
                  <p className="muted">조건에 맞는 기록이 없습니다.</p>
                  <button type="button" onClick={clear}>
                    필터 지우기
                  </button>
                </>
              ) : (
                <p className="muted">아직 기록이 없습니다.</p>
              )}
            </div>
          ) : (
            <div className="table-scroll">
              <table aria-label="감사 기록" className="list-table audit-table">
                <thead>
                  <tr>
                    <th scope="col">일시</th>
                    <th scope="col">행위자</th>
                    <th scope="col">행위</th>
                    <th scope="col">대상</th>
                    <th scope="col">요약</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item) => (
                    <AuditRow key={item.id} item={item} resolveUser={resolveUser} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {total > PAGE_SIZE || offset > 0 ? (
            <div className="pager">
              <span>
                전체 {total.toLocaleString("en-US")}건 중 {Math.min(offset + 1, total).toLocaleString("en-US")}–{Math.min(offset + PAGE_SIZE, total).toLocaleString("en-US")}
              </span>
              <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
                이전
              </button>
              <button type="button" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
                다음
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function targetName(details: unknown): string {
  if (typeof details !== "object" || details === null || Array.isArray(details)) return "";
  const name = (details as Record<string, unknown>).target_name;
  return typeof name === "string" ? name.replace(/\s+/g, " ").trim().slice(0, 60) : "";
}

function AuditRow({ item, resolveUser }: { item: AuditItem; resolveUser: (id: number) => string | undefined }) {
  const actor = item.actor === null ? SERVER_ACTOR : item.actor.display_name ? item.actor.display_name : `사용자 #${item.actor.id}`;
  const action = isAuditAction(item.action) ? ACTION_LABELS[item.action] : "알 수 없는 행위";
  const kind = isTargetType(item.target_type) ? TARGET_TYPE_LABELS[item.target_type] : "알 수 없는 대상";
  const name = targetName(item.details);
  return (
    <tr>
      <td className="audit-time">{formatSecond(item.occurred_at)}</td>
      <td className="audit-actor">{actor}</td>
      <td className="audit-action">{action}</td>
      <td className="audit-target">
        {kind} #{item.target_id}
        {name ? ` ${name}` : ""}
      </td>
      <td className="audit-summary">{summarize(item.action, item.details, resolveUser)}</td>
    </tr>
  );
}
