"""권한 관리(`access`): 팀·사용자·소속(역할) 관리, `/api/me`, 최초 관리자·시험 사용자 시드.

04 §2-2: 소유 정적 표 `users` `teams` `team_members`(쓰기). router(API) → service(로직) →
repo(데이터 접근) 3층이다. 읽기 판정(`current_user`, 권한 함수)은 `auth` 모듈이 한다.
"""
