"""환경변수 기반 설정.

설정은 환경변수에서만 읽는다(.env 파일을 직접 읽지 않는다). 변수 이름은 `.env.example`의
canonical name과 같다. 새 변수를 추가하면 `.env.example -> 이 파일 -> compose.yml ->
Jenkinsfile -> README/Skill -> 테스트` 순서로 영향을 확인한다.
"""

from __future__ import annotations

import re
from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 세그먼트에 쓸 수 있는 문자. 규칙은 frontend/src/config.ts, nginx 시작 스크립트
# (18-bi-wizard-env.envsh)와 같다.
_SEGMENT_PATTERN = re.compile(r"[A-Za-z0-9._~-]+")


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
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

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
    postgres_user: str = Field(min_length=1)
    postgres_password: SecretStr = Field(min_length=1)

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
