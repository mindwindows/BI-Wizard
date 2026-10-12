"""PostgreSQL 연결. 드라이버는 pg8000(BSD-3)이며 URL은 URL.create로 만든다.

접속 계정 이름은 **코드 상수**다(`docs/decisions/03b-gate3-round-decisions.md` 3-2).
- backend 런타임: `bi_app`(정적 표는 명시 GRANT만, `bi_data`에만 CREATE)
- 마이그레이션(migrate 서비스): `bi_owner`(정적 표 소유)
이미지 슈퍼유저(`POSTGRES_USER`)로 접속하는 경로는 없다. 환경변수로 받는 것은 비밀번호뿐이다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import SecretStr
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from app.config import Settings

APP_DB_USER = "bi_app"
OWNER_DB_USER = "bi_owner"

DbRole = Literal["app", "owner"]


def _credentials(settings: Settings, role: DbRole) -> tuple[str, SecretStr | None, str]:
    if role == "app":
        return APP_DB_USER, settings.postgres_app_password, "POSTGRES_APP_PASSWORD"
    if role == "owner":
        return OWNER_DB_USER, settings.postgres_owner_password, "POSTGRES_OWNER_PASSWORD"
    raise ValueError(f"알 수 없는 DB 역할: {role!r}")


def build_database_url(settings: Settings, role: DbRole) -> URL:
    """접속 URL을 만든다. 문자열을 이어 붙이지 않아 비밀번호의 특수문자도 안전하다.

    비밀번호가 없거나 비어 있으면 실패한다(fail closed). 오류 메시지에는 변수 이름만 쓴다.
    """
    username, password, variable = _credentials(settings, role)
    secret = password.get_secret_value() if password is not None else ""
    if not secret:
        raise ValueError(f"{variable}가 설정되어 있지 않거나 비어 있다.")
    return URL.create(
        drivername="postgresql+pg8000",
        username=username,
        password=secret,
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
    )


def create_db_engine(settings: Settings) -> Engine:
    """backend 런타임 엔진(`bi_app`)."""
    return create_engine(
        build_database_url(settings, "app"),
        pool_pre_ping=True,
        hide_parameters=True,  # 오류 메시지·로그에 SQL 파라미터 값(login_id 등)을 넣지 않는다.
        pool_size=5,
        max_overflow=0,
        # 수식 글자 상수 완화책 ①(07 §4-3): 세션의 `standard_conforming_strings`를 on으로
        # 고정한다. 서버 설정이 바뀌어도 이 연결의 글자 리터럴 해석이 바뀌지 않는다(시작 자가
        # 점검도 확인한다).
        connect_args={"timeout": 5, "startup_params": {"standard_conforming_strings": "on"}},
    )
