import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ErrorNotice, Loading } from "../../../components";
import { describeApiError } from "../../../errors";
import { listAllTeams, listUsers } from "../api";
import { useMe } from "../MeContext";
import {
  LOGIN_ID_MAX,
  ROLE_LABELS,
  TEAM_CODE_PATTERN,
  TEAM_NAME_MAX,
  USER_DISPLAY_NAME_MAX,
  type Team,
  type TeamRole,
  type User,
} from "../types";
import {
  applyChange,
  describeChange,
  memberKey,
  newTeamKey,
  newUserKey,
  orderChanges,
  teamKey,
  userKey,
  type Change,
  type Staged,
} from "./changes";

const PAGE_SIZE = 50;

interface LoadResult {
  key: string;
  teams?: Team[];
  users?: { items: User[]; total: number };
  error?: unknown;
}

interface SaveRow {
  key: string;
  text: string;
  status: "waiting" | "ok" | "error" | "skipped";
  message?: string;
}

type Dialog = null | { phase: "confirm" } | { phase: "saving" | "done"; rows: SaveRow[] };

type Editing = null | { type: "team"; id: number } | { type: "user"; id: number };

/** S6 권한 관리. 관리자만 쓴다(서버 권한이 최종 방어선이며 화면도 직접 접속 때 한 번 더 막는다). */
export function PermissionsPage() {
  const { state } = useMe();
  if (state.status !== "ready") return null;
  if (!state.me.is_admin) {
    return (
      <section data-testid="screen-S6">
        <h1>S6 권한 관리</h1>
        <p role="alert" className="state state-error">
          관리자만 사용할 수 있는 화면입니다.
        </p>
      </section>
    );
  }
  return <PermissionsConsole />;
}

