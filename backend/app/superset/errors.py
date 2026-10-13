"""Superset 호출 오류. **사유 코드만** 담는다(응답 본문·URL·토큰을 담지 않는다).

`str(error)`와 `repr(error)`도 코드만 나온다. 로그에는 클래스 이름과 코드만 남긴다.
"""

from __future__ import annotations

# 사유 코드 -> 한국어 요약(`last_error`에 `코드: 요약`으로 저장, 관리자 현황용).
# 코드는 이 표에만 있다. SQL·Superset 응답 문구·이름·URL은 요약에 넣지 않는다.
REASON_SUMMARY: dict[str, str] = {
    "UNAVAILABLE_CONNECT": "대시보드 서비스에 연결하지 못했습니다.",
    "UNAVAILABLE_TIMEOUT": "대시보드 서비스의 응답이 늦어 중단했습니다.",
    "UNAVAILABLE_5XX": "대시보드 서비스가 오류를 돌려주었습니다.",
    "AUTH_FAILED": "대시보드 서비스 계정으로 로그인하거나 권한을 얻지 못했습니다.",
    "NOT_OWNER": "서비스 계정이 소유하지 않은 데이터셋이라 바꿀 수 없습니다.",
    "NAME_CONFLICT": "같은 이름의 다른 데이터셋이 대시보드 서비스에 이미 있습니다.",
    "VIEW_MISSING": "데이터셋의 조회용 뷰가 없어 열을 읽지 못했습니다.",
    "DB_MISMATCH": "등록된 데이터셋이 기대한 데이터 연결에 있지 않습니다.",
    "DB_NOT_FOUND": "대시보드 서비스에서 업무 데이터 연결을 찾지 못했습니다.",
    "BAD_RESPONSE": "대시보드 서비스의 응답 형식이 예상과 다릅니다.",
    "INTERNAL": "예기치 않은 오류가 발생했습니다.",
}

# 연결 문제로 보는 코드(서킷 브레이커 집계와 자동 재시도 대상).
UNAVAILABLE_CODES = frozenset({"UNAVAILABLE_CONNECT", "UNAVAILABLE_TIMEOUT", "UNAVAILABLE_5XX"})


def summarize(code: str) -> str:
    """`last_error` 값: `코드: 한국어 요약`. 알 수 없는 코드는 `REJECTED_<상태>` 꼴만 허용한다."""
    if code in REASON_SUMMARY:
        return f"{code}: {REASON_SUMMARY[code]}"
    if code.startswith("REJECTED_") and code[len("REJECTED_") :].isdigit():
        return f"{code}: 대시보드 서비스가 요청을 받아들이지 않았습니다."
    return f"INTERNAL: {REASON_SUMMARY['INTERNAL']}"


class SupersetError(Exception):
    """Superset 호출 실패의 공통 부모. `code`는 사유 코드(`REASON_SUMMARY` 또는
    `REJECTED_<상태>`)다."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code

    def __str__(self) -> str:
        return self.code


class SupersetUnavailable(SupersetError):
    """연결 불가·시간 초과·5xx. 일시적일 수 있어 나중에 다시 시도할 수 있다."""


class SupersetRejected(SupersetError):
    """Superset이 요청을 거부했다(인증·권한·검증 실패 등). 같은 요청을 다시 보내도 같다."""
