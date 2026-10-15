# 엑셀 가져오기 설계용 실측 결과 (상세)

**제안 문서의 부속 자료.** 요약과 해석은 `docs/research/excel-import-design.md`에 있다. 이 문서는 표와 원자료만 담는다.
작성일 2026-10-14, 기준 커밋 origin/main 49c5093. 모든 데이터는 합성(난수, seed 고정)이며 **실제 회사 엑셀로 검증하지 않았다.** 표지: [실측] = 이번 세션에서 직접 측정한 값.
스크립트와 실행 방법: `docs/research/experiments/excel-import/README.md`.

## 1. 측정 환경 [실측]
| 항목 | 값 |
| --- | --- |
| 호스트 | Intel Xeon 2.80GHz 4 vCPU, RAM 16GB, 스왑 없음, 커널 6.18.44, Docker 29.8.2. 측정 중 다른 컨테이너는 없었고 부하 평균은 측정 직전 0.3 정도였다 |
| 호스트 실행(host) | 임시 venv, Python 3.12.3 (expat 2.6.1) |
| 컨테이너 실행(docker) | 기존 이미지 `bi-wizard-backend:local`(Python 3.12.15, expat 2.8.5, 비루트)을 `--memory=1g --memory-swap=1g`(compose backend `mem_limit: 1g`와 같은 한도)로 실행. 패키지는 `pip install --target`으로 만든 폴더를 읽기 전용으로 마운트(**이미지는 수정하지 않음**) |
| 패키지 | openpyxl 3.1.5, et_xmlfile 2.0.0, defusedxml 0.7.1, RapidFuzz 3.14.6, python-multipart 0.0.32, xlsxwriter 3.2.9(샘플 생성용). lxml 없음(openpyxl은 표준 ElementTree 경로) |
| 측정 방법 | 작업자 프로세스 하나가 한 번 실행하고 JSON 한 줄을 출력(`worker.py`). 최대 RSS = `resource.getrusage(RUSAGE_SELF).ru_maxrss`. **증가분 = 최대 RSS − import 직후 RSS(host 25MB, docker 28MB)**. 각 항목 3회, 평균/최대. docker 시간에는 컨테이너 기동 시간을 넣지 않았다(작업자 내부 시간) |
| 범위 | 파일 열기·훑기·변환·검증. **DB 적재는 8절에서 따로** 쟀다. 네트워크 업로드는 9절 |

## 2. 시험 파일 (합성) [실측]
| 이름 | 모양 | 크기 | 비고 |
| --- | --- | --- | --- |
| `m_col_36` | 월 = 열: 제목 행(병합) + 머리글(진짜 날짜 셀 36개) + 항목 16,170행 + 20항목마다 소계 수식 행·빈 행 | 4.86 MiB | 빈 칸 4%, `-` 글자 1%, 수식 29,124칸(캐시 값 포함) |
| `m_col_12` | 같은 모양, 월 12개, 항목 42,507행 | 4.84 MiB | 수식 25,512칸 |
| `m_col_text` | 머리글이 글자 `1월`~`12월`, 연도는 시트 이름 `2026`에만 있음, 항목 42,487행 | 4.83 MiB | 연도 정보 위치 시험 |
| `table_12` | 이미 월 = 행인 긴 표 12열 53,073행 | 4.90 MiB | 전치 없는 경로의 기준 |
| `worst_cells_flat` | 100열 x 20,000행 = 2,000,100칸(0~1 정수) | 4.27 MiB | 셀 수 상한 근처. 0~99 난수로 만들면 7.57 MiB라 5MB 안에 2,000,000칸이 들어가지 않는다 |
| `worst_sst` | 100열, 서로 다른 5자 영숫자 646,500칸(공유 문자열 최대) | 4.90 MiB | 메모리·시간 최악 |

정상 샘플의 사전 검사(프로토타입 `precheck.py`, 업로드 상한 5 MiB) [실측]:

| 파일 | 크기 | 해제 합계 | 비율 | 판정 | 사유 코드 | 시간 |
| --- | --- | --- | --- | --- | --- | --- |
| m_col_12.xlsx | 4.84 MiB | 27.4 MiB | 5.7 | 통과 | - | 0.7 ms |
| m_col_36.xlsx | 4.86 MiB | 25.6 MiB | 5.3 | 통과 | - | 0.7 ms |
| m_col_text.xlsx | 4.83 MiB | 27.4 MiB | 5.7 | 통과 | - | 0.7 ms |
| table_12.xlsx | 4.90 MiB | 24.5 MiB | 5.0 | 통과 | - | 0.7 ms |
| worst_cells.xlsx | 7.569 MiB | - | - | 거부 | TOO_LARGE | 0.0 ms |
| worst_cells_flat.xlsx | 4.27 MiB | 50.4 MiB | 11.8 | 통과 | - | 0.6 ms |
| worst_sst.xlsx | 4.90 MiB | 35.6 MiB | 7.3 | 통과 | - | 0.7 ms |

`worst_cells.xlsx`(7.57 MiB)는 크기 상한에서 거부된다(`TOO_LARGE`). 저장소의 `docs/samples/`(openpyxl이 만든 4개)도 모두 통과했다.

## 3. 정상 파일 메모리·시간 (host, 임시 venv) [실측]
`open_ro` = read-only 열기만, `scan_ro` = 첫 시트 `iter_rows(values_only)` 전체 훑기(행 100,000·열 100·셀 2,000,000 상한 검사 포함), `open_normal` = 일반 모드(`read_only=False`)로 열기만, `scan_formula` = `data_only=False`로 훑으며 수식 셀 세기, `e2e_months` = 월 = 열 → 월 = 행 전치 + 셀 변환·검증(`item_cap=0` 항목 전부 보관, `100` 데이터셋 열 상한), `e2e_table` = 월 = 행 표를 행마다 검증해 목표 행 목록 생성. `defused=off`는 `OPENPYXL_DEFUSEDXML=False`.
셀 수는 **값이 있는 칸**으로 센다(`iter_rows(max_col=101)`는 각 행을 101칸으로 채워 돌려주므로 길이로 세면 셀 수가 부풀려진다).

