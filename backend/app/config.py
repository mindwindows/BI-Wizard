"""환경변수 기반 설정.

설정은 환경변수에서만 읽는다(.env 파일을 직접 읽지 않는다). 변수 이름은 `.env.example`의
canonical name과 같다. 새 변수를 추가하면 `.env.example -> 이 파일 -> compose.yml ->
Jenkinsfile -> README/Skill -> 테스트` 순서로 영향을 확인한다.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 세그먼트에 쓸 수 있는 문자. 규칙은 frontend/src/config.ts, nginx 시작 스크립트
# (18-bi-wizard-env.envsh)와 같다.
_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9._~-]+")


# 인증 스텁(시험용 사용자로 접속자를 흉내 내는 임시 기능)을 켤 수 있는 APP_ENV. 이 목록 밖이면
# 스텁 스위치가 켜진 채로는 시작하지 않는다(fail-closed, bi-review 7-5, 03b 5-2 K3).
AUTH_STUB_ALLOWED_ENVS = frozenset({"local", "test"})


def check_auth_stub_allowed(*, enabled: bool, app_env: str, app_env_explicit: bool) -> None:
    """인증 스텁 스위치와 APP_ENV의 조합을 판정한다. 허용되지 않으면 ValueError.

    - 스위치가 꺼져 있으면 항상 통과한다(기본값).
    - 켜져 있으면 APP_ENV가 환경변수로 **명시적으로 설정**되어 있고(코드 기본값 `local`이 채운
      경우는 미설정으로 본다) 값이 허용 목록(`local`, `test`) 안일 때만 통과한다. 빈 값,
      대소문자 변형, `production`/`staging` 같은 다른 값은 모두 거부한다(정규화하지 않는다).
    """
    if not enabled:
        return
    if not app_env_explicit:
        raise ValueError(
            "AUTH_STUB_ENABLED=true는 APP_ENV를 명시적으로 설정해야 한다"
            "(설정하지 않은 값은 운영 환경일 수 있어 거부한다)."
        )
    if app_env not in AUTH_STUB_ALLOWED_ENVS:
        raise ValueError(
            "AUTH_STUB_ENABLED=true는 APP_ENV가 local 또는 test일 때만 허용된다"
            "(개발·시험 환경 전용)."
        )


def validate_base_path(value: str) -> str:
    """하위 경로 형식을 검사한다.

    빈 값(루트 배포)은 허용한다. 아니면 앞 '/' 필수, 뒤 '/' 금지, '//' 금지, 세그먼트는 허용 문자만,
    '.'와 '..' 세그먼트와 개행은 거부한다(값 전체를 검사한다).
    """
    if value == "":
        return value
    segments = value[1:].split("/") if value.startswith("/") else []
    valid = bool(segments) and all(
        _SEGMENT_PATTERN.fullmatch(segment) and segment not in {".", ".."} for segment in segments
    )
    if not valid:
        raise ValueError(
            "하위 경로는 빈 값이거나 '/경로' 형식이어야 한다"
            "(앞 '/' 필수, 뒤 '/'와 '.'/'..' 세그먼트 금지)."
        )
    return value


class Settings(BaseSettings):
    # hide_input_in_errors: 검증 오류 메시지에 입력 값(비밀번호 포함)이 나오지 않게 한다.
    model_config = SettingsConfigDict(
        extra="ignore", case_sensitive=False, hide_input_in_errors=True
    )

    app_name: str = "BI-Wizard"
    app_env: str = "local"
    app_debug: bool = False
    # 포털의 하위 경로(운영자 확인 필요). backend의 root_path로 쓴다.
    app_base_path: str = ""
    # false: 프록시가 접두를 유지한 채 전달, true: 프록시가 접두를 떼고 전달.
    app_proxy_strip_prefix: bool = False

    backend_host: str = "0.0.0.0"  # noqa: S104 - 컨테이너 안에서 모든 인터페이스에 바인딩한다.
    backend_port: int = Field(default=8000, ge=1, le=65535)

    postgres_host: str = "postgres"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    postgres_db: str = Field(min_length=1)
    # DB 접속 계정 이름은 코드 상수다(app/db.py: backend=bi_app, 마이그레이션=bi_owner).
    # 비밀번호만 받는다. POSTGRES_USER/POSTGRES_PASSWORD(이미지 슈퍼유저)는 backend가 읽지 않는다
    # (03b 3-2, 운영 가이드와의 의도적 차이). 컨테이너마다 필요한 비밀번호만 전달하므로 둘 다 선택
    # 값이고, 필요한 쪽이 없으면 접속 URL을 만들 때 실패한다.
    postgres_app_password: SecretStr | None = None
    postgres_owner_password: SecretStr | None = None

    # 인증 스텁 스위치. 기본 꺼짐. 켜는 조건은 check_auth_stub_allowed 참고.
    # (스텁 로그인 기능 자체는 FU-1a에서 만든다.)
    auth_stub_enabled: bool = False

    log_level: str = "INFO"

    @field_validator("app_base_path")
    @classmethod
    def _check_base_path(cls, value: str) -> str:
        return validate_base_path(value)

    @field_validator("log_level")
    @classmethod
    def _check_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL은 CRITICAL/ERROR/WARNING/INFO/DEBUG 중 하나여야 한다.")
        return level

    @model_validator(mode="after")
    def _check_auth_stub(self) -> Settings:
        # "app_env"가 model_fields_set에 있으면 환경변수로 명시된 값이다(코드 기본값은 없다).
        check_auth_stub_allowed(
            enabled=self.auth_stub_enabled,
            app_env=self.app_env,
            app_env_explicit="app_env" in self.model_fields_set,
        )
        return self

    @property
    def received_api_prefix(self) -> str:
        """프록시 뒤에서 backend가 실제로 받는 API 접두.

        APP_PROXY_STRIP_PREFIX=false이면 `${APP_BASE_PATH}/api`, true이면 `/api`다.
        (라우트는 항상 `/api` 아래에 있고, `root_path`가 하위 경로를 떼어 두 형태를 모두 받는다.)
        """
        if self.app_proxy_strip_prefix:
            return "/api"
        return f"{self.app_base_path}/api"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 값은 환경변수에서 온다.
