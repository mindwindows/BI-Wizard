# excel-import 실험 스크립트 (설계 실측용, 제품 코드 아님)

`docs/research/excel-import-design.md`(제안, 미승인)의 근거를 만든 스크립트다. 결과 상세는 `docs/research/results/excel-import-measurements.md`.
**제품 코드로 가져가지 않는다.** 필요한 로직은 기능 단위(FU)에서 테스트와 함께 새로 구현한다. 모든 데이터는 합성이다(실제 회사 엑셀 아님).

## 준비
```
python3.12 -m venv <임시폴더>/xl-venv            # 저장소 안에 만들지 않는다
<임시폴더>/xl-venv/bin/pip install -r requirements-experiment.txt   # 막히면 개발 환경에서만 PIP_CERT=/root/.ccr/ca-bundle.crt
# docker 측정용(이미지는 수정하지 않는다): 패키지를 폴더에 설치해 읽기 전용으로 마운트
<임시폴더>/xl-venv/bin/pip install --target <임시폴더>/site openpyxl==3.1.5 defusedxml==0.7.1 rapidfuzz==3.14.6 python-multipart==0.0.32
# upload_probe.py, db_insert_probe.py는 backend 의존성(fastapi, uvicorn, httpx, pg8000, SQLAlchemy)이 있는 별도 임시 venv가 필요하다
#   python3.12 -m venv <임시폴더>/bk-venv && <임시폴더>/bk-venv/bin/pip install -r backend/requirements.txt openpyxl==3.1.5 defusedxml==0.7.1 python-multipart==0.0.32
```

## 순서 (모두 `<임시폴더>`에서 실행, 저장소 파일을 쓰지 않는다)
| 단계 | 명령 | 하는 일 |
| --- | --- | --- |
| 1 | `python gen_samples.py <샘플폴더>` | 합성 xlsx 7종 생성(약 1분). 목표 4.9 MiB로 행 수를 보정 |
| 2 | `python gen_tamper.py <변조폴더>` | 폭탄·변조·위장 29종 생성(합계 약 20MB) |
| 3 | `python run_precheck.py <폴더> [상한MiB]` | `precheck.py` 사전 검사 결과 표 |
| 4 | `python bench.py host <샘플폴더> <결과.jsonl>` / `python bench.py docker <샘플폴더> <결과.jsonl> <site폴더>` | 열기·훑기·전치·검증 메모리·시간 행렬(각 3회, 약 15분씩). docker는 `bi-wizard-backend:local`을 `--memory=1g`로 실행 |
| 5 | `python summarize.py <결과.jsonl>` | 마크다운 요약 표 |
| 6 | `python bench_tamper.py <변조폴더> <결과.jsonl> <site폴더> [이름...]` | 사전 검사 없이 openpyxl만으로 열었을 때(docker 1g, 120초 timeout) |
| 7 | `python worker.py e2e_stream <샘플> keep=0\|1` | 2,000,000칸 스트리밍/전량 보관 메모리 비교 |
| 8 | `python upload_probe.py <작업폴더>` | 멀티파트 `UploadFile` vs 원본 본문 스트리밍, 본문 상한 미들웨어 |
| 9 | 임시 PostgreSQL 컨테이너 + `PROBE_PGPASSWORD=... python db_insert_probe.py 127.0.0.1 <포트> <사용자> <DB> [시험...]` | C4 방식 행마다 INSERT vs 배치 INSERT 시간 |
| 10 | `python values_probe.py <작업폴더>`, `python test_headers.py`, `python suggest_bench.py` | 셀 값 변환 탐침, 날짜 머리글 해석 46건, 열 이름 제안 비교 |

## 파일
| 파일 | 설명 |
| --- | --- |
| `gen_samples.py` | 정상 모양 합성 xlsx 생성기(xlsxwriter) |
| `gen_tamper.py` | 변조·폭탄 생성기. 해제 100~200MB 파일은 압축 후 0.1~0.5MB |
| `precheck.py` | zip 사전 검사 시제품(중앙 디렉터리·앞 4KB만 읽음) |
| `worker.py` / `bench.py` / `bench_tamper.py` / `summarize.py` | 측정 작업자·행렬 실행기·요약 |
| `headers.py` / `test_headers.py` / `suggest_bench.py` | 날짜 머리글 해석·열 이름 매핑 제안 시제품과 시험 |
| `values_probe.py` | 셀 종류별 openpyxl 반환값 탐침 |
| `upload_probe.py` / `db_insert_probe.py` | 업로드 수신·DB 적재 측정 |
| `run_precheck.py` | 폴더 전체 사전 검사 표 |

## 주의
- 파괴적 명령(`rm -rf` 등)은 쓰지 않는다. 임시 폴더·venv·시험 컨테이너는 **이름을 지정해** 정리한다(`docker rm -f <이름>`).
- 시험 PostgreSQL 비밀번호는 임시 값을 환경변수로만 넘긴다(저장소·로그에 남기지 않는다).
- 변조 파일은 서명이 없는 합성 파일이지만 파서에 부담을 주도록 만들었으므로 **호스트 직접 실행이 아니라 `--memory` 제한 컨테이너(`bench_tamper.py`)에서** 연다.