| 파일 | 모드 | 인수 | 비고 | 횟수 | 시간 평균/최대(s) | 최대 RSS 평균/최대(MB) | 증가분 평균(MB) | 결과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m_col_36.xlsx | baseline |  |  | 1 | 0.00 / 0.00 | 25.1 / 25.1 | 0.0 | ok  |
| m_col_36.xlsx | precheck |  |  | 3 | 0.00 / 0.00 | 25.3 / 25.4 | 0.2 | ok  |
| m_col_36.xlsx | open_ro |  |  | 3 | 0.20 / 0.22 | 28.8 / 28.8 | 3.7 | ok  |
| m_col_36.xlsx | scan_ro |  |  | 3 | 5.15 / 5.24 | 29.1 / 29.2 | 4.0 | ok rows=17790 cells=637430 stop=끝까지 |
| m_col_36.xlsx | scan_ro |  | defused=off | 3 | 3.61 / 3.66 | 29.2 / 29.3 | 4.0 | ok rows=17790 cells=637430 stop=끝까지 |
| m_col_36.xlsx | open_normal |  |  | 3 | 8.37 / 8.55 | 272.2 / 272.2 | 247.0 | ok  |
| m_col_36.xlsx | scan_formula |  |  | 3 | 5.54 / 5.61 | 29.2 / 29.2 | 4.0 | ok formula_cells=29124 |
| m_col_36.xlsx | e2e_months | item_cap=0 |  | 3 | 6.97 / 7.10 | 114.5 / 114.5 | 89.3 | ok items=16170 periods=36 errors_total=0 out_cells=582120 |
| m_col_36.xlsx | e2e_months | item_cap=0 | defused=off | 3 | 5.72 / 6.00 | 114.5 / 114.5 | 89.3 | ok items=16170 periods=36 errors_total=0 out_cells=582120 |
| m_col_36.xlsx | e2e_months | item_cap=100 |  | 3 | 4.90 / 5.19 | 29.8 / 29.9 | 4.7 | ok items=100 periods=36 errors_total=0 out_cells=3600 |
| m_col_12.xlsx | open_ro |  |  | 3 | 0.58 / 0.71 | 33.9 / 33.9 | 8.8 | ok  |
| m_col_12.xlsx | scan_ro |  |  | 3 | 6.21 / 6.41 | 34.4 / 34.5 | 9.3 | ok rows=46761 cells=644966 stop=끝까지 |
| m_col_12.xlsx | open_normal |  |  | 3 | 9.57 / 9.98 | 279.4 / 279.5 | 254.2 | ok  |
| m_col_12.xlsx | scan_formula |  |  | 3 | 6.34 / 6.67 | 34.4 / 34.5 | 9.3 | ok formula_cells=25512 |
| m_col_12.xlsx | e2e_months | item_cap=0 |  | 3 | 8.06 / 8.46 | 123.3 / 123.4 | 98.2 | ok items=42507 periods=12 errors_total=0 out_cells=510084 |
| m_col_12.xlsx | e2e_months | item_cap=100 |  | 3 | 5.55 / 5.71 | 34.8 / 34.8 | 9.6 | ok items=100 periods=12 errors_total=0 out_cells=1200 |
| m_col_text.xlsx | e2e_months | item_cap=100 |  | 3 | 5.76 / 5.80 | 34.8 / 34.9 | 9.8 | ok items=100 periods=12 errors_total=0 out_cells=1200 |
| m_col_text.xlsx | e2e_months | item_cap=0 |  | 3 | 7.74 / 8.24 | 123.1 / 123.2 | 98.1 | ok items=42487 periods=12 errors_total=0 out_cells=509844 |
| table_12.xlsx | open_ro |  |  | 3 | 0.62 / 0.64 | 35.7 / 35.8 | 10.5 | ok  |
| table_12.xlsx | scan_ro |  |  | 3 | 5.86 / 5.94 | 36.1 / 36.1 | 11.0 | ok rows=53074 cells=636888 stop=끝까지 |
| table_12.xlsx | open_normal |  |  | 3 | 9.29 / 9.52 | 279.9 / 280.2 | 254.8 | ok  |
| table_12.xlsx | e2e_table |  |  | 3 | 8.34 / 8.75 | 133.8 / 133.9 | 108.7 | ok rows=53073 errors_total=0 |
| worst_cells_flat.xlsx | open_ro |  |  | 3 | 0.01 / 0.01 | 25.8 / 25.8 | 0.7 | ok  |
| worst_cells_flat.xlsx | scan_ro |  |  | 3 | 14.04 / 14.48 | 27.7 / 27.8 | 2.6 | ok rows=20001 cells=2000100 stop=셀 상한 초과 |
| worst_cells_flat.xlsx | open_normal |  |  | 3 | 24.03 / 24.60 | 753.6 / 753.7 | 728.5 | ok  |
| worst_sst.xlsx | open_ro |  |  | 3 | 8.02 / 8.17 | 114.8 / 114.8 | 89.6 | ok  |
| worst_sst.xlsx | scan_ro |  |  | 3 | 13.00 / 13.22 | 114.8 / 114.9 | 89.7 | ok rows=6465 cells=646500 stop=끝까지 |
| worst_sst.xlsx | scan_ro |  | defused=off | 3 | 9.69 / 9.84 | 114.8 / 114.9 | 89.7 | ok rows=6465 cells=646500 stop=끝까지 |
| worst_sst.xlsx | open_normal |  |  | 3 | 15.80 / 16.10 | 298.2 / 298.2 | 273.1 | ok  |

## 4. 정상 파일 메모리·시간 (docker, `--memory=1g`) [실측]
같은 항목을 backend 이미지와 같은 한도의 컨테이너(Python 3.12.15)에서 쟀다. OOM kill은 없었다.

