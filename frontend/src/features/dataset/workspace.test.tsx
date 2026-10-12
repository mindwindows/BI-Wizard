import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { createTestRouter } from "../../routes";
import { ADMIN_ME, HEALTH_HANDLERS, apiError, installFetch, json, type RecordedCall } from "../../test-utils";
import { COL, makeDetail, makeFakeWorkspace, type FakeWorkspace } from "./test-server";
import type { DatasetDetail } from "./types";

const BASE = "/bi-wizard";

beforeEach(() => {
  window.__APP_CONFIG__ = { basePath: BASE, supersetRoot: `${BASE}/superset` };
  window.sessionStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete window.__APP_CONFIG__;
});

async function openWorkspace(detail: DatasetDetail = makeDetail()): Promise<{ fake: FakeWorkspace; calls: RecordedCall[] }> {
  const fake = makeFakeWorkspace(detail);
  const { calls } = installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), ...fake.handlers });
  render(<App router={createTestRouter(BASE, `${BASE}/datasets/${detail.id}`)} />);
  await screen.findByRole("region", { name: "데이터셋 정보" });
  return { fake, calls };
}

const writes = (calls: RecordedCall[]) => calls.filter((c) => c.method !== "GET");
const inspector = () => screen.getByRole("complementary", { name: "Inspector" });
const addForm = () => within(inspector()).getByRole("form", { name: "열 추가" });
const startAdd = () => fireEvent.click(screen.getByRole("button", { name: "열 추가" }));
const type = (form: HTMLElement, label: string, value: string) =>
  fireEvent.change(within(form).getByLabelText(label), { target: { value } });

const SALES = [
  COL(1, "기준일", "date", { required: true }),
  COL(2, "매출", "number", { rules: { min: 0, max: "9.5", decimals: 1 }, tag: "수입" }),
  COL(3, "메모", "text", { rules: { max_length: 50 } }),
  COL(4, "등급", "choice", { rules: { options: ["상", "중", "하"] } }),
  COL(5, "합계", "number", { kind: "formula" }),
];

describe("S4 작업공간 골격", () => {
  it("좌(데이터셋 정보·열 목록) 중앙(열 헤더 미리보기) 우(Inspector) 3분할", async () => {
    await openWorkspace(makeDetail({ columns: SALES, base_date_column_id: 1 }));
    expect(screen.getByRole("heading", { level: 1, name: /월별 매출/ })).toBeTruthy();
    const info = screen.getByRole("region", { name: "데이터셋 정보" });
    expect(info.textContent).toContain("영업");
    expect(info.textContent).toContain("월");
    expect(info.textContent).toContain("관리자 김");
    expect(info.textContent).toContain("2026-10-12");
    expect(info.textContent).toContain("기준일"); // 기준 날짜 열
    const list = within(screen.getByRole("region", { name: "열 목록" })).getAllByRole("button").map((b) => b.textContent);
    expect(list.slice(0, 5).map((t) => t?.split(" ")[0])).toEqual(["기준일", "매출", "메모", "등급", "합계"]);
    const preview = screen.getByRole("table", { name: "열 헤더 미리보기" });
    expect(within(preview).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("기준일"), expect.stringContaining("매출"), expect.stringContaining("합계")]),
    );
    expect(inspector()).toBeTruthy();
    // 지금 단계에서 안내 문구 없이 빈 영역이다.
    expect(screen.queryByText(/다음 단계/)).toBeNull();
  });

  it("열이 없으면 열 추가 안내", async () => {
    await openWorkspace();
    expect(screen.getByTestId("no-columns")).toBeTruthy();
  });

  it("열은 position 순으로 보인다", async () => {
    await openWorkspace(makeDetail({ columns: [COL(1, "나중", "text", { position: 9 }), COL(2, "먼저", "text", { position: 1 })] }));
    const names = within(screen.getByRole("table", { name: "열 헤더 미리보기" })).getAllByRole("columnheader").map((h) => h.textContent);
    expect(names[0]).toContain("먼저");
    expect(names[1]).toContain("나중");
  });

  it("없는 데이터셋(404)은 쉬운 문구, 화면 식별자는 유지", async () => {
    installFetch({ ...HEALTH_HANDLERS, "GET /me": () => json(200, ADMIN_ME), "GET /datasets/9": () => apiError(404, "NOT_FOUND") });
    render(<App router={createTestRouter(BASE, `${BASE}/datasets/9`)} />);
    expect((await screen.findByRole("alert")).textContent).toContain("찾을 수 없습니다");
    expect(screen.getByTestId("screen-S4")).toBeTruthy();
  });

  it("Inspector는 접고 펼 수 있고 폭을 조절할 수 있다", async () => {
    await openWorkspace();
    const aside = inspector();
    const slider = within(aside).getByLabelText("Inspector 폭") as HTMLInputElement;
    fireEvent.change(slider, { target: { value: "500" } });
    expect(aside.style.width).toBe("500px");
    fireEvent.click(within(aside).getByRole("button", { name: "Inspector 접기" }));
    expect(within(aside).queryByLabelText("Inspector 폭")).toBeNull();
    fireEvent.click(within(aside).getByRole("button", { name: "Inspector 펼치기" }));
    expect(within(aside).getByLabelText("Inspector 폭")).toBeTruthy();
  });
});

