# Gate ③ 실험 기록 보관 (docs/research)

Gate ③ 실험(X-1~X-29, A-22~A-27)의 상세 결과와 재현 스크립트다. 요약과 결정은 `docs/decisions/03c-gate3-experiment-results.md`와 `04~08`에 있다. 이 폴더는 구현 단계에서 근거를 다시 확인하거나 시험을 재현할 때 쓴다.

세션 컨테이너가 사라지면 `_workspace/`(git 제외)도 사라지므로, 이후 작업에 필요한 것만 여기로 옮겼다. 옮기지 않은 것(원문 사실 확인 `facts-*.md`, 라운드별 옵션 비교안 `round*-options.md`, 스크린샷·로그·큰 xlsx 샘플·Superset 소스 사본)은 결정이 03b·03c와 04~08에 반영돼 있어 보관하지 않았다. 다른 문서가 `_workspace/gate3/...` 경로를 가리키면 그것은 보관되지 않은 작업 파일이다.

## 결과 (results/)
| 파일 | 내용 | 필요한 때 |
| --- | --- | --- |
| `superset-r3-results.md` | 3라운드 Superset 시험(Gamma 권한, 서비스 계정, 필터 상태, X-18 같은 출처 iframe 등) | EW-3·EW-4, FU-1e |
| `superset-r4-results.md` | 4라운드 Superset 시험(guest 토큰 발급·검증 훅, `bi_guest` 최소 권한 이분 탐색, X-28) | EW-3·EW-4, FU-1e |
| `superset-a27-results.md` | A-27: 서비스 계정의 열 `verbose_name` 설정(`PUT /api/v1/dataset/{id}`의 `columns`는 교체) | FU-1d |
| `db-r4-results.md` | X-26 리터럴·`CREATE VIEW` 시험(CAST 일치율), X-29 권한·왕복 | FU-1b, 수식 엔진 |
| `import-r4-results.md` | 업로드·zip 사전 검사·nginx 한도 시험 | 가져오기 단위(EW-2) |

## 스크립트 (experiments/)
| 위치 | 용도 |
| --- | --- |
| `r3/` | Superset 3라운드 시험 스크립트(`setup_base.py`, `x20_*` 권한, `x22_*` 서비스 계정 흐름, `x23_*`) |
| `r4/db/` | X-26(`x26_*`), X-29(`x29_*`) 시험. `a.sh`, `dblib.py`는 공용 |
| `r4/` | guest 토큰(`gtok*.py`, `gs.py`), Superset 기반 설정(`setup_base.py`, `dc.sh`) |
| `r4/import/` | 업로드 시험 생성기·작업자(`scripts/`), `build_cases.py`(클립보드 사례 생성), `refparser.py` |
| `r4/alembic_scratch/` | 정적 표 revision 초안 실험(참고용, 실제 마이그레이션은 `backend/migrations/`) |
| `r5/` | 5라운드 Superset UI(Playwright `pw4_*.js`)와 서비스 계정 PUT 시험(`t1~t5`) |

## 사용상 주의
- 스크립트는 당시 임시 스택(컨테이너 이름, 포트, 임시 계정)을 가정한다. 그대로 실행되지 않을 수 있고, 비밀번호는 환경변수나 임시 env 파일로 넘긴다(저장소에 비밀값은 없다).
- 결과 문서의 수치는 합성 샘플 기준이다(`docs/samples/README.md`의 한계 참조). 실제 팀 데이터로 검증한 것이 아니다.
- 이 스크립트를 제품 코드로 가져오지 않는다. 필요한 로직은 FU에서 테스트와 함께 새로 구현한다.