| 파일 | 모드 | 인수 | 비고 | 횟수 | 시간 평균/최대(s) | 최대 RSS 평균/최대(MB) | 증가분 평균(MB) | 결과 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| m_col_36.xlsx | baseline |  |  | 1 | 0.00 / 0.00 | 28.4 / 28.4 | 0.0 | ok  |
| m_col_36.xlsx | precheck |  |  | 3 | 0.00 / 0.01 | 28.3 / 28.4 | 0.0 | ok  |
| m_col_36.xlsx | open_ro |  |  | 3 | 0.21 / 0.23 | 31.1 / 31.2 | 2.6 | ok  |
| m_col_36.xlsx | scan_ro |  |  | 3 | 5.71 / 5.75 | 31.4 / 31.5 | 2.9 | ok rows=17790 cells=637430 stop=끝까지 |
| m_col_36.xlsx | scan_ro |  | defused=off | 3 | 4.12 / 4.30 | 31.2 / 31.7 | 1.7 | ok rows=17790 cells=637430 stop=끝까지 |
| m_col_36.xlsx | open_normal |  |  | 3 | 9.01 / 9.14 | 274.3 / 274.5 | 246.0 | ok  |
| m_col_36.xlsx | scan_formula |  |  | 3 | 6.07 / 6.11 | 31.4 / 31.6 | 3.0 | ok formula_cells=29124 |
| m_col_36.xlsx | e2e_months | item_cap=0 |  | 3 | 8.07 / 8.31 | 114.9 / 115.2 | 87.0 | ok items=16170 periods=36 errors_total=0 out_cells=582120 |
| m_col_36.xlsx | e2e_months | item_cap=0 | defused=off | 3 | 6.17 / 6.25 | 115.1 / 115.2 | 85.5 | ok items=16170 periods=36 errors_total=0 out_cells=582120 |
| m_col_36.xlsx | e2e_months | item_cap=100 |  | 3 | 5.34 / 5.57 | 31.4 / 31.5 | 3.5 | ok items=100 periods=36 errors_total=0 out_cells=3600 |
| m_col_12.xlsx | open_ro |  |  | 3 | 0.56 / 0.59 | 36.0 / 36.2 | 7.4 | ok  |
| m_col_12.xlsx | scan_ro |  |  | 3 | 6.68 / 6.94 | 36.5 / 36.9 | 7.8 | ok rows=46761 cells=644966 stop=끝까지 |
| m_col_12.xlsx | open_normal |  |  | 3 | 10.02 / 10.11 | 281.6 / 281.8 | 253.3 | ok  |
| m_col_12.xlsx | scan_formula |  |  | 3 | 7.34 / 7.54 | 36.6 / 36.7 | 8.1 | ok formula_cells=25512 |
| m_col_12.xlsx | e2e_months | item_cap=0 |  | 3 | 8.74 / 8.87 | 123.8 / 123.9 | 95.9 | ok items=42507 periods=12 errors_total=0 out_cells=510084 |
| m_col_12.xlsx | e2e_months | item_cap=100 |  | 3 | 6.33 / 6.48 | 36.5 / 36.7 | 8.7 | ok items=100 periods=12 errors_total=0 out_cells=1200 |
| m_col_text.xlsx | e2e_months | item_cap=100 |  | 3 | 6.38 / 6.63 | 36.6 / 36.7 | 8.7 | ok items=100 periods=12 errors_total=0 out_cells=1200 |
| m_col_text.xlsx | e2e_months | item_cap=0 |  | 3 | 8.70 / 8.97 | 123.7 / 123.8 | 95.7 | ok items=42487 periods=12 errors_total=0 out_cells=509844 |
| table_12.xlsx | open_ro |  |  | 3 | 0.73 / 0.86 | 37.9 / 38.3 | 9.3 | ok  |
| table_12.xlsx | scan_ro |  |  | 3 | 6.52 / 6.68 | 38.1 / 38.4 | 9.6 | ok rows=53074 cells=636888 stop=끝까지 |
| table_12.xlsx | open_normal |  |  | 3 | 10.15 / 10.46 | 282.3 / 282.4 | 253.7 | ok  |
| table_12.xlsx | e2e_table |  |  | 3 | 9.14 / 9.30 | 134.2 / 134.3 | 105.8 | ok rows=53073 errors_total=0 |
| worst_cells_flat.xlsx | open_ro |  |  | 3 | 0.01 / 0.01 | 28.6 / 28.7 | 0.0 | ok  |
| worst_cells_flat.xlsx | scan_ro |  |  | 3 | 15.45 / 15.50 | 30.1 / 30.2 | 1.5 | ok rows=20001 cells=2000100 stop=셀 상한 초과 |
| worst_cells_flat.xlsx | open_normal |  |  | 3 | 25.99 / 26.80 | 755.2 / 755.4 | 727.2 | ok  |
| worst_sst.xlsx | open_ro |  |  | 3 | 8.82 / 9.10 | 117.3 / 117.4 | 88.8 | ok  |
| worst_sst.xlsx | scan_ro |  |  | 3 | 13.92 / 14.25 | 117.3 / 117.4 | 88.7 | ok rows=6465 cells=646500 stop=끝까지 |
| worst_sst.xlsx | scan_ro |  | defused=off | 3 | 11.02 / 11.12 | 117.5 / 117.8 | 88.1 | ok rows=6465 cells=646500 stop=끝까지 |
| worst_sst.xlsx | open_normal |  |  | 3 | 17.06 / 17.52 | 300.1 / 300.3 | 271.6 | ok  |

추가 실측(docker, 3회 평균): `e2e_stream`은 모든 칸을 숫자로 변환·검증하는 최악 시나리오다. `worst_cells_flat`(2,000,000칸) 스트리밍(1,000행 배치 뒤 버림) 약 19.5초·최대 RSS 40MB(증가 12MB), **전량 보관 약 18.7초·최대 RSS 260MB(증가 232MB, 칸당 약 116바이트)**, `m_col_12` 스트리밍 약 9.2초·37MB.

