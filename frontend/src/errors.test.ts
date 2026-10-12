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

  it("ApiError가 아니면 일반 문구", () => {
    expect(describeApiError(new Error("boom"))).toContain("오류가 발생했습니다");
  });
});
