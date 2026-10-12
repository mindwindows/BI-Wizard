"""공통 계층(`core`): 오류 형식, 요청 id, DB 세션 의존성.

설정(`app.config`), DB 엔진(`app.db`), `/health`(`app.health`), 정적 `MetaData`(`app.db_metadata`)는
import 경로를 지키려고 기존 위치에 둔다(04 §2-1은 이들도 core로 본다).
이 패키지는 그 위에 새로 얹는 부분이다.
업무 로직은 두지 않는다.
"""
