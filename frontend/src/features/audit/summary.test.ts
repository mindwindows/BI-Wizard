import { describe, expect, it } from "vitest";
import { OMITTED, PARTIAL, summarize } from "./summary";
import { AUDIT_ACTIONS, ACTION_LABELS, type AuditAction } from "./types";

const names = (id: number) => ({ 7: "박입력" })[id as 7];

/** 04 §5-1 표의 허용 키로 만든 대표 details와 기대 요약. 행위 17개 전부. */
const CASES: Array<[AuditAction, Record<string, unknown>, string]> = [
  ["dataset.create", { target_name: "월별 매출", team_id: 3, date_unit: "month", def_version: 1 }, "팀 번호 3, 날짜 단위 월, 정의 버전 1"],
  [
    "dataset.update",
    { target_name: "월별 매출", team_id: 3, changes: { name: { from: "가", to: "나" }, date_unit: { from: "month", to: "day" }, base_date_column_id: { from: null, to: 12 } }, def_version: 4 },
    "이름 '가'→'나', 날짜 단위 월→일, 기준 날짜 열 없음→열 번호 12, 정의 버전 4",
  ],
  ["dataset.archive", { target_name: "월별 매출", team_id: 3 }, "데이터셋 보관"],
  ["dataset.restore", { target_name: "월별 매출", team_id: 3 }, "데이터셋 복구"],
  ["column.add", { target_name: "월별 매출", column_id: 5, column_name: "매출", column_type: "number", required: true, def_version: 2 }, "열 '매출' 추가 (숫자, 필수), 정의 버전 2"],
  [
    "column.update",
    { target_name: "월별 매출", column_id: 5, column_name: "매출액", changes: { display_name: { from: "매출", to: "매출액" }, required: { from: true, to: false }, tag: { from: null, to: "금액" }, position: { from: 2, to: 3 } }, rules_changed: true, def_version: 5 },
    "열 '매출액', 열 이름 '매출'→'매출액', 필수 여부 필수→선택, 구분 태그 없음→'금액', 위치 2→3, 검증 규칙 변경, 정의 버전 5",
  ],
  ["formula_column.add", { target_name: "월별 매출", column_id: 6, column_name: "합계", result_type: "number", ast_hash: "abc123", def_version: 6 }, "계산 열 '합계' 추가 (결과 숫자), 정의 버전 6"],
  [
    "formula_column.update",
    { target_name: "월별 매출", column_id: 6, column_name: "합계", result_type: "text", result_type_changed: true, ast_hash_from: "aaa", ast_hash: "bbb", def_version: 7 },
    "계산 열 '합계' 수식 수정, 결과 타입이 바뀜 (글자), 정의 버전 7",
  ],
  ["team.create", { target_name: "영업", code: "sales" }, "팀 코드 sales"],
  ["team.update", { target_name: "영업", changes: { name: { from: "영업", to: "영업1" }, is_active: { from: true, to: false } } }, "이름 '영업'→'영업1', 사용 상태 사용 중→사용 중지"],
  ["member.set", { target_name: "영업", user_id: 7, role: "definer", role_from: "entry" }, "사용자 '박입력', 역할 입력자→정의 담당자"],
  ["member.remove", { target_name: "영업", user_id: 8, role_from: "definer" }, "사용자 번호 8 소속 해제, 이전 역할 정의 담당자"],
  ["user.create", { target_name: "김관리", is_admin: false }, "관리자 권한 없음으로 등록"],
  ["user.update", { target_name: "김관리", changes: { is_admin: { from: false, to: true }, is_active: { from: true, to: false } }, display_name_changed: true }, "관리자 권한 없음→있음, 사용 상태 사용 중→사용 중지, 표시 이름 변경"],
  ["user.bootstrap_admin", { target_name: "김관리", is_admin: true }, "서버 명령으로 최초 관리자 등록"],
  ["dashboard.create", { target_name: "경영", embedded_uuid: "0f8fad5b-d9cb-469f-a165-70867728950e" }, "임베드 번호 0f8fad5b-d9cb-469f-a165-70867728950e"],
  ["dashboard.update", { target_name: "경영", changes: { is_active: { from: true, to: false } } }, "연결 해제"],
];