## 5. 사전 검사 vs 변조 파일 [실측]
변조 파일은 `gen_tamper.py`가 만든 합성 파일이다(해제 크기 100~200MB 폭탄 5종, 한도 안쪽 큰 시트 1종, 선언 크기 속임, 중첩 zip, 항목 2만 개, 시트 5천 개 선언, XML 공격 4종, 형식 위장·매크로·외부 링크(DDE 모양)·삽입 개체·경로 이름·암호화 비트·bzip2·중복 이름).

사전 검사 결과(업로드 상한 5 MiB, 해제 합계 상한 75 MiB, 압축률 50, 항목 100 MiB, 항목 수 1,000, 시트 30, 범위 정보 없는 시트 20 MiB). **시간은 3회 중 최소.**

| 파일 | 크기 | 해제 합계 | 비율 | 판정 | 사유 코드 | 시간 |
| --- | --- | --- | --- | --- | --- | --- |
| backslash_names.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | BAD_NAMES | 0.7 ms |
| billion_laughs_sheet.xlsx | 0.01 MiB | 0.0 MiB | 3.5 | 거부 | DTD | 0.4 ms |
| bomb_celltext_100mb.xlsx | 0.10 MiB | 100.0 MiB | 982.0 | 거부 | UNC_TOTAL,RATIO,ENTRY_UNC,NO_DIMENSION_BIG | 0.4 ms |
| bomb_rows_200mb.xlsx | 0.49 MiB | 200.0 MiB | 408.4 | 거부 | UNC_TOTAL,RATIO,ENTRY_UNC,NO_DIMENSION_BIG | 0.4 ms |
| bomb_sst_many_100mb.xlsx | 0.25 MiB | 100.0 MiB | 394.8 | 거부 | UNC_TOTAL,RATIO,ENTRY_UNC | 0.6 ms |
| bomb_sst_one_100mb.xlsx | 0.11 MiB | 100.0 MiB | 925.8 | 거부 | UNC_TOTAL,RATIO,ENTRY_UNC | 0.6 ms |
| bomb_whitespace_150mb.xlsx | 0.15 MiB | 150.0 MiB | 997.4 | 거부 | UNC_TOTAL,RATIO,ENTRY_UNC,NO_DIMENSION_BIG | 0.5 ms |
| bzip2_entry.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | COMPRESSION | 0.7 ms |
| declared_size_lie.xlsx | 0.25 MiB | 0.0 MiB | 0.1 | 거부 | BAD_ENTRY | 0.4 ms |
| dtd_in_content_types.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | DTD | 0.4 ms |
| dtd_in_sst.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | DTD | 0.5 ms |
| duplicate_names.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | DUP_NAMES | 0.7 ms |
| embedded_ole_object.xlsx | 0.01 MiB | 0.1 MiB | 4.2 | 거부 | EMBEDDED | 0.7 ms |
| empty_file.xlsx | 0.000 MiB | - | - | 거부 | EMPTY_FILE | 0.0 ms |
| encrypted_flag_entry.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | ENCRYPTED_ENTRY,BAD_ENTRY | 0.5 ms |
| external_link_dde.xlsx | 0.01 MiB | 0.1 MiB | 4.3 | 거부 | EXTERNAL_LINK | 0.7 ms |
| gentle_inside_limit.xlsx | 3.38 MiB | 69.6 MiB | 20.6 | 거부 | NO_DIMENSION_BIG | 0.4 ms |
| many_entries_20000.xlsx | 2.280 MiB | - | - | 거부 | TOO_MANY_ENTRIES | 94.1 ms |
| nested_zip.xlsx | 0.01 MiB | 0.1 MiB | 12.4 | 거부 | EMBEDDED,NESTED_ZIP | 1.2 ms |
| ole2_encrypted_like.xlsx | 0.004 MiB | - | - | 거부 | OLE2 | 0.0 ms |
| path_traversal_names.xlsx | 0.01 MiB | 0.0 MiB | 4.3 | 거부 | BAD_NAMES | 0.6 ms |
| png_renamed.xlsx | 0.003 MiB | - | - | 거부 | NOT_ZIP | 0.0 ms |
| sheets_declared_5000.xlsx | 0.04 MiB | 0.3 MiB | 7.9 | 거부 | TOO_MANY_SHEETS | 18.6 ms |
| text_renamed.xlsx | 0.000 MiB | - | - | 거부 | NOT_ZIP | 0.0 ms |
| truncated_zip.xlsx | 0.006 MiB | - | - | 거부 | BAD_ZIP | 0.1 ms |
| xlsb_like.xlsx | 0.01 MiB | 0.1 MiB | 4.3 | 거부 | XLSB | 1.1 ms |
| xlsm_macro.xlsx | 0.01 MiB | 0.1 MiB | 4.2 | 거부 | MACRO,MACRO_TYPE,NOT_XLSX | 0.7 ms |
| xxe_external_entity_sheet.xlsx | 0.01 MiB | 0.0 MiB | 3.4 | 거부 | DTD | 0.4 ms |
| zip_not_xlsx.xlsx | 0.00 MiB | 0.0 MiB | 1.0 | 거부 | NOT_XLSX | 0.1 ms |

사전 검사를 **건너뛰고** openpyxl만으로 열었을 때(docker `--memory=1g`, 120초 timeout, 시트 훑기 `scan_ro`). 프로세스가 "정상 종료"라는 것은 공격이 성공했다는 뜻이 아니라 예외 또는 정상 완료를 뜻한다.

