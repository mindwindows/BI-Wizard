"""서버 명령(`python -m app.cli <명령>`). 새 환경변수 없이 기존 설정(`bi_app` 접속)을 그대로 쓴다.

- `create-admin --login-id X --display-name Y`: 최초 관리자를 만든다(03b 5-2 K3 ㄷ). 같은
  로그인 ID의 활성 관리자가 이미 있으면 아무것도 바꾸지 않고 성공(멱등), 일반 사용자나 비활성
  사용자면 거부한다(권한을 조용히 올리지 않는다). 비밀번호는 다루지 않는다. 새로 만든 경우에만
  감사 기록 `user.bootstrap_admin`이 한 건 남는다(행위자 없음, `actor_source=cli`, 04 §5-1).
- `seed-stub-users`: 시험용 팀·사용자·소속을 넣는다(개발·시험 전용). `AUTH_STUB_ENABLED=true`이고
  `APP_ENV`가 명시적으로 `local`/`test`인 설정에서만 실행하고, 아니면 거부한다
  (`bi-review` 7-5). 운영 기록 대상이 아니므로 감사 기록을 남기지 않는다(04 §5-1).

종료 코드: 0 성공, 1 DB 오류, 2 입력 오류 또는 기존 사용자 충돌, 3 설정/규칙으로 거부.
메시지에는 비밀번호·접속 정보를 넣지 않는다.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.access import service
from app.access.schemas import LoginId, UserDisplayName
from app.auth.stub import assert_stub_allowed
from app.config import Settings, get_settings
from app.db import create_db_engine

EXIT_OK = 0
EXIT_DB = 1
EXIT_INPUT = 2
EXIT_REFUSED = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="BI-Wizard 서버 명령")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="최초 관리자 만들기")
    admin.add_argument("--login-id", required=True, help="신원 어댑터가 주는 로그인 ID")
    admin.add_argument("--display-name", required=True, help="화면에 보일 이름")
    sub.add_parser("seed-stub-users", help="시험용 팀·사용자 넣기(스텁이 켜진 개발·시험 환경 전용)")
    return parser


def _load_settings() -> Settings | None:
    try:
        return get_settings()
    except ValidationError:
        # 입력 값은 숨긴다(hide_input_in_errors). 어떤 규칙인지는 설정 문서를 본다.
        print(
            "설정이 올바르지 않아 실행하지 않는다(예: AUTH_STUB_ENABLED와 APP_ENV 조합).",
            file=sys.stderr,
        )
        return None


def main(
    argv: Sequence[str] | None = None,
    *,
    settings: Settings | None = None,
    engine: Engine | None = None,
) -> int:
    args = _parser().parse_args(argv)
    if settings is None:
        settings = _load_settings()
        if settings is None:
            return EXIT_REFUSED

    if args.command == "seed-stub-users":
        try:
            assert_stub_allowed(settings)
        except ValueError as exc:
            print(f"시험용 사용자 시드를 거부한다: {exc}", file=sys.stderr)
            return EXIT_REFUSED

    if args.command == "create-admin":
        try:
            login_id = TypeAdapter(LoginId).validate_python(args.login_id)
            display_name = TypeAdapter(UserDisplayName).validate_python(args.display_name)
        except ValidationError:
            print(
                "로그인 ID(1~200자) 또는 표시 이름(1~100자)이 올바르지 않다"
                "(빈 값, 너무 긺, 제어문자).",
                file=sys.stderr,
            )
            return EXIT_INPUT

    own_engine = engine is None
    try:
        engine = engine or create_db_engine(settings)
    except ValueError as exc:  # POSTGRES_APP_PASSWORD 누락 등(변수 이름만 들어 있다)
        print(f"DB 접속 설정이 없다: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    try:
        with Session(engine) as session:
            if args.command == "create-admin":
                return _create_admin(session, login_id, display_name)
            return _seed(session)
    except Exception as exc:
        # SQL·접속 정보가 섞일 수 있어 예외 클래스 이름만 보여 준다.
        print(
            f"DB 작업에 실패했다({type(exc).__name__}). postgres와 migrate가 끝났는지 확인하세요.",
            file=sys.stderr,
        )
        return EXIT_DB
    finally:
        if own_engine:
            engine.dispose()


def _create_admin(session: Session, login_id: str, display_name: str) -> int:
    try:
        created = service.create_first_admin(session, login_id=login_id, display_name=display_name)
    except service.UserExistsError:
        print(
            "이미 등록된 사용자라 최초 관리자로 만들지 않았다"
            "(관리자 권한은 관리자 화면에서 바꾼다).",
            file=sys.stderr,
        )
        return EXIT_INPUT
    print("관리자를 만들었다." if created else "이미 활성 관리자로 등록되어 있다(변경 없음).")
    return EXIT_OK


def _seed(session: Session) -> int:
    created = service.seed_stub_data(session)
    print(
        f"시험용 데이터를 넣었다: 팀 {created['teams']}, 사용자 {created['users']}, "
        f"소속 {created['memberships']}개 새로 만듦."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
