import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ErrorNotice, Loading } from "../../components";
import { useMe } from "../access/MeContext";
import { createDashboard, listDashboards, updateDashboard } from "./api";
import type { Dashboard, DashboardList } from "./types";
import { UUID_FORMAT_HELP, isCanonicalUuid, normalizeEmbeddedUuid } from "./uuid";

interface Loaded {
  key: number;
  list?: DashboardList;
  error?: unknown;
}

const MAX_NAME = 100;
// 제어문자(0x00-0x1F, 0x7F)는 이름에 쓸 수 없다(E4).
// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/;

/** 이름 검증(E4와 같은 규칙: 공백만 금지, 100자 이하, 제어문자 금지). 문제가 없으면 빈 문자열. */
export function nameProblem(name: string): string {
  const trimmed = name.trim();
  if (trimmed === "") return "이름을 입력해 주세요.";
  if (trimmed.length > MAX_NAME) return `이름은 ${MAX_NAME}자 이하여야 합니다.`;
  if (CONTROL.test(trimmed)) return "이름에 쓸 수 없는 문자가 있습니다.";
  return "";
}

/**
 * S8 대시보드 연결 관리(관리자). 포털에 보여 줄 대시보드를 등록·해제한다.
 * Superset에서 임베드를 켜고 받은 번호(embedded uuid)를 이름과 함께 등록한다. 서버 권한(E4·E5 관리자)이 최종 방어선이다.
 */
