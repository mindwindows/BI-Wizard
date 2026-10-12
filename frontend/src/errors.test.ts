import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { describeApiError } from "./errors";

const err = (status: number, code: string, details: unknown = null, message = "서버 문구") =>
  new ApiError(status, { code, message, details, request_id: null });

describe("describeApiError (05 §3 코드별 문구)", () => {
  it("LAST_ADMIN", () => {
    expect(describeApiError(err(409, "LAST_ADMIN"))).toContain("마지막 관리자");
  });

  it("ALREADY_EXISTS는 details.field로 나눈다", () => {
    expect(describeApiError(err(409, "ALREADY_EXISTS", { field: "code" }))).toContain("같은 코드의 팀");
    expect(describeApiError(err(409, "ALREADY_EXISTS", { field: "login_id" }))).toContain("로그인 ID");
    expect(describeApiError(err(409, "ALREADY_EXISTS", { field: "zzz" }))).toBe("이미 같은 값이 있습니다.");
    expect(describeApiError(err(409, "ALREADY_EXISTS"))).toBe("이미 같은 값이 있습니다.");
  });

  it("VALIDATION_ERROR는 필드와 필드 코드를 쉬운 말로 풀어 쓴다", () => {
    const text = describeApiError(
      err(422, "VALIDATION_ERROR", {
        fields: [
          { field: "code", code: "BAD_FORMAT", message: "x" },
          { field: "name", code: "TOO_LONG", message: "y" },
        ],
      }),
    );
    expect(text).toContain("팀 코드: 형식이 맞지 않습니다");
    expect(text).toContain("이름: 너무 깁니다");
  });

  it("VALIDATION_ERROR에 fields가 없어도 안전하다", () => {
    expect(describeApiError(err(422, "VALIDATION_ERROR", null))).toBe("입력한 내용을 확인해 주세요.");
  });

  it("권한·없음·네트워크·500", () => {
    expect(describeApiError(err(403, "FORBIDDEN"))).toContain("권한이 없습니다");
    expect(describeApiError(err(404, "NOT_FOUND"))).toContain("찾을 수 없습니다");
    expect(describeApiError(err(0, "NETWORK_ERROR"))).toContain("연결하지 못했습니다");
    expect(describeApiError(err(500, "INTERNAL_ERROR"))).toContain("예기치 않은 오류");
  });

  it("모르는 4xx 코드는 서버의 한국어 문구, 모르는 5xx는 일반 문구(서버 내부 문구를 믿지 않음)", () => {
    expect(describeApiError(err(400, "SOMETHING_NEW", null, "새 규칙 위반입니다."))).toBe("새 규칙 위반입니다.");
    expect(describeApiError(err(503, "SOMETHING_NEW", null, "db down: secret"))).toBe("요청을 처리하지 못했습니다.");
    expect(describeApiError(err(404, "HTTP_404", null, "요청을 처리하지 못했습니다."))).toBe("요청을 처리하지 못했습니다.");
  });

  it("SERVICE_UNAVAILABLE(503)은 로그아웃이 아니라 일시 장애 문구", () => {
    const text = describeApiError(err(503, "SERVICE_UNAVAILABLE", null, "db down: secret"));
    expect(text).toBe("서버가 일시적으로 응답하지 못합니다. 잠시 뒤 다시 시도하세요.");
    expect(text).not.toContain("로그인");
  });

  it("TARGET_INACTIVE(409)는 details.field별로 비활성 팀·사용자 소속 지정 불가를 안내한다", () => {
    expect(describeApiError(err(409, "TARGET_INACTIVE", { field: "team" }))).toContain("비활성 팀");
    expect(describeApiError(err(409, "TARGET_INACTIVE", { field: "user" }))).toContain("비활성 사용자");
    const generic = describeApiError(err(409, "TARGET_INACTIVE", { field: "zzz" }));
    expect(generic).toContain("비활성");
    expect(generic).toContain("소속");
    expect(describeApiError(err(409, "TARGET_INACTIVE"))).toContain("소속");
  });

  it("입력 그리드 오류 코드(05 §3)는 쉬운 문구", () => {
    expect(describeApiError(err(409, "CELL_CONFLICT"))).toContain("다른 사람이 먼저 이 칸");
    expect(describeApiError(err(409, "PASTE_CONFLICT"))).toContain("아무것도 저장하지 않았습니다");
    expect(describeApiError(err(409, "PERIOD_CONFLICT"))).toContain("같은 기간의 행");
    expect(describeApiError(err(404, "ROW_NOT_FOUND"))).toContain("행을 찾을 수 없습니다");
  });

  it("METHOD_NOT_ALLOWED(405)", () => {
    expect(describeApiError(err(405, "METHOD_NOT_ALLOWED"))).toContain("허용되지 않는");
  });

  it("422 VALIDATION_ERROR 하나로 형식 오류를 다룬다(400 BAD_REQUEST 문구에 의존하지 않음)", () => {
    expect(describeApiError(err(422, "VALIDATION_ERROR", { fields: [] }))).toBe("입력한 내용을 확인해 주세요.");
    // BAD_REQUEST는 더 이상 오지 않으므로 전용 문구가 없고, 모르는 4xx 규칙을 따른다.
    expect(describeApiError(err(400, "BAD_REQUEST", null, "서버 문구"))).toBe("서버 문구");
  });

  it("1b 코드: 행이 있어 변경 불가, 열 잠김, 순환, 열 이름 중복", () => {
    expect(describeApiError(err(422, "DATASET_HAS_ROWS"))).toContain("이미 입력된 행");
    expect(describeApiError(err(422, "COLUMN_LOCKED"))).toContain("바꿀 수 없습니다");
    expect(describeApiError(err(422, "FORMULA_CIRCULAR"))).toContain("순환");
    expect(describeApiError(err(409, "ALREADY_EXISTS", { field: "display_name" }))).toContain("같은 이름의 열");
  });

  it("DEFINITION_BUSY·WRITE_BUSY는 retry_after가 있으면 몇 초 뒤인지 덧붙인다", () => {
    expect(describeApiError(err(503, "DEFINITION_BUSY", { retry_after: 3 }))).toContain("약 3초");
    expect(describeApiError(err(503, "DEFINITION_BUSY", null))).toContain("잠시 뒤");
    expect(describeApiError(err(503, "DEFINITION_BUSY", null))).not.toContain("약");
  });

  it("정의 필드 이름과 코드(1b)를 쉬운 말로 푼다", () => {
    const text = describeApiError(
      err(422, "VALIDATION_ERROR", {
        fields: [
          { field: "display_name", code: "RESERVED", message: "x" },
          { field: "rules", code: "BAD_FORMAT", message: "x" },
          { field: "date_unit", code: "BAD_FORMAT", message: "x" },
          { field: "base_date_column_id", code: "BAD_FORMAT", message: "x" },
        ],
      }),
    );
    expect(text).toContain("표시 이름: 사용할 수 없는 이름입니다");
    expect(text).toContain("검증 규칙: 형식이 맞지 않습니다");
    expect(text).toContain("날짜 단위: 형식이 맞지 않습니다");
    expect(text).toContain("기준 날짜 열: 형식이 맞지 않습니다");
  });

  it("ApiError가 아니면 일반 문구", () => {
    expect(describeApiError(new Error("boom"))).toContain("오류가 발생했습니다");
  });
});
