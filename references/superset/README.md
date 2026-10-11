# superset — Embedded SDK와 guest token 참고

| 항목 | 내용 |
| --- | --- |
| 출처 URL | https://github.com/apache/superset |
| 확보 커밋 | `e229ea4a543546b94bc3e751f611109d111cc8db` (2026-10-11, 기본 브랜치 `master` HEAD). SDK 경로 마지막 커밋은 2026-10-09 |
| 확보일 | 2026-10-11 |
| 라이선스 | Apache License 2.0 (`LICENSE.txt`, `NOTICE` 원본 동봉). SDK 패키지(`@superset-ui/embedded-sdk` 0.4.0)도 Apache-2.0 |
| 목적 | 브리프 4.6절 포털 임베딩: FastAPI가 guest token을 발급하고 프런트가 `embedDashboard`로 iframe을 연결하는 흐름, RLS 연결 방식을 참고 |
| 승인 | Gate ① (2026-10-11) 사용자 승인, `docs/decisions/02-tech-reference.md` |

## 참고할 위치
- `superset-embedded-sdk/src/index.ts` — `embedDashboard`, 토큰 갱신(`armRefresh`, `getGuestTokenRefreshTiming`)
- `superset-embedded-sdk/README.md` — 사전 조건(`EMBEDDED_SUPERSET`, `GUEST_TOKEN_JWT_SECRET`, `can_grant_guest_token`), 옵션
- `superset/security/api.py` — `POST /guest_token/` 요청·응답 스키마
- `superset/security/guest_token.py` — guest token 타입, RLS 규칙(`dataset`, `clause`)

## 주의
- **master 소스와 배포본(npm 0.4.0, Superset PyPI 6.1.0)이 다를 수 있다.** 구현 시 사용할 버전을 고정하고 해당 태그의 소스를 다시 읽는다.
- RLS `clause`는 SQL 조건 문자열이다. 사용자 입력이나 문자열 값을 그대로 넣지 않는다. 설계는 Gate ③에서 PostgreSQL·SQLAlchemy 공식 문서로 근거를 확인한 뒤 정한다.
- **원본 대조로 확인된 사항:**
  - RLS 제약의 근거 파일은 `api.py`다(`dataset`은 선택·양의 정수, `clause`는 필수 문자열, 모르는 키는 400). `guest_token.py`의 `GuestTokenRlsRule`은 `dataset: Optional[str]`이다.
  - 서버는 `clause`를 검증하지 않는다(`api.py`에 "check rls rules for validity?" TODO뿐). 감사 로그에도 `clause` 본문을 남기지 않는다. `GUEST_TOKEN_VALIDATOR_HOOK`으로 검증을 추가할 수 있다.
  - SDK README의 경로 표기는 `/security/guest_token`이고 서버 라우트는 `/guest_token/`(리소스명 `security`)이다.
  - `getGuestTokenRefreshTiming`의 정의는 `./guestTokenRefresh`에 있어 **받지 않았다.** 토큰 만료 전 갱신 시점 계산 방식은 이 폴더로 확인할 수 없다.
  - iframe sandbox 기본값(`allow-same-origin`, `allow-scripts`, `allow-popups` 등)과 `fetchGuestToken` 기본 제한 시간 30초가 `index.ts`에 있다.
- Superset 서비스 구성의 팀 웹서버 허용 여부는 브리프 5절 4번, Explore 화면 제공 방식은 5절 7번(미결정)이다.
- `GUEST_TOKEN_JWT_SECRET`은 Secret이므로 `.env`에만 둔다.
- Superset 내부 코드는 수정하지 않는다(브리프 4.6절).

## 사용 규칙
- 원본 그대로 보관한다. **파일을 수정하지 않는다.** Apache 2.0 복사 시 라이선스·NOTICE 유지와 변경 표시 의무를 사용자와 먼저 확인한다.

## 파일 목록과 무결성
| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `LICENSE.txt` | 11585 | `ff254eb676d6ed2b36f26a74e7c50411cd57e11823f3e91004ffe48fcfd273cf` |
| `NOTICE` | 169 | `9a94a669b32e29b02157ed507fd01689b7c65237a44f6ae4984b240c6dc2a2ab` |
| `superset-embedded-sdk/src/index.ts` | 25300 | `7d9be403f51a4552f7c3eac490c621811a1d5b8a20c3b2cde540f911ca725955` |
| `superset/security/api.py` | 17397 | `71b96a19679e6b7265122a9cb2c31d29b471180ffc8d7b304923062d1bce88c4` |
| `superset/security/guest_token.py` | 8048 | `93fa660b67aea46ef525839a402c014e513b9569c037491317936e99ef269fe3` |