export function DashboardAdminPage() {
  const { state } = useMe();
  const isAdmin = state.status === "ready" && state.me.is_admin;
  const [reloadKey, setReloadKey] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [name, setName] = useState("");
  const [uuidText, setUuidText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<unknown>(undefined);
  const [done, setDone] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: number; name: string } | null>(null);
  const [rowError, setRowError] = useState<unknown>(undefined);
  const [busyId, setBusyId] = useState<number | null>(null);

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    listDashboards({ includeInactive: true }, controller.signal)
      .then((list) => !controller.signal.aborted && setLoaded({ key: reloadKey, list }))
      .catch((error: unknown) => !controller.signal.aborted && setLoaded({ key: reloadKey, error }));
    return () => controller.abort();
  }, [reloadKey, isAdmin]);

  const reload = useCallback(() => setReloadKey((value) => value + 1), []);

  if (state.status !== "ready") return null;
  if (!state.me.is_admin) {
    return (
      <section data-testid="screen-S8">
        <h1>S8 대시보드 연결 관리</h1>
        <p role="alert" className="state state-error">
          관리자만 사용할 수 있는 화면입니다.
        </p>
      </section>
    );
  }

  const normalized = normalizeEmbeddedUuid(uuidText);
  const uuidWrong = uuidText.trim() !== "" && !isCanonicalUuid(normalized);
  const nameWrong = name !== "" ? nameProblem(name) : "";
  const canSubmit = !submitting && nameProblem(name) === "" && isCanonicalUuid(normalized);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!canSubmit) return;
    setSubmitting(true);
    setFormError(undefined);
    setDone(null);
    try {
      const created = await createDashboard({ name: name.trim(), embedded_uuid: normalized });
      setDone(`'${created.name}' 대시보드를 연결했습니다.`);
      setName("");
      setUuidText("");
      reload();
    } catch (error) {
      setFormError(error);
    } finally {
      setSubmitting(false);
    }
  };

  const change = async (item: Dashboard, body: { name?: string; is_active?: boolean }) => {
    setBusyId(item.id);
    setRowError(undefined);
    try {
      await updateDashboard(item.id, body);
      setEditing(null);
      reload();
    } catch (error) {
      setRowError(error);
    } finally {
      setBusyId(null);
    }
  };

  const loading = loaded?.key !== reloadKey;
  const items = loaded?.list?.items ?? [];

  return (
    <section data-testid="screen-S8" className="console">
      <h1>S8 대시보드 연결 관리</h1>
      <div className="panel admin-help" data-testid="admin-help">
        <h2>연결하는 방법</h2>
        <ol>
          <li>Superset에서 대시보드를 열고 임베드를 켭니다(대시보드 메뉴의 &quot;임베드 대시보드&quot;). 이때 허용 도메인에 이 포털의 주소 <code>{window.location.origin}</code> 를 입력합니다.</li>
          <li>임베드를 켜면 나오는 번호(36자)를 복사해 아래에 이름과 함께 등록합니다.</li>
          <li>등록하면 모든 사용자가 S7 대시보드 화면에서 볼 수 있습니다. 해제하면 더 이상 열리지 않지만, Superset의 임베드는 관리자가 따로 꺼야 합니다.</li>
        </ol>
        <p className="muted" data-testid="admin-warning">
          운영 주의: Superset에 다른 DB 연결을 추가하지 마세요.
        </p>
      </div>

      <form className="panel panel-form" onSubmit={(event) => void submit(event)} aria-label="대시보드 연결 등록">
        <h2>새 대시보드 연결</h2>
        <label>
          이름 (사용자에게 보이는 이름)
          <input value={name} maxLength={200} onChange={(event) => setName(event.target.value)} aria-invalid={nameWrong !== ""} />
        </label>
        {nameWrong ? (
          <p className="state-error-inline" role="alert">
            {nameWrong}
          </p>
        ) : null}
        <label>
          임베드 번호 (Superset에서 받은 번호)
          <input value={uuidText} onChange={(event) => setUuidText(event.target.value)} aria-invalid={uuidWrong} spellCheck={false} autoComplete="off" />
        </label>
        {uuidWrong ? (
          <p className="state-error-inline" role="alert" data-testid="uuid-format-error">
            {UUID_FORMAT_HELP}
          </p>
        ) : uuidText.trim() !== "" && uuidText.trim() !== normalized ? (
          <p className="muted" data-testid="uuid-normalized">
            대문자는 소문자로 바꿔서 등록합니다: {normalized}
          </p>
        ) : null}
        {formError !== undefined ? <ErrorNotice error={formError} /> : null}
        {done ? (
          <p role="status" className="state state-ok" data-testid="register-done">
            {done}
          </p>
        ) : null}
        <div className="actions">
          <button type="submit" className="primary" disabled={!canSubmit}>
            {submitting ? "등록하는 중…" : "연결 등록"}
          </button>
        </div>
      </form>

      <h2>연결된 대시보드</h2>
      {loading ? <Loading label="대시보드 목록을 불러오는 중" /> : null}
      {!loading && loaded?.error !== undefined ? (
        <ErrorNotice error={loaded.error}>
          <button type="button" onClick={reload}>
            다시 불러오기
          </button>
        </ErrorNotice>
      ) : null}
      {rowError !== undefined ? <ErrorNotice error={rowError} /> : null}
      {!loading && loaded?.list ? (
        items.length === 0 ? (
          <p className="muted" data-testid="no-dashboards">
            연결된 대시보드가 없습니다. 위에서 등록해 주세요.
          </p>
        ) : (
          <table aria-label="대시보드 연결 목록" className="list-table">
            <thead>
              <tr>
                <th scope="col">이름</th>
                <th scope="col">임베드 번호</th>
                <th scope="col">상태</th>
                <th scope="col">
                  <span className="visually-hidden">동작</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <tr key={item.id} className={item.is_active ? undefined : "inactive"}>
                  <td>
                    {editing?.id === item.id ? (
                      <span className="inline-edit">
                        <input
                          aria-label="새 이름"
                          value={editing.name}
                          maxLength={200}
                          onChange={(event) => setEditing({ id: item.id, name: event.target.value })}
                        />
                        <button
                          type="button"
                          disabled={busyId === item.id || nameProblem(editing.name) !== "" || editing.name.trim() === item.name}
                          onClick={() => void change(item, { name: editing.name.trim() })}
                        >
                          저장
                        </button>
                        <button type="button" onClick={() => setEditing(null)}>
                          취소
                        </button>
                        {nameProblem(editing.name) ? <span className="state-error-inline">{nameProblem(editing.name)}</span> : null}
                      </span>
                    ) : (
                      item.name
                    )}
                  </td>
                  <td>
                    <code>{item.embedded_uuid}</code>
                  </td>
                  <td>{item.is_active ? <span className="badge">연결됨</span> : <span className="badge badge-off">해제됨</span>}</td>
                  <td>
                    <button type="button" disabled={busyId === item.id || editing?.id === item.id} onClick={() => setEditing({ id: item.id, name: item.name })}>
                      이름 변경
                    </button>{" "}
                    <button type="button" disabled={busyId === item.id} onClick={() => void change(item, { is_active: !item.is_active })}>
                      {item.is_active ? "연결 해제" : "다시 연결"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : null}
    </section>
  );
}