describe("Inspector 열 추가 (B5)", () => {
  it("숫자 열: 본문에 expected_version·이름·타입·필수·rules(십진 문자열)·태그·위치를 싣는다", async () => {
    const { calls } = await openWorkspace(makeDetail({ columns: [COL(1, "기준일", "date")] }));
    startAdd();
    const form = addForm();
    type(form, "열 이름", "  매출액 ");
    type(form, "타입", "number");
    fireEvent.click(within(form).getByLabelText("필수 입력"));
    type(form, "최솟값", "0");
    type(form, "최댓값", "100.50");
    type(form, "소수 자릿수", "2");
    type(form, "구분 태그", "수입");
    type(form, "위치", "2");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await screen.findByRole("status");
    const post = writes(calls)[0];
    expect(`${post.method} ${post.path}`).toBe("POST /datasets/7/columns");
    expect(post.body).toEqual({
      expected_version: 3,
      display_name: "매출액",
      type: "number",
      required: true,
      rules: { min: "0", max: "100.50", decimals: 2 },
      tag: "수입",
      position: 2,
    });
    // 새 열이 목록에 나타나고 선택되어 수정 폼으로 바뀐다.
    expect(await within(screen.getByRole("region", { name: "열 목록" })).findByRole("button", { name: /매출액/ })).toBeTruthy();
    expect(within(inspector()).getByRole("form", { name: "열 수정: 매출액" })).toBeTruthy();
  });

  it("필수 입력이 아니면 required=false, 비운 규칙·태그·위치는 키를 보내지 않는다", async () => {
    const { calls } = await openWorkspace();
    startAdd();
    const form = addForm();
    type(form, "열 이름", "메모");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, display_name: "메모", type: "text", required: false });
  });

  it("두 번 연속 추가하면 두 번째는 새 def_version(4)을 expected_version으로 보낸다", async () => {
    const { calls } = await openWorkspace();
    startAdd();
    type(addForm(), "열 이름", "가");
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    await screen.findByRole("status");
    startAdd();
    type(addForm(), "열 이름", "나");
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    expect((writes(calls)[0].body as { expected_version: number }).expected_version).toBe(3);
    expect((writes(calls)[1].body as { expected_version: number }).expected_version).toBe(4);
  });

  it("타입에 따라 규칙 칸이 바뀐다(태그는 숫자 열만)", async () => {
    await openWorkspace();
    startAdd();
    const form = addForm();
    const has = (label: string) => within(form).queryByLabelText(label) !== null;
    expect([has("최솟값"), has("최대 글자 수"), has("가장 이른 날짜"), has("선택 목록 (한 줄에 하나)"), has("구분 태그")]).toEqual([false, true, false, false, false]);
    type(form, "타입", "number");
    expect([has("최솟값"), has("최대 글자 수"), has("구분 태그")]).toEqual([true, false, true]);
    type(form, "타입", "date");
    expect([has("가장 이른 날짜"), has("가장 늦은 날짜"), has("최솟값")]).toEqual([true, true, false]);
    type(form, "타입", "choice");
    expect([has("선택 목록 (한 줄에 하나)"), has("구분 태그")]).toEqual([true, false]);
    type(form, "타입", "boolean");
    expect([has("선택 목록 (한 줄에 하나)"), has("최대 글자 수"), has("최솟값"), has("가장 이른 날짜")]).toEqual([false, false, false, false]);
  });

  it("선택 목록·날짜·글자 규칙 본문", async () => {
    const { calls } = await openWorkspace();
    startAdd();
    let form = addForm();
    type(form, "열 이름", "등급");
    type(form, "타입", "choice");
    type(form, "선택 목록 (한 줄에 하나)", "상\n중\n하");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toMatchObject({ type: "choice", rules: { options: ["상", "중", "하"] } });

    startAdd();
    form = addForm();
    type(form, "열 이름", "기한");
    type(form, "타입", "date");
    type(form, "가장 이른 날짜", "2026-01-01");
    type(form, "가장 늦은 날짜", "2026-12-31");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(2));
    expect(writes(calls)[1].body).toMatchObject({ type: "date", rules: { min: "2026-01-01", max: "2026-12-31" } });

    startAdd();
    form = addForm();
    type(form, "열 이름", "비고");
    type(form, "최대 글자 수", "30");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    await waitFor(() => expect(writes(calls)).toHaveLength(3));
    expect(writes(calls)[2].body).toMatchObject({ type: "text", rules: { max_length: 30 } });
  });

  it.each([["[매출]"], ['매"출'], ["a\tb"]])("금지 문자가 든 열 이름 %j는 입력 즉시 안내하고 저장을 막는다", async (name) => {
    const { calls } = await openWorkspace();
    startAdd();
    const form = addForm();
    type(form, "열 이름", name);
    expect(within(form).getByTestId("name-error").textContent).toContain("쓸 수 없습니다");
    const save = within(form).getByRole("button", { name: "열 추가" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);
    fireEvent.submit(form);
    expect(writes(calls)).toEqual([]);
  });

  it("예약어는 입력 즉시 안내하고 저장을 막는다. 안내 문구는 처음부터 보인다", async () => {
    const { calls } = await openWorkspace();
    startAdd();
    const form = addForm();
    expect(within(form).getByTestId("name-hint").textContent).toContain("row_id");
    for (const name of ["team", "팀", "row_id", "행 번호"]) {
      type(form, "열 이름", name);
      expect(within(form).getByTestId("name-error").textContent).toContain("예약어");
      expect((within(form).getByRole("button", { name: "열 추가" }) as HTMLButtonElement).disabled).toBe(true);
    }
    type(form, "열 이름", "팀원 수");
    expect(within(form).queryByTestId("name-error")).toBeNull();
    expect(writes(calls)).toEqual([]);
  });

  it("열 이름 입력은 100자로 제한된다", async () => {
    await openWorkspace();
    startAdd();
    expect((within(addForm()).getByLabelText("열 이름") as HTMLInputElement).maxLength).toBe(100);
  });

  it("규칙 오류(최솟값 > 최댓값)는 호출 없이 칸 옆에 알린다", async () => {
    const { calls } = await openWorkspace();
    startAdd();
    const form = addForm();
    type(form, "열 이름", "x");
    type(form, "타입", "number");
    type(form, "최솟값", "10");
    type(form, "최댓값", "9");
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    expect(within(form).getByText(/최댓값은 최솟값보다 작을 수 없습니다/)).toBeTruthy();
    expect(writes(calls)).toEqual([]);
  });

  it("서버 422(예약어/길이)와 중복 열 이름(409)을 쉬운 문구로 보여 준다", async () => {
    const { fake } = await openWorkspace();
    startAdd();
    const form = addForm();
    type(form, "열 이름", "x");
    fake.failNext(() =>
      apiError(422, "VALIDATION_ERROR", "서버", { fields: [{ field: "display_name", code: "RESERVED", message: "m" }] }),
    );
    fireEvent.click(within(form).getByRole("button", { name: "열 추가" }));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("사용할 수 없는 이름");
    fake.failNext(() => apiError(409, "ALREADY_EXISTS", "서버", { field: "display_name" }));
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    await waitFor(() => expect(within(inspector()).getByRole("alert").textContent).toContain("같은 이름의 열이 이미"));
  });
});