function PermissionsConsole() {
  const [staged, setStaged] = useState<Staged>({});
  const [queryInput, setQueryInput] = useState("");
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [reloadKey, setReloadKey] = useState(0);
  const [result, setResult] = useState<LoadResult | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const requestKey = `${reloadKey}|${q}|${offset}`;
  useEffect(() => {
    let active = true;
    Promise.all([listAllTeams(), listUsers({ q: q || undefined, limit: PAGE_SIZE, offset })])
      .then(([teams, page]) => {
        if (active) setResult({ key: requestKey, teams, users: { items: page.items, total: page.total } });
      })
      .catch((error: unknown) => {
        if (active) setResult({ key: requestKey, error });
      });
    return () => {
      active = false;
    };
  }, [requestKey, q, offset]);

  // 저장하지 않은 변경이 있으면 탭을 닫기 전에 브라우저가 한 번 묻는다.
  const pendingCount = Object.keys(staged).length;
  useEffect(() => {
    if (pendingCount === 0) return undefined;
    const handler = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [pendingCount]);

  const loading = result?.key !== requestKey;
  const teams = result?.teams ?? [];
  const users = result?.users?.items ?? [];
  const total = result?.users?.total ?? 0;

  function stage(key: string, change: Change | null) {
    setStaged((previous) => {
      const next = { ...previous };
      if (change === null) delete next[key];
      else next[key] = change;
      return next;
    });
    setNotice(null);
  }

  async function save() {
    const ordered = orderChanges(staged);
    const rows: SaveRow[] = ordered.map(([key, change]) => ({ key, text: describeChange(change), status: "waiting" }));
    setDialog({ phase: "saving", rows: [...rows] });
    let failed = false;
    for (let index = 0; index < ordered.length; index += 1) {
      const [, change] = ordered[index];
      if (failed) {
        rows[index] = { ...rows[index], status: "skipped" };
        continue;
      }
      try {
        await applyChange(change);
        rows[index] = { ...rows[index], status: "ok" };
      } catch (error) {
        failed = true;
        rows[index] = { ...rows[index], status: "error", message: describeApiError(error) };
      }
      setDialog({ phase: "saving", rows: [...rows] });
    }
    const done = new Set(rows.filter((row) => row.status === "ok").map((row) => row.key));
    setStaged((previous) => Object.fromEntries(Object.entries(previous).filter(([key]) => !done.has(key))));
    setDialog({ phase: "done", rows: [...rows] });
    setNotice(failed ? null : `${rows.length}건을 저장했습니다.`);
    setReloadKey((value) => value + 1);
  }

  const roleOf = (user: User, teamId: number): TeamRole | null =>
    user.memberships.find((m) => m.team_id === teamId)?.role ?? null;

  function onRoleChange(user: User, team: Team, value: "" | TeamRole) {
    const original = roleOf(user, team.id);
    const key = memberKey(team.id, user.id);
    const base = { teamId: team.id, teamLabel: team.name, userId: user.id, userLabel: user.display_name };
    if ((value || null) === original) stage(key, null);
    else if (value === "") stage(key, { kind: "member_remove", ...base, from: original as TeamRole });
    else stage(key, { kind: "member_set", ...base, role: value, from: original });
  }

  const editingTeam = editing?.type === "team" ? teams.find((t) => t.id === editing.id) : undefined;
  const editingUser = editing?.type === "user" ? users.find((u) => u.id === editing.id) : undefined;
  const orderedStaged = orderChanges(staged);

  return (
    <section data-testid="screen-S6" className="console">
      <h1>S6 권한 관리</h1>
      <p className="muted">
        팀과 사용자를 고치면 아래 변경 목록에 모이고, 저장 전에 한 번에 확인합니다. 확인하기 전에는 아무것도 바뀌지 않습니다.
      </p>
      {notice ? (
        <p role="status" className="state state-ok">
          {notice}
        </p>
      ) : null}

      <div className="console-forms">
        <TeamCreateForm teams={teams} staged={staged} onStage={stage} />
        <UserCreateForm staged={staged} onStage={stage} />
      </div>

      <form
        className="toolbar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          setOffset(0);
          setQ(queryInput.trim());
        }}
      >
        <label>
          사용자 검색
          <input value={queryInput} onChange={(event) => setQueryInput(event.target.value)} placeholder="로그인 ID 또는 이름" />
        </label>
        <button type="submit">검색</button>
      </form>

      {loading ? <Loading label="팀과 사용자를 불러오는 중" /> : null}
      {!loading && result?.error ? (
        <ErrorNotice error={result.error}>
          <button type="button" onClick={() => setReloadKey((value) => value + 1)}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}

      {!loading && !result?.error ? (
        <>
          {users.length === 0 ? (
            <p className="muted" data-testid="no-users">
              {q ? "검색 결과가 없습니다." : "등록된 사용자가 없습니다. 위에서 사용자를 사전 등록해 주세요."}
            </p>
          ) : null}
          {teams.length === 0 ? (
            <p className="muted" data-testid="no-teams-admin">
              만들어진 팀이 없습니다. 위에서 팀을 만들어 주세요.
            </p>
          ) : null}
          {users.length > 0 ? (
            <p className="muted" data-testid="inactive-guide">
              비활성 팀이나 사용자에게는 소속을 지정할 수 없습니다(이미 있는 소속은 해제만 가능). 필요하면 먼저 다시 사용 상태로 바꿔 주세요.
            </p>
          ) : null}
          {users.length > 0 ? (
            <div className="grid-scroll">
              <table className="matrix" aria-label="팀과 사용자 권한">
                <thead>
                  <tr>
                    <th scope="col">사용자</th>
                    {teams.map((team) => (
                      <th key={team.id} scope="col" className={team.is_active ? "" : "inactive"}>
                        <div>{team.name}</div>
                        <div className="muted">
                          {team.code}
                          {team.is_active ? "" : " · 비활성"}
                        </div>
                        <button type="button" className="link" onClick={() => setEditing({ type: "team", id: team.id })}>
                          {team.name} 수정
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id} className={user.is_active ? "" : "inactive"}>
                      <th scope="row">
                        <div>
                          {user.display_name}
                          {user.is_admin ? <span className="badge">관리자</span> : null}
                          {user.is_active ? null : <span className="badge badge-off">비활성</span>}
                        </div>
                        <div className="muted">{user.login_id}</div>
                        <button type="button" className="link" onClick={() => setEditing({ type: "user", id: user.id })}>
                          {user.display_name} 수정
                        </button>
                      </th>
                      {teams.map((team) => {
                        const change = staged[memberKey(team.id, user.id)];
                        const value: "" | TeamRole =
                          change?.kind === "member_set" ? change.role : change?.kind === "member_remove" ? "" : (roleOf(user, team.id) ?? "");
                        // 비활성 팀·사용자 칸: 소속 추가·역할 변경 컨트롤은 막는다(서버는 409 TARGET_INACTIVE, 최종 방어선).
                        // 이미 있는 소속의 해제(A9)는 서버가 허용하므로 "소속 없음" 선택만 남긴다.
                        const blocked = !team.is_active || !user.is_active;
                        const original = roleOf(user, team.id);
                        const noOption = (role: TeamRole) => blocked && value !== role;
                        return (
                          <td key={team.id} className={change ? "changed" : ""}>
                            <select
                              aria-label={`${user.display_name} - ${team.name} 역할`}
                              value={value}
                              disabled={blocked && original === null && change === undefined}
                              onChange={(event) => onRoleChange(user, team, event.target.value as "" | TeamRole)}
                            >
                              <option value="">소속 없음</option>
                              <option value="definer" disabled={noOption("definer")}>
                                {ROLE_LABELS.definer}
                              </option>
                              <option value="entry" disabled={noOption("entry")}>
                                {ROLE_LABELS.entry}
                              </option>
                            </select>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
          {total > 0 ? (
            <div className="pager">
              <span>
                전체 {total}명 중 {offset + 1}–{Math.min(offset + PAGE_SIZE, total)}
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

      {editingTeam ? (
        <TeamEditPanel
          key={editingTeam.id}
          team={editingTeam}
          staged={staged[teamKey(editingTeam.id)]}
          onClose={() => setEditing(null)}
          onStage={stage}
        />
      ) : null}
      {editingUser ? (
        <UserEditPanel
          key={editingUser.id}
          user={editingUser}
          staged={staged[userKey(editingUser.id)]}
          onClose={() => setEditing(null)}
          onStage={stage}
        />
      ) : null}

      <section aria-label="변경 목록" className="pending">
        <h2>변경 목록 ({pendingCount}건)</h2>
        {pendingCount === 0 ? (
          <p className="muted">아직 바꾼 내용이 없습니다.</p>
        ) : (
          <ul>
            {orderedStaged.map(([key, change]) => (
              <li key={key}>
                {describeChange(change)}{" "}
                <button type="button" className="link" onClick={() => stage(key, null)} aria-label={`빼기: ${describeChange(change)}`}>
                  빼기
                </button>
              </li>
            ))}
          </ul>
        )}
        <div className="actions">
          <button type="button" disabled={pendingCount === 0} onClick={() => setDialog({ phase: "confirm" })}>
            저장하기
          </button>
          <button type="button" disabled={pendingCount === 0} onClick={() => setStaged({})}>
            모두 취소
          </button>
        </div>
      </section>

      {dialog ? (
        <SummaryDialog
          dialog={dialog}
          confirmRows={orderedStaged.map(([key, change]) => ({ key, text: describeChange(change) }))}
          onConfirm={() => void save()}
          onClose={() => setDialog(null)}
        />
      ) : null}
    </section>
  );
}

function SummaryDialog({
  dialog,
  confirmRows,
  onConfirm,
  onClose,
}: {
  dialog: NonNullable<Dialog>;
  confirmRows: Array<{ key: string; text: string }>;
  onConfirm: () => void;
  onClose: () => void;
}) {
  const titleId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const busy = dialog.phase === "saving";

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  useEffect(() => {
    if (busy) return undefined;
    const handler = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [busy, onClose]);

  const title = dialog.phase === "confirm" ? "다음 변경을 저장할까요?" : dialog.phase === "saving" ? "저장하는 중" : "저장 결과";
  return (
    <div className="modal-backdrop">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal">
        <h2 id={titleId} ref={headingRef} tabIndex={-1}>
          {title}
        </h2>
        {dialog.phase === "confirm" ? (
          <>
            <ol>
              {confirmRows.map((row) => (
                <li key={row.key}>{row.text}</li>
              ))}
            </ol>
            <p className="muted">
              {confirmRows.length}건을 위 순서대로 저장합니다. 중간에 실패하면 거기서 멈추고, 이미 저장된 변경은 그대로 남습니다.
            </p>
            <div className="actions">
              <button type="button" onClick={onConfirm}>
                확인하고 저장
              </button>
              <button type="button" onClick={onClose}>
                돌아가기
              </button>
            </div>
          </>
        ) : (
          <>
            <ol>
              {dialog.rows.map((row) => (
                <li key={row.key} data-status={row.status}>
                  <strong>{{ waiting: "대기", ok: "완료", error: "실패", skipped: "실행 안 함" }[row.status]}</strong> {row.text}
                  {row.message ? (
                    <div role="alert" className="state-error-inline">
                      {row.message}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
            {dialog.phase === "done" && dialog.rows.some((row) => row.status !== "ok") ? (
              <p className="muted">실패하거나 실행하지 않은 변경은 변경 목록에 그대로 남아 있습니다. 고친 뒤 다시 저장해 주세요.</p>
            ) : null}
            <div className="actions">
              <button type="button" disabled={busy} onClick={onClose}>
                닫기
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function TeamCreateForm({ teams, staged, onStage }: { teams: Team[]; staged: Staged; onStage: (key: string, change: Change | null) => void }) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!TEAM_CODE_PATTERN.test(code)) {
      setError("팀 코드는 영문 소문자, 숫자, 밑줄(_)만 1~32자로 입력해 주세요.");
      return;
    }
    if (trimmed === "" || trimmed.length > TEAM_NAME_MAX) {
      setError(`팀 이름은 1~${TEAM_NAME_MAX}자로 입력해 주세요.`);
      return;
    }
    if (teams.some((team) => team.code === code) || staged[newTeamKey(code)]) {
      setError("같은 코드의 팀이 이미 있거나 변경 목록에 있습니다.");
      return;
    }
    onStage(newTeamKey(code), { kind: "team_create", code, name: trimmed });
    setCode("");
    setName("");
    setError(null);
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="팀 만들기" noValidate>
      <h2>팀 만들기</h2>
      <label>
        팀 코드
        <input value={code} maxLength={32} onChange={(event) => setCode(event.target.value)} placeholder="예: sales_1" />
      </label>
      <label>
        팀 이름
        <input value={name} maxLength={TEAM_NAME_MAX} onChange={(event) => setName(event.target.value)} />
      </label>
      <p className="muted">코드는 만든 뒤 바꿀 수 없습니다(영문 소문자·숫자·밑줄).</p>
      {error ? (
        <p role="alert" className="state-error-inline">
          {error}
        </p>
      ) : null}
      <button type="submit">변경 목록에 담기</button>
    </form>
  );
}

function UserCreateForm({ staged, onStage }: { staged: Staged; onStage: (key: string, change: Change | null) => void }) {
  const [loginId, setLoginId] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [isAdmin, setIsAdmin] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const login = loginId.trim();
    const display = displayName.trim();
    if (login === "" || display === "") {
      setError("로그인 ID와 표시 이름을 입력해 주세요.");
      return;
    }
    if (login.length > LOGIN_ID_MAX) {
      setError(`로그인 ID는 ${LOGIN_ID_MAX}자 이하로 입력해 주세요.`);
      return;
    }
    if (display.length > USER_DISPLAY_NAME_MAX) {
      setError(`표시 이름은 ${USER_DISPLAY_NAME_MAX}자 이하로 입력해 주세요.`);
      return;
    }
    if (staged[newUserKey(login)]) {
      setError("같은 로그인 ID가 이미 변경 목록에 있습니다.");
      return;
    }
    onStage(newUserKey(login), { kind: "user_create", login_id: login, display_name: display, is_admin: isAdmin });
    setLoginId("");
    setDisplayName("");
    setIsAdmin(false);
    setError(null);
  }

  return (
    <form className="panel" onSubmit={submit} aria-label="사용자 사전 등록" noValidate>
      <h2>사용자 사전 등록</h2>
      <label>
        로그인 ID
        <input value={loginId} maxLength={LOGIN_ID_MAX} onChange={(event) => setLoginId(event.target.value)} />
      </label>
      <label>
        표시 이름
        <input value={displayName} maxLength={USER_DISPLAY_NAME_MAX} onChange={(event) => setDisplayName(event.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={isAdmin} onChange={(event) => setIsAdmin(event.target.checked)} />
        관리자로 등록
      </label>
      {error ? (
        <p role="alert" className="state-error-inline">
          {error}
        </p>
      ) : null}
      <button type="submit">변경 목록에 담기</button>
    </form>
  );
}

function TeamEditPanel({
  team,
  staged,
  onClose,
  onStage,
}: {
  team: Team;
  staged: Change | undefined;
  onClose: () => void;
  onStage: (key: string, change: Change | null) => void;
}) {
  const pending = staged?.kind === "team_update" ? staged : undefined;
  const [name, setName] = useState(pending?.name ?? team.name);
  const [active, setActive] = useState(pending?.is_active ?? team.is_active);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "" || trimmed.length > TEAM_NAME_MAX) {
      setError(`팀 이름은 1~${TEAM_NAME_MAX}자로 입력해 주세요.`);
      return;
    }
    const change: Change = { kind: "team_update", teamId: team.id, label: team.name };
    if (trimmed !== team.name) change.name = trimmed;
    if (active !== team.is_active) change.is_active = active;
    onStage(teamKey(team.id), change.name === undefined && change.is_active === undefined ? null : change);
    onClose();
  }

  return (
    <form className="panel" onSubmit={submit} aria-label={`팀 수정: ${team.name}`} noValidate>
      <h2>팀 수정: {team.name}</h2>
      <p className="muted">코드 {team.code}는 바꿀 수 없습니다.</p>
      <label>
        팀 이름
        <input value={name} maxLength={TEAM_NAME_MAX} onChange={(event) => setName(event.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        사용 중
      </label>
      {error ? (
        <p role="alert" className="state-error-inline">
          {error}
        </p>
      ) : null}
      <button type="submit">변경 목록에 담기</button>
      <button type="button" onClick={onClose}>
        닫기
      </button>
    </form>
  );
}

function UserEditPanel({
  user,
  staged,
  onClose,
  onStage,
}: {
  user: User;
  staged: Change | undefined;
  onClose: () => void;
  onStage: (key: string, change: Change | null) => void;
}) {
  const pending = staged?.kind === "user_update" ? staged : undefined;
  const [displayName, setDisplayName] = useState(pending?.display_name ?? user.display_name);
  const [isAdmin, setIsAdmin] = useState(pending?.is_admin ?? user.is_admin);
  const [active, setActive] = useState(pending?.is_active ?? user.is_active);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = displayName.trim();
    if (trimmed === "") {
      setError("표시 이름을 입력해 주세요.");
      return;
    }
    if (trimmed.length > USER_DISPLAY_NAME_MAX) {
      setError(`표시 이름은 ${USER_DISPLAY_NAME_MAX}자 이하로 입력해 주세요.`);
      return;
    }
    const change: Change = { kind: "user_update", userId: user.id, label: user.display_name };
    if (trimmed !== user.display_name) change.display_name = trimmed;
    if (isAdmin !== user.is_admin) change.is_admin = isAdmin;
    if (active !== user.is_active) change.is_active = active;
    const empty = change.display_name === undefined && change.is_admin === undefined && change.is_active === undefined;
    onStage(userKey(user.id), empty ? null : change);
    onClose();
  }

  return (
    <form className="panel" onSubmit={submit} aria-label={`사용자 수정: ${user.display_name}`} noValidate>
      <h2>사용자 수정: {user.display_name}</h2>
      <p className="muted">로그인 ID {user.login_id}는 바꿀 수 없습니다.</p>
      <label>
        표시 이름
        <input value={displayName} maxLength={USER_DISPLAY_NAME_MAX} onChange={(event) => setDisplayName(event.target.value)} />
      </label>
      <label className="inline">
        <input type="checkbox" checked={isAdmin} onChange={(event) => setIsAdmin(event.target.checked)} />
        관리자
      </label>
      <label className="inline">
        <input type="checkbox" checked={active} onChange={(event) => setActive(event.target.checked)} />
        사용 중
      </label>
      {error ? (
        <p role="alert" className="state-error-inline">
          {error}
        </p>
      ) : null}
      <button type="submit">변경 목록에 담기</button>
      <button type="button" onClick={onClose}>
        닫기
      </button>
    </form>
  );
}
