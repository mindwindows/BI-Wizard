# FU-2b 화면 스크린샷 (S2 보관·복구, S4 읽기 전용 배너, S3 이름 충돌, S10 감사 행)

- 촬영일: 2026-10-14(서버 시계 기준), backend HEAD `57a2085` + frontend 작업 트리(FU-2b 화면, 이 README 시점에 커밋 전).
- 크기: 모두 1920×1080 PNG(viewport, `deviceScaleFactor` 1, 스크롤하지 않은 첫 화면). 10장.
- 데이터: 전부 합성이다(스텁 팀·사용자와 시드가 만든 팀·데이터셋 이름). 실제 사용자·업무 데이터는 없다.
- 신원: 개발용 인증 스텁(`AUTH_STUB_ENABLED=true`, `APP_ENV=local`)의 신원 전환기로 정의 담당자(`stub-definer`)·입력자(`stub-entry`)·관리자(`stub-admin`, 소속 팀 없음)를 바꿔 찍었다. 위쪽 점선 "개발용 신원"은 이 때문이다(운영 설정에는 나타나지 않는다).
- 환경: 로컬 compose(프로젝트명 `fu2bshot`, 포털 `127.0.0.1:36280`), `APP_BASE_PATH=/bi-wizard`, `APP_PROXY_STRIP_PREFIX=false`, 새 DB. 임시 env는 `_workspace/qa/`(Git 제외)의 더미 값뿐이다. Superset 없이 `postgres`·`db-bootstrap`·`migrate`·`backend`·`frontend`만 띄웠다. **그래서 목록의 "동기 상태" 열은 모두 "등록 실패"로 보인다**(Superset이 없기 때문이며 보관·복구와 무관).
- 비밀값 대조: 촬영 스크립트가 모든 화면의 DOM 글자·HTML을 임시 env의 비밀성 값과 토큰 모양에 대조했고 발견 **0건**이었다. 모든 PNG를 눈으로도 확인했다.

## 파일 목록
| 파일 | 화면 | 상태 | 촬영 조건 |
| --- | --- | --- | --- |
| `fu2b-s2-list-active.png` | S2 | 기본 보기 "사용 중": 보관 행이 없고, 정의 담당자에게만 행별 "보관" 버튼과 "관리" 열이 있음(B팀 행은 담당자가 아니어서 버튼 없음) | `stub-definer` |
| `fu2b-s2-list-all.png` | S2 | 보기 "전체": 보관 행에 "보관" 배지와 "복구" 버튼, 비활성 팀(폐쇄팀) 소유 보관 행에도 "복구" 버튼 | 같은 신원, 보기 전체 |
| `fu2b-s2-archive-confirm.png` | S2 | 보관 확인창: 뜻(입력·정의 변경이 멈추고 목록에서 숨겨짐, 복구하면 다시 고칠 수 있음)과 한계(Superset·읽기 전용 데이터로는 계속 보임, 영구 삭제는 아직 없음) 강조 상자, 이름 입력 없음, 보관하기/취소 | "보관" 클릭, 확인은 누르지 않음 |
| `fu2b-workspace-archived-banner.png` | S4 | 보관 중 읽기 전용 배너 + 복구 버튼, 열 추가·계산 열 추가·데이터셋 설정 저장 비활성, 그리드는 읽기 전용 안내(값은 보임) | 보관된 "작년 매출" 주소 접속 |
| `fu2b-name-conflict-archived.png` | S3 | 보관된 "작년 매출"과 같은 이름으로 만들기: 서버 안내 "…보관된 데이터셋과 같은 이름입니다. 보관된 데이터셋을 복구하거나 다른 이름을 쓰세요." 가 폼 안에 보임 | 만들기 클릭 |
| `fu2b-s2-nonadmin-no-buttons.png` | S2 | 입력자: "전체" 보기에서 배지는 보이고 버튼과 "관리" 열은 없음 | `stub-entry` |
| `fu2b-s2-admin-no-buttons.png` | S2 | 소속 팀 없는 관리자: 마찬가지로 버튼·"관리" 열 없음(관리자 예외 없음) | `stub-admin` |
| `fu2b-s2-restored.png` | S2 | 복구 직후: "'임시 실험' 데이터셋을 복구했습니다…" 안내, 그 행에서 배지가 사라지고 "보관" 버튼이 다시 보임 | 정의 담당자가 보기 "전체"에서 "복구" 확인 |
| `fu2b-audit-archive-rows.png` | S10 | 행위 "데이터셋 보관" 필터: 대상 "데이터셋 #번호 이름", 요약 "데이터셋 보관" | `stub-admin` |
| `fu2b-audit-restore-rows.png` | S10 | 행위 "데이터셋 복구" 필터 | 같은 방법 |

## 촬영 방법
`fu2a`와 같다. 스크립트는 `capture/capture2b.cjs`(촬영), `capture/seed2b.py`(합성 데이터 시드)다. 비밀 없이 쓴 명령:
1. 이미지: 현재 소스에서 새로 빌드(CA 오버레이 보조 Dockerfile은 저장소 밖 `_workspace/qa/`): `docker build -f <보조 Dockerfile> --build-context ca=/root/.ccr -t bi-wizard-{backend,frontend}:local {backend,frontend}`.
2. 기동: `docker compose -p fu2bshot --env-file <임시 env> up -d --no-build frontend`, `exec -T backend python -m app.cli seed-stub-users`.
3. 시드(실제 API): `python3 capture/seed2b.py http://127.0.0.1:36280/bi-wizard/api <ids2b.json>` (A팀 사용 중 2·보관 2, B팀 1, 비활성이 된 폐쇄팀 소유 보관 1).
4. 촬영: `PLAYWRIGHT_MODULE=/opt/node-tools/node_modules/playwright node capture/capture2b.cjs --origin http://127.0.0.1:36280 --base /bi-wizard --ids <ids2b.json> --env <임시 env> --out .` (마지막 줄 "비밀값·내부 경로 발견 건수: 0" 확인). 복구 장면이 데이터를 바꾸므로 다시 찍을 때는 "임시 실험"(데이터셋 5)을 먼저 보관 상태로 되돌린다.
5. 정리: `stop`·`rm -f`에 서비스 이름을 지정하고 볼륨 `fu2bshot_postgres_data`와 네트워크 `fu2bshot_default`를 이름으로 삭제(`down -v`·`prune` 금지).

## 알려진 한계
- 보기를 바꾸면 복구·보관 안내가 지워진다(의도). 그래서 `fu2b-s2-restored.png`는 보기를 바꾸지 않고 바로 찍었다.
- 버튼이 없는 행은 버튼이 있는 행보다 조금 낮다(표 행 높이가 버튼 높이에 따름, 보기 전용 결함).
- 촬영하지 않은 것: 503 다시 시도 창, 403 안내, 열려 있던 화면이 저장 때 DATASET_ARCHIVED를 받아 배너로 바뀌는 장면(vitest로 덮음).
