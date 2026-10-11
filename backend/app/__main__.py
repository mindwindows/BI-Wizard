"""`python -m app`: uvicorn으로 backend를 실행한다. 주소와 포트는 환경변수에서 읽는다."""

import uvicorn

from app.config import get_settings
from app.db import build_database_url


def main() -> None:
    # 설정이 잘못됐으면 서버를 띄우기 전에 종료한다: 인증 스텁 스위치와 APP_ENV 조합(Settings 검증),
    # POSTGRES_APP_PASSWORD 누락(fail closed).
    settings = get_settings()
    build_database_url(settings, "app")
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=settings.backend_host,
        port=settings.backend_port,
        log_level=settings.log_level.lower(),
        workers=1,
    )


if __name__ == "__main__":
    main()