| 파일 | defusedxml | 결과 | 시간(s) | 최대 RSS(MB) | openpyxl 반응 |
| --- | --- | --- | --- | --- | --- |
| backslash_names | 사용 | 정상 종료 | 1.3 | 28.4 | ok |
| billion_laughs_sheet | 끔 | 정상 종료 | 1.2 | 74.9 | ParseError: limit on input amplification factor (from DTD and entities) breached: line 2,  |
| billion_laughs_sheet | 사용 | 정상 종료 | 1.1 | 28.5 | ValueError: Unable to read workbook: could not read worksheets from /samples/billion_laugh |
| bomb_celltext_100mb | 사용 | 정상 종료 | 2.4 | 227.9 | ok |
| bomb_rows_200mb | 사용 | 정상 종료 | 63.7 | 588.9 | ok |
| bomb_sst_many_100mb | 사용 | 정상 종료 | 89.2 | 595.1 | ok |
| bomb_sst_one_100mb | 사용 | 정상 종료 | 1.9 | 228.1 | IndexError: list index out of range |
| bomb_whitespace_150mb | 사용 | 정상 종료 | 2.8 | 330.9 | ok |
| bzip2_entry | 사용 | 정상 종료 | 1.0 | 28.5 | ok |
| declared_size_lie | 사용 | 정상 종료 | 1.0 | 28.6 | BadZipFile: Bad CRC-32 for file 'xl/worksheets/sheet1.xml' |
| dtd_in_content_types | 끔 | 정상 종료 | 1.1 | 29.5 | ok |
| dtd_in_content_types | 사용 | 정상 종료 | 1.0 | 28.7 | ValueError: Unable to read workbook: could not read manifest from /samples/dtd_in_content_ |
| dtd_in_sst | 끔 | 정상 종료 | 1.0 | 29.6 | IndexError: list index out of range |
| dtd_in_sst | 사용 | 정상 종료 | 1.1 | 28.7 | ValueError: Unable to read workbook: could not read strings from /samples/dtd_in_sst.xlsx. |
| duplicate_names | 사용 | 정상 종료 | 1.1 | 28.6 | ok |
| embedded_ole_object | 사용 | 정상 종료 | 1.0 | 28.8 | ok |
| empty_file | 사용 | 정상 종료 | 1.0 | 28.6 | BadZipFile: File is not a zip file |
| encrypted_flag_entry | 사용 | 정상 종료 | 1.0 | 28.5 | RuntimeError: File 'xl/styles.xml' is encrypted, password required for extraction |
| external_link_dde | 사용 | 정상 종료 | 1.0 | 28.7 | ok |
| gentle_inside_limit | 사용 | 정상 종료 | 26.7 | 266.2 | ok |
| many_entries_20000 | 사용 | 정상 종료 | 1.3 | 38.9 | ok |
| nested_zip | 사용 | 정상 종료 | 1.1 | 28.6 | ok |
| ole2_encrypted_like | 사용 | 정상 종료 | 1.1 | 28.5 | BadZipFile: File is not a zip file |
| path_traversal_names | 사용 | 정상 종료 | 1.0 | 28.8 | ok |
| png_renamed | 사용 | 정상 종료 | 1.1 | 28.3 | BadZipFile: File is not a zip file |
| sheets_declared_5000 | 사용 | 정상 종료 | 18.3 | 35.2 | ok |
| text_renamed | 사용 | 정상 종료 | 1.1 | 28.5 | BadZipFile: File is not a zip file |
| truncated_zip | 사용 | 정상 종료 | 1.1 | 28.8 | BadZipFile: File is not a zip file |
| xlsb_like | 사용 | 정상 종료 | 1.0 | 28.5 | ok |
| xlsm_macro | 사용 | 정상 종료 | 1.2 | 28.6 | OSError: File contains no valid workbook part |
| xxe_external_entity_sheet | 끔 | 정상 종료 | 1.0 | 29.6 | ParseError: undefined entity &xxe;: line 2, column 188 |
| xxe_external_entity_sheet | 사용 | 정상 종료 | 1.1 | 28.6 | ValueError: Unable to read workbook: could not read worksheets from /samples/xxe_external_ |
| zip_not_xlsx | 사용 | 정상 종료 | 0.9 | 28.7 | KeyError: "There is no item named '[Content_Types].xml' in the archive" |

- 이번에 만든 가장 큰 폭탄(해제 200MB)은 1g 한도에서 OOM kill이 나지 않았으나(RSS 589MB) **63.7초**가 걸렸고, 짧은 공유 문자열 100MB는 **89.2초**·595MB였다. 03c X-27의 더 큰 폭탄(300MB 이상)에서는 OOM kill이 관찰됐다(이번 세션에서는 재현하지 않음).
- 사전 검사를 통과하는 가장 큰 모양(`gentle_inside_limit`, 해제 70MB·압축률 20.6)은 `<dimension>`이 없어 **26.7초·266MB**였다. 그래서 사전 검사에 "범위 정보(`<dimension>`)가 앞 4KB에 없는 시트는 해제 20MB 초과 시 거부" 규칙을 더했고, 이 파일은 `NO_DIMENSION_BIG`로 거부된다(위 사전 검사 표).
- `declared_size_lie`: 선언 크기만 속인 파일은 `zipfile`이 `BadZipFile: Bad CRC-32`로 끝내 메모리가 늘지 않았다(28.6MB).
- XML 공격: defusedxml 사용 시 4건 모두 거부(`ValueError: Unable to read workbook` 또는 `could not read manifest`), 끄면 이 이미지의 expat 2.8.5는 billion laughs를 `limit on input amplification factor`로, 외부 엔티티를 `undefined entity`로 거부하고 `file:///etc/hostname` 내용은 유출되지 않았다. 내부 엔티티 선언만 있는 `dtd_in_content_types`는 defusedxml을 끄면 **정상으로 열린다**(DTD 자체는 막지 않음).
- openpyxl이 스스로 거부하는 것: `.xlsm`(`OSError: File contains no valid workbook part`), 암호화 비트(`RuntimeError: ... password required`), 비 zip(`BadZipFile`), xlsx 아닌 zip(`KeyError`, 감싸야 함). **스스로 거부하지 않는 것**: 외부 링크·DDE 모양 연결·삽입 개체·중첩 zip·`../` 경로 이름·bzip2 항목·중복 항목·`.xlsb` 모양(모두 정상으로 열림) → 사전 검사가 필요하다.