describe("summarize", () => {
  it("시험 사례가 행위 17개를 하나도 빠짐없이 덮는다", () => {
    expect(CASES.map(([action]) => action).sort()).toEqual([...AUDIT_ACTIONS].sort());
    for (const action of AUDIT_ACTIONS) expect(ACTION_LABELS[action]).toBeTruthy();
  });

  it.each(CASES)("%s 요약", (action, details, expected) => {
    expect(summarize(action, details, names)).toBe(expected);
  });

  it("보관·복구는 허용 키(target_name·team_id) 밖의 값을 이름도 값도 출력하지 않는다", () => {
    expect(summarize("dataset.archive", { target_name: "비밀 이름", team_id: 3, rows: ["행값 9"], def_version: 4 })).toBe(`데이터셋 보관 ${PARTIAL}`);
    expect(summarize("dataset.restore", { target_name: "비밀 이름", team_id: "x" })).toBe("데이터셋 복구");
    expect(summarize("dataset.restore", { target_name: "비밀 이름", team_id: 3, formula: "=A+B" })).not.toContain("=A+B");
  });

  it("대시보드 다시 연결과 이름 변경", () => {
    expect(summarize("dashboard.update", { changes: { is_active: { from: false, to: true } } })).toBe("다시 연결");
    expect(summarize("dashboard.update", { changes: { name: { from: "a", to: "b" }, is_active: { from: true, to: false } } })).toBe("이름 'a'→'b', 연결 해제");
  });

  it("새 소속은 '새 소속'으로, 사용자 이름을 모르면 번호로 적는다", () => {
    expect(summarize("member.set", { user_id: 9, role: "entry", role_from: null })).toBe("사용자 번호 9, 새 소속, 역할 입력자");
  });

  it("허용 키 밖의 키는 이름도 값도 출력하지 않고 '일부 상세 생략'만 덧붙인다", () => {
    const leaked = ["비밀 행 값 12345", "=A+B*SECRET", "eyJhbGciOiJIUzI1NiJ9.token", "extra_key_name"];
    const out = summarize("team.create", { code: "sales", row_values: { c_1: leaked[0] }, formula: leaked[1], token: leaked[2], [leaked[3]]: 1 });
    expect(out).toBe(`팀 코드 sales ${PARTIAL}`);
    for (const text of leaked) expect(out).not.toContain(text);
  });

  it("changes 안의 허용 필드 밖 항목도 이름·값을 출력하지 않는다", () => {
    const out = summarize("dataset.update", { changes: { name: { from: "가", to: "나" }, c_17: { from: "행값-1", to: "행값-2" } } });
    expect(out).toBe(`이름 '가'→'나' ${PARTIAL}`);
    expect(out).not.toMatch(/c_17|행값/);
  });

  it("허용 키라도 모양이 다르면(객체·배열 등) 값을 출력하지 않는다", () => {
    expect(summarize("column.add", { column_name: { c_1: "행값" }, column_type: ["number"], required: "yes", def_version: "7" })).toBe(OMITTED);
    expect(summarize("dataset.update", { changes: { name: { from: { x: "행값" }, to: ["행값"] } } })).toBe("이름 변경");
  });

  it("알 수 없는 행위, 객체가 아닌 details, 빈 details는 안전한 폴백이다", () => {
    expect(summarize("row.update", { code: "x", value: "행값" })).toBe(OMITTED);
    expect(summarize("team.create", null)).toBe(OMITTED);
    expect(summarize("team.create", "행값 문자열")).toBe(OMITTED);
    expect(summarize("team.create", ["행값"])).toBe(OMITTED);
    expect(summarize("team.create", {})).toBe(OMITTED);
    expect(summarize(42, {})).toBe(OMITTED);
  });

  it("이름은 길면 자르고 줄바꿈을 한 줄로 만든다", () => {
    const long = "가".repeat(100);
    const out = summarize("dataset.update", { changes: { name: { from: "a\nb", to: long } } });
    expect(out).toBe(`이름 'a b'→'${"가".repeat(40)}…'`);
  });

  it("prototype 이름(toString 등)이 필드·라벨 조회에 걸리지 않는다", () => {
    expect(summarize("dataset.update", { changes: { toString: { from: 1, to: 2 }, date_unit: { from: "constructor", to: "month" } } })).toBe(`날짜 단위 변경 ${PARTIAL}`);
  });
});
