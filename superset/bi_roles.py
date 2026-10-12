"""Superset 역할·권한 목록(저장소 고정 파일). 권한 목록은 이 파일 한 곳에만 둔다.

- 승인 근거: docs/decisions/08-superset-embedding.md §2~§5, 03b 8절(EW-3).
- 비밀번호·계정 이름 같은 환경 값은 여기에 두지 않는다(환경변수로만 받는다).
- 권한 항목은 (권한 이름, 보기/메뉴 이름) 쌍이다(Superset의 PermissionView).
- schema_access 항목의 이름은 `[DATABASE_NAME].[POSTGRES_DB].[bi_data]`로 실행 때 조립한다(`schema_access_name`).
- guest 역할 `bi_guest`는 EW-4에서 추가한다(여기에 없다).
"""

# register_database.py와 ensure_roles.py가 같은 값을 쓴다(업무 데이터 연결의 표시 이름).
DATABASE_NAME = "BI-Wizard (read-only)"
# 업무 데이터(동적 표·뷰)가 놓이는 schema. 이름은 코드 상수다(db-bootstrap과 같은 값).
BI_SCHEMA = "bi_data"

# schema_access 권한 항목의 보기/메뉴 이름을 가리키는 자리표시자.
SCHEMA_ACCESS = ("schema_access", None)

# 역할 이름
SERVICE_ROLE = "bi_service"
GUEST_ISSUER_ROLE = "bi_guest_issuer"
AUTHOR_ROLE = "bi_author"
AUTHOR_SCHEMA_ROLE = "bi_author_schema"
GAMMA_ROLE = "Gamma"  # 내장 역할. bi_author를 처음 만들 때 권한을 복사하는 원본이다(직접 부여하지 않는다).

# 권한 목록을 통째로 교체하는 역할(매 기동 멱등).
ROLE_PERMISSIONS = {
    # 가상 데이터셋 등록 서비스 계정(08 §2). can_grant_guest_token은 주지 않는다(발급 계정과 분리).
    SERVICE_ROLE: [
        ("can_read", "Dataset"),
        ("can_write", "Dataset"),
        SCHEMA_ACCESS,
        ("can_read", "SecurityRestApi"),  # CSRF 토큰 조회
    ],
    # guest token 발급 전용 계정(08 §4). REST(JWT) 로그인용 can_read를 포함한 2개.
    GUEST_ISSUER_ROLE: [
        ("can_grant_guest_token", "SecurityRestApi"),
        ("can_read", "SecurityRestApi"),
    ],
    # 작성자의 bi_data schema 접근(08 §5). bi_author(Gamma 복사본)와 함께 작성자 계정에 수동으로 부여한다.
    AUTHOR_SCHEMA_ROLE: [
        SCHEMA_ACCESS,
    ],
}

# 어떤 경우에도 있으면 안 되는 권한(역할 이름 -> 권한 쌍). 있으면 시작 실패.
FORBIDDEN_PERMISSIONS = {
    SERVICE_ROLE: [("can_grant_guest_token", "SecurityRestApi")],
}


def schema_access_name(postgres_db: str) -> str:
    """schema_access 항목의 이름. Superset의 get_schema_perm(database, catalog, schema)과 같은 형식이다."""
    return f"[{DATABASE_NAME}].[{postgres_db}].[{BI_SCHEMA}]"


def resolve(entries: list, postgres_db: str) -> list:
    """자리표시자를 실제 보기/메뉴 이름으로 바꾼 (권한 이름, 보기/메뉴 이름) 목록."""
    return [
        (name, view if view is not None else schema_access_name(postgres_db))
        for name, view in entries
    ]
