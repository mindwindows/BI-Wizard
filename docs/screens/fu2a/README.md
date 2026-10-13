# FU-2a 화면 스크린샷 (S10 감사 기록)

- 촬영일: 2026-10-14(서버 시계 기준), HEAD `d8a05e2` + 작업 트리(대상 번호 입력칸 폭 수정 `size` 8 → 16). 그 작업 트리는 이후 커밋 `81cb582`(제품 코드 최종)에 포함됐다
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면). 8장, 합계 약 1.1 MiB.
- 데이터: 전부 합성이다(팀·사용자·데이터셋·대시보드 이름과 임베드 번호는 `uuid4`로 만든 값). 실제 사용자·업무 데이터는 없다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 신원 전환기로 관리자(`stub-admin`)·입력자(`stub-entry`)를 바꿔 찍었다. 위쪽 점선 "개발용 신원" 선택은 이 때문이다(운영 설정에서는 나타나지 않는다).
- 환경: 로컬 compose(전용 프로젝트명 `fu2ashot`, 포털 `127.0.0.1:36280`, backend 39280), `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 새 DB. 임시 env 파일은 `_workspace/qa/`(Git 제외)에 만든 더미 값뿐이고 사용자 `.env`는 쓰지 않았다. `docker compose up -d --no-build frontend`로 `postgres`·`db-bootstrap`·`migrate`·`backend`·`frontend`만 띄웠다(Superset은 이 화면에 필요 없어 띄우지 않았다).
- 비밀값 대조: 촬영 스크립트가 모든 화면의 DOM 글자·HTML을 임시 env의 비밀성 값(`*PASSWORD*`, `*SECRET*`, `*KEY*`, `*TOKEN*`)과 토큰 모양(`eyJ…`)·내부 경로·예외 흔적 패턴에 대조했고 발견 **0건**이었다. 모든 PNG를 눈으로도 확인했다(비밀번호·토큰·행 값·수식 원문 없음). 화면의 임베드 번호(`6224f9fa-…`)는 E3가 모두에게 공개하는 값으로 합성이다.

## 파일 목록
| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu2a-empty-state-no-records.png` | S10 | 빈 상태(필터 없음): "아직 기록이 없습니다." | 새 DB, 시드 전, `stub-admin` |
| `fu2a-list-default.png` | S10 | 목록 첫 쪽(최신순 50건): 일시·행위자·행위·대상·요약, 정의·소속·팀·사용자·대시보드 행위가 섞여 있고 쪽 이동줄은 아래에 있어 첫 화면에서는 잘림 | 시드 뒤 `stub-admin` |
| `fu2a-list-page2.png` | S10 | 다음 쪽: "전체 61건 중 51–61", 맨 아래에 행위자 "서버 명령" 행(최초 관리자 등록) | "다음" 클릭 |
| `fu2a-filter-applied.png` | S10 | 필터 적용: 대상 종류 "데이터셋" + 번호 1 → 그 데이터셋의 정의 이력 9건(데이터셋 만들기·열 추가·설정 변경·열 수정·계산 열 추가·수식 수정) | 필터 입력 뒤 "조회" |
| `fu2a-filter-applied-action.png` | S10 | 필터 적용: 행위 "대시보드 수정"(이름 변경, 연결 해제·다시 연결) | 같은 방법 |
| `fu2a-filter-applied-server-command.png` | S10 | 필터 적용: 행위 "최초 관리자 등록" → 행위자 "서버 명령" 1건 | 같은 방법 |
| `fu2a-empty-state-filtered.png` | S10 | 빈 상태(필터 있음): "조건에 맞는 기록이 없습니다." + 필터 지우기 버튼 | 대상 종류 "사용자", 번호 999999 |
| `fu2a-forbidden-nonadmin.png` | S10 비관리자 거부 | 직접 접속: "관리자만 볼 수 있습니다"(필터·목록 없음, 관리 메뉴 없음) | `stub-entry`가 `/bi-wizard/admin/audit`로 접속 |

## 촬영 방법
playwright는 저장소 의존성이 아니다(`PLAYWRIGHT_MODULE`, `CHROMIUM_PATH` 환경변수로 저장소 밖 설치를 가리킨다). 스크립트는 `capture/capture2a.cjs`(촬영), `capture/seed2a.py`(합성 데이터 시드)다. 사용 명령은 비밀 없이 아래와 같다.

1. 더미 값만 든 임시 env 파일을 `_workspace/qa/`에 만든다(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`, `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 비밀 변수 10개는 새 무작위 값, 포트는 65535 이하). 이미지는 로컬에서 만들어 `bi-wizard-backend:local`·`bi-wizard-frontend:local`로 둔다(이 세션은 프록시 CA를 넣는 보조 Dockerfile을 `docker build -f … --build-context ca=/root/.ccr`로 썼고 저장소에는 넣지 않았다).
2. 새 DB로 띄운다: `docker compose -p fu2ashot --env-file <임시 env> up -d --no-build frontend`, 이어서 `exec -T backend python -m app.cli seed-stub-users`.
3. 빈 상태를 먼저 찍는다(기록 0건): `node capture/capture2a.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --env <임시 env> --out . --only empty`
4. 서버 명령 행: `exec -T backend python -m app.cli create-admin --login-id cli-admin --display-name "서버 관리자"`
5. 시드(실제 API: 대시보드 연결·이름 변경 40번, 팀·사용자·소속, 데이터셋·열·수식, 연결 해제·다시 연결): `python3 capture/seed2a.py http://127.0.0.1:36280/bi-wizard/api <ids2a.json>`
6. 나머지 촬영: `node capture/capture2a.cjs … --ids <ids2a.json> --only main` (마지막 줄 "비밀값·내부 경로 발견 건수: 0" 확인)
7. 정리: 컨테이너는 `stop` 뒤 서비스 이름을 지정해 `rm -f`, 볼륨은 이름(`fu2ashot_postgres_data`)을 지정해 삭제한다(`down -v`·`volume prune` 금지, `bi-wizard_postgres_data`는 건드리지 않는다).

## 촬영 중 고친 화면 결함
- 대상 번호 입력칸이 좁아 안내 글자("종류를 먼저 선택")가 잘렸다 → `size`를 16으로 넓혔다(`frontend/src/features/audit/AuditPage.tsx`). 고친 뒤 8장을 모두 다시 찍었다.

## 알려진 한계
- 표의 열 폭은 내용에 따라 자동으로 정해져(`table-layout: auto`) 조회 결과마다 조금 달라진다(필터 전후 화면에서 열 위치가 약간 움직임).
- 모든 시드 변경이 같은 초 안에 일어나 일시 열이 거의 같다. 정렬은 시각 내림차순, 같으면 번호 내림차순이다(05 F1).
- 쪽 이동줄은 50건 목록 아래에 있어 `fu2a-list-default.png` 첫 화면에는 보이지 않는다(쪽 이동은 `fu2a-list-page2.png`).
- 촬영하지 않은 것: 503 재시도 화면, 422 입력 오류 화면, 페이지 이동 중 로딩 표시(시험은 vitest로 덮었다). 날짜 입력창은 Chromium 기본 모양이다.
