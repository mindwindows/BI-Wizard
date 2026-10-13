"""감사 기록(`audit`, FU-2a, 04 §2-1·§5-1, 06 §2-1): 쓰기 함수 `record`와 관리자 전용 목록 조회(F1).

호출자는 `access`·`dataset`·`superset` service뿐이다(`formula`·`entry`는 직접 부르지 않는다).
`record`는 커밋·롤백을 하지 않는다: 호출한 쪽이 `session.commit()` 앞에서 부른다.
"""

from app.audit.service import CLI_ACTOR, Actor, AuditRecordError, CliActor, record

__all__ = ["CLI_ACTOR", "Actor", "AuditRecordError", "CliActor", "record"]