describe("Inspector 열 수정 (B6)", () => {
  const detail = () => makeDetail({ columns: SALES, base_date_column_id: 1 });
  const selectColumn = (name: RegExp) => fireEvent.click(within(screen.getByRole("region", { name: "열 목록" })).getByRole("button", { name }));

  it("타입·종류는 바꿀 수 없다고 표시하고 입력칸이 없다", async () => {
    await openWorkspace(detail());
    selectColumn(/^매출/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 매출" });
    expect(within(form).queryByLabelText("타입")).toBeNull();
    expect(within(form).getByTestId("type-locked").textContent).toContain("숫자");
    expect(within(form).getByTestId("type-locked").textContent).toContain("바꿀 수 없습니다");
    expect(within(form).getByTestId("kind-locked").textContent).toContain("입력 열");
  });

  it("서버 값(숫자로 온 min 포함)을 입력칸에 보여 주고, 바뀐 항목만 expected_version과 함께 보낸다", async () => {
    const { calls } = await openWorkspace(detail());
    selectColumn(/^매출/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 매출" });
    expect((within(form).getByLabelText("최솟값") as HTMLInputElement).value).toBe("0");
    expect((within(form).getByLabelText("최댓값") as HTMLInputElement).value).toBe("9.5");
    expect((within(form).getByLabelText("소수 자릿수") as HTMLInputElement).value).toBe("1");
    expect((within(form).getByLabelText("구분 태그") as HTMLInputElement).value).toBe("수입");
    const save = within(form).getByRole("button", { name: "저장" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // 바뀐 것이 없으면 저장 불가
    type(form, "최댓값", "20");
    fireEvent.click(save);
    await screen.findByRole("status");
    const patch = writes(calls)[0];
    expect(`${patch.method} ${patch.path}`).toBe("PATCH /datasets/7/columns/2");
    expect(patch.body).toEqual({ expected_version: 3, rules: { min: "0", max: "20", decimals: 1 } });
  });

  it("이름·필수·태그·위치 변경은 해당 필드만 보낸다. type·kind는 보내지 않는다", async () => {
    const { calls } = await openWorkspace(detail());
    selectColumn(/^메모/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 메모" });
    type(form, "열 이름", "비고");
    fireEvent.click(within(form).getByLabelText("필수 입력"));
    type(form, "위치", "9");
    fireEvent.click(within(form).getByRole("button", { name: "저장" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, display_name: "비고", required: true, position: 9 });
    expect(writes(calls)[0].body).not.toHaveProperty("type");
    expect(writes(calls)[0].body).not.toHaveProperty("kind");
  });

  it("숫자 열의 태그를 비우면 tag를 null로 보낸다", async () => {
    const { calls } = await openWorkspace(detail());
    selectColumn(/^매출/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 매출" });
    type(form, "구분 태그", "");
    fireEvent.click(within(form).getByRole("button", { name: "저장" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, tag: null });
  });

  it("이름을 예약어/금지 문자로 바꾸면 저장할 수 없다", async () => {
    await openWorkspace(detail());
    selectColumn(/^메모/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 메모" });
    type(form, "열 이름", "team");
    expect(within(form).getByTestId("name-error")).toBeTruthy();
    expect((within(form).getByRole("button", { name: "저장" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("열 머리글을 눌러도 선택된다", async () => {
    await openWorkspace(detail());
    fireEvent.click(within(screen.getByRole("table", { name: "열 헤더 미리보기" })).getByRole("button", { name: /메모/ }));
    expect(within(inspector()).getByRole("form", { name: "열 수정: 메모" })).toBeTruthy();
  });

  it("COLUMN_LOCKED 422와 순환(FORMULA_CIRCULAR) 422는 쉬운 문구", async () => {
    const { fake } = await openWorkspace(detail());
    selectColumn(/^매출/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 매출" });
    type(form, "구분 태그", "다른");
    fake.failNext(() => apiError(422, "COLUMN_LOCKED"));
    fireEvent.click(within(form).getByRole("button", { name: "저장" }));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("바꿀 수 없습니다");
    fake.failNext(() => apiError(422, "FORMULA_CIRCULAR"));
    fireEvent.click(within(inspector()).getByRole("button", { name: "저장" }));
    await waitFor(() => expect(within(inspector()).getByRole("alert").textContent).toContain("순환"));
  });

  it("계산 열(kind=formula)은 여기서 고칠 수 없고 저장 버튼이 없다", async () => {
    await openWorkspace(detail());
    selectColumn(/^합계/);
    const form = within(inspector()).getByRole("form", { name: "열 수정: 합계" });
    expect(within(form).getByTestId("kind-locked").textContent).toContain("계산 열");
    expect(within(form).queryByRole("button", { name: "저장" })).toBeNull();
  });
});

describe("Inspector 데이터셋 설정 (B4)", () => {
  const detail = () => makeDetail({ columns: SALES, base_date_column_id: null });
  const openSettings = () => fireEvent.click(screen.getByRole("button", { name: "데이터셋 설정" }));
  const settings = () => within(inspector()).getByRole("form", { name: "데이터셋 설정" });

  it("기준 날짜 열 선택지는 입력 열 중 날짜 열뿐이고, 지정하면 base_date_column_id를 보낸다", async () => {
    const { calls } = await openWorkspace(detail());
    openSettings();
    const select = within(settings()).getByLabelText("기준 날짜 열") as HTMLSelectElement;
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["없음", "기준일"]);
    type(settings(), "기준 날짜 열", "1");
    fireEvent.click(within(settings()).getByRole("button", { name: "저장" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, base_date_column_id: 1 });
    expect(`${writes(calls)[0].method} ${writes(calls)[0].path}`).toBe("PATCH /datasets/7");
  });

  it("기준 날짜 열을 '없음'으로 되돌리면 null을 보낸다", async () => {
    const { calls } = await openWorkspace(makeDetail({ columns: SALES, base_date_column_id: 1 }));
    openSettings();
    type(settings(), "기준 날짜 열", "");
    fireEvent.click(within(settings()).getByRole("button", { name: "저장" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, base_date_column_id: null });
  });

  it("날짜 단위와 이름 변경은 바뀐 필드만 보낸다", async () => {
    const { calls } = await openWorkspace(detail());
    openSettings();
    type(settings(), "날짜 단위", "year");
    type(settings(), "이름", "연간 매출");
    fireEvent.click(within(settings()).getByRole("button", { name: "저장" }));
    await screen.findByRole("status");
    expect(writes(calls)[0].body).toEqual({ expected_version: 3, name: "연간 매출", date_unit: "year" });
    expect(await screen.findByRole("heading", { level: 1, name: /연간 매출/ })).toBeTruthy();
  });

  it("행이 있어 거부되면(DATASET_HAS_ROWS) 이유와 해결책을 알려 준다", async () => {
    const { fake } = await openWorkspace(detail());
    openSettings();
    type(settings(), "날짜 단위", "day");
    fake.failNext(() => apiError(422, "DATASET_HAS_ROWS", "서버 문구"));
    fireEvent.click(within(settings()).getByRole("button", { name: "저장" }));
    const alert = await within(inspector()).findByRole("alert");
    expect(alert.textContent).toContain("이미 입력된 행");
    expect(alert.textContent).toContain("날짜 단위");
    expect(alert.textContent).not.toContain("서버 문구");
  });
});

describe("정의 버전 충돌과 재시도", () => {
  it("DEFINITION_VERSION_MISMATCH: 다시 읽기 안내 + 최신 상태 재로딩 뒤 새 버전으로 저장된다", async () => {
    const { fake, calls } = await openWorkspace(makeDetail({ columns: [COL(1, "기준일", "date")] }));
    // 다른 사람이 먼저 열을 추가했다.
    fake.state.columns.push(COL(2, "남이 추가", "text"));
    fake.state.def_version = 9;
    startAdd();
    type(addForm(), "열 이름", "내 열");
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    const alert = await within(inspector()).findByRole("alert");
    expect(alert.textContent).toContain("다른 사람이 먼저");
    expect(alert.textContent).toContain("다시 읽");
    // 최신 상태 재로딩: 남이 추가한 열이 목록에 나타난다.
    expect(await within(screen.getByRole("region", { name: "열 목록" })).findByRole("button", { name: /남이 추가/ })).toBeTruthy();
    expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7")).toHaveLength(2);
    // 입력하던 열 이름은 지워지지 않고, 다시 저장하면 최신 버전(9)을 보낸다.
    expect((within(addForm()).getByLabelText("열 이름") as HTMLInputElement).value).toBe("내 열");
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    await screen.findByRole("status");
    const posts = writes(calls);
    expect((posts[0].body as { expected_version: number }).expected_version).toBe(3);
    expect((posts[1].body as { expected_version: number }).expected_version).toBe(9);
  });

  it("DEFINITION_BUSY: 잠시 뒤 다시 시도 안내, 같은 내용을 다시 저장할 수 있다", async () => {
    const { fake, calls } = await openWorkspace();
    startAdd();
    type(addForm(), "열 이름", "가");
    fake.failNext(() => apiError(503, "DEFINITION_BUSY", "서버", { retry_after: 3 }));
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    const alert = await within(inspector()).findByRole("alert");
    expect(alert.textContent).toContain("잠시 뒤");
    expect(calls.filter((c) => c.method === "GET" && c.path === "/datasets/7")).toHaveLength(1); // 재로딩 없음
    const save = within(addForm()).getByRole("button", { name: "열 추가" }) as HTMLButtonElement;
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    await screen.findByRole("status");
    expect(writes(calls)).toHaveLength(2);
    expect(writes(calls)[1].body).toEqual(writes(calls)[0].body);
  });
});

describe("읽기 전용 (정의 권한 없음)", () => {
  const readOnly = () => makeDetail({ columns: SALES, permissions: { define: false, enter: true } });

  it("열 추가 버튼과 저장 버튼이 없고 입력칸은 막혀 있으며 안내가 보인다", async () => {
    const { calls } = await openWorkspace(readOnly());
    expect(screen.queryByRole("button", { name: "열 추가" })).toBeNull();
    expect(within(inspector()).getByTestId("readonly-notice").textContent).toContain("정의 담당자");
    fireEvent.click(within(screen.getByRole("region", { name: "열 목록" })).getByRole("button", { name: /^매출/ }));
    const form = within(inspector()).getByRole("form", { name: "열 수정: 매출" });
    expect(within(form).queryByRole("button", { name: "저장" })).toBeNull();
    for (const label of ["열 이름", "필수 입력", "최솟값", "최댓값", "소수 자릿수", "구분 태그", "위치"]) {
      expect((within(form).getByLabelText(label) as HTMLInputElement).disabled).toBe(true);
    }
    fireEvent.submit(form);
    expect(writes(calls)).toEqual([]);
  });

  it("데이터셋 설정도 읽기 전용이다", async () => {
    const { calls } = await openWorkspace(readOnly());
    fireEvent.click(screen.getByRole("button", { name: "데이터셋 설정" }));
    const form = within(inspector()).getByRole("form", { name: "데이터셋 설정" });
    expect(within(form).queryByRole("button", { name: "저장" })).toBeNull();
    expect((within(form).getByLabelText("날짜 단위") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.submit(form);
    expect(writes(calls)).toEqual([]);
  });

  it("권한 판정은 서버가 준 permissions.define이고, 서버가 403이면 문구로 알린다", async () => {
    // 화면이 허용했는데 서버가 거부하는 경우(권한이 방금 회수됨): 서버 권한이 최종 방어선이다.
    const { fake } = await openWorkspace(makeDetail());
    startAdd();
    type(addForm(), "열 이름", "x");
    fake.failNext(() => apiError(403, "FORBIDDEN"));
    fireEvent.click(within(addForm()).getByRole("button", { name: "열 추가" }));
    expect((await within(inspector()).findByRole("alert")).textContent).toContain("권한이 없습니다");
  });
});