## 6. 업로드 수신 방식 비교 (uvicorn 서버 프로세스의 VmHWM) [실측]
`upload_probe.py`, 임시 venv(fastapi/starlette 1.7.0, python-multipart 0.0.32). 서버를 시나리오마다 새로 띄움.

| 시나리오 | 응답 | 본문 | 소요 | 서버 RSS |
| --- | --- | --- | --- | --- |
| up_5mb (멀티파트 UploadFile) | 200 | {"size":5138022,"rolled_to_disk":true,"name":"x.xlsx"} | 0.11 s | 시작 45.8 -> 최대 51.9 MB (증가 6.1) |
| raw_5mb (octet-stream, 스트리밍 BytesIO) | 200 | {"size":5138022} | 0.08 s | 시작 45.8 -> 최대 51.7 MB (증가 5.9) |
| raw_7mb_cl (7MiB, Content-Length 있음 -> 읽기 전에 거부) | 413 | {"code":"PAYLOAD_TOO_LARGE"} | 0.09 s | 시작 45.9 -> 최대 47.0 MB (증가 1.1) |
| raw_chunked (64MiB, 길이 모름) | 413 | {"code":"PAYLOAD_TOO_LARGE","read":6388889} | 0.15 s | 시작 45.9 -> 최대 53.0 MB (증가 7.1) |
| up_64mb (멀티파트 64MiB, 앱 상한 없음) | 200 | {"size":67108864,"rolled_to_disk":true,"name":"x.xlsx"} | 0.70 s | 시작 45.9 -> 최대 111.3 MB (증가 65.4) |
| up_64mb + RequestBodyLimitMiddleware(6MiB) | 413 | Content Too Large | 0.46 s | 시작 45.9 -> 최대 47.1 MB (증가 1.2) |
| up_5mb + RequestBodyLimitMiddleware(6MiB) | 200 | {"size":5138022,"rolled_to_disk":true,"name":"x.xlsx"} | 0.09 s | 시작 45.8 -> 최대 51.9 MB (증가 6.1) |

- 멀티파트 `UploadFile`은 1MiB를 넘으면 `SpooledTemporaryFile`이 **디스크(TMPDIR)로 넘어간다**(`rolled_to_disk: true`, Starlette 1.7.0 `spool_max_size = 1MiB`). 앱에 상한 검사가 없으면 64MiB도 그대로 받는다(대조). 프록시가 상한을 막아야 하고 앱은 읽기 전에 `Content-Length`를 확인해야 한다.
- Starlette 1.7.0 내장 `RequestBodyLimitMiddleware(max_body_size=상한 + 1MiB)`는 멀티파트 64MiB를 중간에 끊고 413을 돌려줬다(서버 RSS 증가 1.2MB, 응답 본문은 JSON이 아니라 평문 `Content Too Large`라 05 오류 형식에 맞추려면 감싸야 한다). 5MiB 정상 파일은 통과했다.
- 원본 본문(octet-stream)을 `request.stream()`으로 읽으며 세는 방식은 디스크를 쓰지 않고, 길이를 모르는 청크 전송도 상한 + 1MiB(여유)에서 중단했다(읽은 바이트 6,388,889).

## 7. 값 변환 탐침 (openpyxl 3.1.5 read-only) [실측]
`values_probe.py`. 같은 셀을 `data_only=True`/`False`로 읽은 결과다. 열 `타입`: n 숫자, s 글자, b 불리언, d 날짜, f 수식, e 오류값.

