"""Superset 역할·권한 목록(저장소 고정 파일). 권한 목록은 이 파일 한 곳에만 둔다.

- 승인 근거: docs/decisions/08-superset-embedding.md §2~§5, 03b 8절(EW-3).
- 비밀번호·계정 이름 같은 환경 값은 여기에 두지 않는다(환경변수로만 받는다).
- 권한 항목은 (권한 이름, 보기/메뉴 이름) 쌍이다(Superset의 PermissionView).
- schema_access 항목의 이름은 `[DATABASE_NAME].[POSTGRES_DB].[bi_data]`로 실행 때 조립한다(`schema_access_name`).
- guest 역할 `bi_guest`(EW-4): 임베딩 대시보드를 보는 입장권(guest token)의 역할이다. 이름은 이 파일의 `GUEST_ROLE`이 정본이고
  superset_config.py의 `GUEST_ROLE_NAME`은 같은 값을 따로 적는다(Superset 웹 프로세스는 이 파일을 읽지 못한다).
  두 값이 어긋나면 ensure_roles.py가 실제 적용된 설정(app.config)과 비교해 superset-init을 실패시킨다.
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
GUEST_ROLE = "bi_guest"  # superset_config.py의 GUEST_ROLE_NAME과 같아야 한다(ensure_roles.py가 확인한다).
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
    # 임베딩 대시보드 열람 전용 guest 역할(08 §3, X-25로 21개에서 줄인 4개). 새 권한은 자동으로 추가하지 않는다.
    # 필수 3개: 현재 사용자 조회, 대시보드 읽기, 차트 읽기. 기간 필터 1개: 없으면 기간 팝업의 APPLY가 비활성이다.
    # 넣지 않는 것(승인된 결정): can_explore_json Superset, can_read DashboardPermalinkRestApi(조건부, 필요해지면 보고하고 멈춘다),
    # can_csv Superset(내보내기 금지), 쓰기·Explore·SQL Lab·목록 API 권한 전부.
    GUEST_ROLE: [
        ("can_read", "CurrentUserRestApi"),
        ("can_read", "Dashboard"),
        ("can_read", "Chart"),
        ("can_time_range", "Api"),
    ],
}

# 어떤 경우에도 있으면 안 되는 권한(역할 이름 -> 권한 쌍). 있으면 시작 실패.
FORBIDDEN_PERMISSIONS = {
    SERVICE_ROLE: [("can_grant_guest_token", "SecurityRestApi")],
    # guest 역할의 조건부 항목 2개: 지원 차트 6가지에 필요하지 않다고 확인된 상태이며, 필요해지면 보고하고 멈춘다(08 §3).
    GUEST_ROLE: [("can_explore_json", "Superset"), ("can_read", "DashboardPermalinkRestApi")],
}

# guest 역할(열람 전용)에 들어가면 안 되는 권한의 이름 조각(소문자 부분 문자열). 정확한 쌍 목록으로는 못 막는
# 내보내기·쓰기·Explore·SQL Lab 계열을 이름으로 막는다. 권한 이름 쪽과 보기/메뉴 이름 쪽을 따로 검사한다.
GUEST_FORBIDDEN_PERMISSION_NAME_PARTS = (
    "write", "add", "edit", "delete", "muldelete", "csv", "export", "download", "import", "share",
    "sqllab", "sql_lab", "execute_sql", "explore", "grant", "set_embedded",
    "access",  # schema_access, datasource_access, database_access: guest에게 데이터 접근을 직접 주지 않는다.
)
GUEST_FORBIDDEN_VIEW_NAME_PARTS = ("sqllab", "sql_lab", "sql lab", "explore", "savedquery", "csv", "export")


def forbidden_reason(role_name: str, pair: tuple) -> str | None:
    """권한 쌍이 그 역할에 금지되어 있으면 사유를, 아니면 None을 돌려준다(목록 한 곳에서 판정)."""
    if pair in FORBIDDEN_PERMISSIONS.get(role_name, []):
        return "금지 목록"
    if role_name == GUEST_ROLE:
        permission, view = pair
        for part in GUEST_FORBIDDEN_PERMISSION_NAME_PARTS:
            if part in permission.lower():
                return f"권한 이름에 '{part}' 포함(내보내기·쓰기·Explore·SQL Lab 계열 금지)"
        for part in GUEST_FORBIDDEN_VIEW_NAME_PARTS:
            if part in (view or "").lower():
                return f"보기 이름에 '{part}' 포함(내보내기·쓰기·Explore·SQL Lab 계열 금지)"
    return None


def schema_access_name(postgres_db: str) -> str:
    """schema_access 항목의 이름. Superset의 get_schema_perm(database, catalog, schema)과 같은 형식이다."""
    return f"[{DATABASE_NAME}].[{postgres_db}].[{BI_SCHEMA}]"


def resolve(entries: list, postgres_db: str) -> list:
    """자리표시자를 실제 보기/메뉴 이름으로 바꾼 (권한 이름, 보기/메뉴 이름) 목록."""
    return [
        (name, view if view is not None else schema_access_name(postgres_db))
        for name, view in entries
    ]