| 셀 | 설명 | data_only=True (타입, 값) | data_only=False (타입, 값) |
| --- | --- | --- | --- |
| A1 | 정수 5 | n 5 | n 5 |
| C1 | 병합 셀의 왼쪽 위 | s '병합 셀(C1:D2)' | s '병합 셀(C1:D2)' |
| F1 | 숨긴 열의 값(열 숨김) | s '숨긴 열의 값' | s '숨긴 열의 값' |
| G1 | 서식 있는 글자(rich text) | s '굵게보통' | s '굵게보통' |
| A2 | 소수 1.1 | n 1.1 | n 1.1 |
| D2 | 병합 셀의 나머지(값 없음) | n None | n None |
| A3 | 0.1+0.2 부동소수 잡음(파일에 17자리로 기록) | n 0.3 | n 0.3 |
| A4 | 큰 정수 123456789012345678 (double로 저장됨) | n 1.234567890123457e+17 | n 1.234567890123457e+17 |
| A5 | 숫자처럼 보이는 글자 '00012' | s '00012' | s '00012' |
| A6 | 글자 '1,234.50' (쉼표) | s '1,234.50' | s '1,234.50' |
| A7 | 글자 '-' (없음 표기) | s '-' | s '-' |
| A8 | 빈 글자 '' | s '' | s '' |
| A9 | 공백 글자 '  ' | s '  ' | s '  ' |
| A10 | 불리언 TRUE | b True | b True |
| A11 | 날짜 2026-03-01 | d datetime.datetime(2026, 3, 1, 0, 0) | d datetime.datetime(2026, 3, 1, 0, 0) |
| A12 | 일시 2026-03-01 13:45 | d datetime.datetime(2026, 3, 1, 13, 45) | d datetime.datetime(2026, 3, 1, 13, 45) |
| A13 | 시간만 13:45 | d datetime.time(13, 45) | d datetime.time(13, 45) |
| A14 | 퍼센트 7.5% (값 0.075) | n 0.075 | n 0.075 |
| A15 | 수식 =1+1 (캐시 2) | n 2 | f '=1+1' |
| A16 | 수식 문자열 결과 (캐시 'ab') | s 'ab' | f '="a"&"b"' |
| A17 | 수식 오류 결과 (캐시 #DIV/0!) | e '#DIV/0!' | f '=1/0' |
| A18 | 수식 불리언 결과 (캐시 TRUE) | b True | f '=1=1' |
| A19 | 글자가 '=1+1'로 시작(수식 아님, 글자) | s '=1+1' | s '=1+1' |
| A20 | 글자 "=cmd|' /C calc'!A0" (DDE 모양, 글자) | s "=cmd|' /C calc'!A0" | s "=cmd|' /C calc'!A0" |
| A21 | 글자 '+1+1' | s '+1+1' | s '+1+1' |
| A22 | 글자 '@SUM(1,1)' | s '@SUM(1,1)' | s '@SUM(1,1)' |
| A23 | 글자 '-2+3' | s '-2+3' | s '-2+3' |
| A24 | 글자에 제어문자 'a\x01b' | s 'a_x0001_b' | s 'a_x0001_b' |
| A25 | NFD 한글 '가' (ㄱ+ㅏ) | s '가' | s '가' |
| A26 | 아주 긴 글자 40,000자(엑셀 셀 상한 32,767자 초과 -> 잘림) | s '가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가... | s '가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가가... |
| A27 | 수식 셀(캐시 없음 모양 흉내, 값 0) | n 0 | f '=SUM(A1:A2)' |
| A30 | 숨긴 행의 값(행 숨김) | s '숨긴 행의 값' | s '숨긴 행의 값' |

openpyxl이 저장한 수식 파일(캐시 없음) A3: data_only=True -> ('n', None), data_only=False -> ('f', '=A1+A2')
1904 날짜 체계 파일 A1 (2026-03-01로 기록): data_only=True -> ('d', datetime.datetime(2026, 3, 1, 0, 0))

openpyxl 3.1.5, 실행 Python 3.12.3

## 8. DB 적재 시간 (PostgreSQL 16.10, tmpfs, pg8000 1.31.5, SQLAlchemy 2.1.4) [실측]
임시 컨테이너 `postgres:16.10-bookworm`(데이터 tmpfs, 호스트 포트 매핑 `127.0.0.1`, 측정 뒤 이름을 지정해 제거). 표는 동적 표와 같은 모양(identity PK, 기준 날짜 열 NOT NULL + UNIQUE, `numeric` 열 11개 또는 99개). 스크립트 `db_insert_probe.py`. **호스트 포트 매핑 경유라 지연이 compose 내부 네트워크와 다를 수 있다.**

| 항목 | 시간 | 비고 |
| --- | --- | --- |
| 행마다 `INSERT ... ON CONFLICT DO NOTHING RETURNING`(현재 C4 `repo.insert_row` 방식), 5,000행 x 12열 | 8.16 s | 행당 1.6ms |
| 같은 방식 20,000행 x 12열 | 32.85 s | 100,000행이면 약 165초(선형 외삽) |
| 배치 1,000행씩 `executemany` + `RETURNING`(insertmanyvalues), 5,000행 x 12열 | 0.62~0.97 s | |
| 같은 방식 20,000행 x 12열 | 2.36~2.41 s | |
| 같은 방식 100,000행 x 12열 | 11.33 s | |
| 같은 방식 20,000행 x 100열 | 18.19 s | 셀 2,000,000칸에 해당 |
| 배치 `executemany`, **RETURNING 없음**, 100,000행 x 12열 | 86.52 s | pg8000이 행마다 왕복 → **RETURNING을 붙여야 빠르다** |
| 같은 방식 20,000행 x 100열 | 45.92 s | |
| 기간 5,000개의 충돌을 `IN`으로 미리 조회(기존 5만 행 표) | 0.11 s | 충돌 1,000건 찾음 |

## 9. 검사 규칙·보조 시제품 시험 [실측]
날짜 머리글 해석 사례표(`test_headers.py`, 46건):

| # | 설명 | 입력 | 결과 | 기대 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 1 | 진짜 날짜 셀 | `2026-01-01T00:00:00` | 2026-01-01 | 2026-01-01 | OK |
| 2 | 진짜 날짜 셀(월 중간 -> 첫날로) | `2026-03-17T00:00:00` | 2026-03-01 | 2026-03-01 | OK |
| 3 | 진짜 날짜 셀, 연 단위 | `2026-05-01T00:00:00` | 2026-01-01 | 2026-01-01 | OK |
| 4 | 엑셀 일련번호 46023(=2026-01-01) | `46023` | 2026-01-01 | 2026-01-01 | OK |
| 5 | 숫자 3 + 연도 힌트 | `3` | 2026-03-01 | 2026-03-01 | OK |
| 6 | 숫자 3, 연도 힌트 없음 | `3` | NEEDS_YEAR | NEEDS_YEAR | OK |
| 7 | 숫자 2026, 연 단위 | `2026` | 2026-01-01 | 2026-01-01 | OK |
| 8 | 소수 3.5 | `3.5` | BAD_FORMAT | BAD_FORMAT | OK |
| 9 | 1월 + 연도 힌트 | `'1월'` | 2026-01-01 | 2026-01-01 | OK |
| 10 | 12월 + 공백 | `' 12 월 '` | 2026-12-01 | 2026-12-01 | OK |
| 11 | 1월, 힌트 없음 | `'1월'` | NEEDS_YEAR | NEEDS_YEAR | OK |
| 12 | 13월 | `'13월'` | BAD_FORMAT | BAD_FORMAT | OK |
| 13 | 2026년 1월 | `'2026년 1월'` | 2026-01-01 | 2026-01-01 | OK |
| 14 | 2026년1월 | `'2026년1월'` | 2026-01-01 | 2026-01-01 | OK |
| 15 | 26년 3월 | `'26년 3월'` | 2026-03-01 | 2026-03-01 | OK |
| 16 | 2026-01 | `'2026-01'` | 2026-01-01 | 2026-01-01 | OK |
| 17 | 2026.01 | `'2026.01'` | 2026-01-01 | 2026-01-01 | OK |
| 18 | 2026/1 | `'2026/1'` | 2026-01-01 | 2026-01-01 | OK |
| 19 | 2026-01-15 (월 단위) | `'2026-01-15'` | 2026-01-01 | 2026-01-01 | OK |
| 20 | 2026-01 (일 단위) | `'2026-01'` | UNIT_MISMATCH | UNIT_MISMATCH | OK |
| 21 | 01/2026 | `'01/2026'` | 2026-01-01 | 2026-01-01 | OK |
| 22 | Jan-26 | `'Jan-26'` | 2026-01-01 | 2026-01-01 | OK |
| 23 | Jan 2026 | `'Jan 2026'` | 2026-01-01 | 2026-01-01 | OK |
| 24 | January 2026 | `'January 2026'` | 2026-01-01 | 2026-01-01 | OK |
| 25 | Sept-2026 (Sep로 인식) | `'Sept-2026'` | 2026-09-01 | 2026-09-01 | OK |
| 26 | Jan + 힌트 | `'Jan'` | 2026-01-01 | 2026-01-01 | OK |
| 27 | Foo-26 | `'Foo-26'` | BAD_FORMAT | BAD_FORMAT | OK |
| 28 | 26.1 (연월/월일 구분 불가) | `'26.1'` | AMBIGUOUS | AMBIGUOUS | OK |
| 29 | 1/26 | `'1/26'` | AMBIGUOUS | AMBIGUOUS | OK |
| 30 | 괄호 주석 1월(잠정) | `'1월(잠정)'` | 2026-01-01 | 2026-01-01 | OK |
| 31 | 2026년 (연 단위) | `'2026년'` | 2026-01-01 | 2026-01-01 | OK |
| 32 | 2026 (글자, 월 단위) | `'2026'` | BAD_FORMAT | BAD_FORMAT | OK |
| 33 | 전각 숫자 ２０２６-０１ | `'２０２６-０１'` | 2026-01-01 | 2026-01-01 | OK |
| 34 | 빈 칸 | `None` | EMPTY | EMPTY | OK |
| 35 | 공백 | `'  '` | EMPTY | EMPTY | OK |
| 36 | 불리언 | `True` | BAD_FORMAT | BAD_FORMAT | OK |
| 37 | 합계 | `'합계'` | BAD_FORMAT | BAD_FORMAT | OK |
| 38 | 분기 1Q | `'2026 1Q'` | BAD_FORMAT | BAD_FORMAT | OK |
| 39 | 1899년 | `'1899-01'` | OUT_OF_RANGE | OUT_OF_RANGE | OK |
| - | assign_years 12개월 연속 | | | | OK |
| - | assign_years 연도 넘김(11,12,1,2) | | | | OK |
| - | suggest_year 시트 이름 | | | | OK |
| - | suggest_year 제목 셀 | | | | OK |
| - | suggest_year 후보 둘이면 모호 | | | | OK |
| - | suggest_year 없음 | | | | OK |
| - | suggest_year 숫자 일부(12026)는 연도 아님 | | | | OK |

통과 46/46

열 이름 매핑 제안 비교(`suggest_bench.py`, 합성 정답 45건: 짝 있는 35건 + 짝 없는 10건. **실제 항목 이름 분포가 아니다**):

| 방식 | 임계값 | 맞게 제안 | 제안 못 함 | 틀린 제안 | 짝 없음 정상 | 짝 없는데 제안 |
| --- | --- | --- | --- | --- | --- | --- |
| exact | 100 | 22/35 | 13 | 0 | 10/10 | 0 |
| difflib | 60 | 31/35 | 4 | 0 | 9/10 | 1 |
| difflib | 70 | 30/35 | 5 | 0 | 9/10 | 1 |
| difflib | 80 | 30/35 | 5 | 0 | 10/10 | 0 |
| difflib | 90 | 23/35 | 12 | 0 | 10/10 | 0 |
| rapidfuzz | 60 | 31/35 | 1 | 3 | 8/10 | 2 |
| rapidfuzz | 70 | 30/35 | 2 | 3 | 9/10 | 1 |
| rapidfuzz | 80 | 30/35 | 5 | 0 | 9/10 | 1 |
| rapidfuzz | 90 | 24/35 | 11 | 0 | 9/10 | 1 |

100x100 최선 일치 탐색 시간: rapidfuzz 14.8 ms, difflib 117.8 ms

제품 코드의 검증기 처리량(`backend/app/entry/values.py`의 `parse_cell`, number 열 min/max/decimals 규칙): 600,000칸 2.34초(칸당 3.9µs), text 열 200,000칸 0.85초. 엑셀 float → 십진 문자열 변환(`format(Decimal(f"{v:.15g}"), "f")`) 600,000칸 0.77초. 즉 2,000,000칸 전부 숫자라 가정하면 검증기만 약 8초다.

## 10. 한계 [확인 못 함 포함]
1. 합성 데이터만 썼다. 실제 업무 엑셀의 압축률·문자열 비중·병합 셀·서식·`<dimension>` 유무는 미확인이다. Excel이 직접 저장한 파일은 한 개도 없다(xlsxwriter, openpyxl이 만든 파일뿐).
2. 시간은 4 vCPU 호스트에서 한 번에 한 작업만 돌린 값이다. 같은 프로세스 안 동시 2건(GIL)은 이번에 다시 재지 않았고 03c X-27 기록(2건 약 2.3배)을 인용한다.
3. DB 적재는 호스트 포트 매핑 경유 tmpfs PostgreSQL 한 인스턴스에서 한 번씩 쟀다(반복 3회가 아님). 인덱스는 PK와 기간 UNIQUE뿐이다(실제 동적 표는 `ds_` 표라 동일 구성이지만 뷰·Superset 영향은 없음).
4. 병합 셀 위치와 숨긴 행·열은 read-only 모드에서 알 수 없다(7절 D2, A30, F1).
5. 프록시(nginx `client_max_body_size`)는 이번에 다시 측정하지 않았다. 03c X-27 6절의 기존 실측(기본 1m이면 1MiB 초과 413, 상한 + 1MiB 여유 필요)을 인용한다.
