# 02. 기술 Reference

- Gate: ① RESEARCH & DECIDE
- 승인일: 2026-10-11 (사용자 승인)
- 근거 조사: researcher 조사 → reviewer 교차검증 → 확보한 원본 파일과의 재대조. 조사 초안은 `_workspace/gate1/tech-references.md`(Git 제외)에 있고, 이 문서에는 승인된 선택과 원본 대조 결과를 옮겼다.
- 확보 위치: 루트 `references/<후보>/` (각 폴더 README에 출처, 커밋, 라이선스, 참고 위치, 파일별 SHA-256)

## 결정

1. **5개 후보를 모두 확보한다.** 영역마다 1개, 모두 허용형 라이선스다.
2. **저장소 전체가 아니라 비교표가 지목한 파일만** `references/<후보명>/`에 받는다. 각 폴더에 원본 `LICENSE`(NOTICE가 있으면 NOTICE)를 함께 둔다.
3. **받지 않는 것:** Grist `ext/`, Baserow `premium/`·`enterprise/`·`docs/`.
4. **참고 우선순위:** Baserow → lark → Superset Embedded → Grist → react-datasheet-grid.
5. 후보는 **구조·알고리즘 참고용**이다. 라이브러리 선택은 브리프 4.7절대로 유지한다(FastAPI, SQLAlchemy, openpyxl, pandas, rapidfuzz, lark, React, AG Grid Community, Apache Superset).

## 선택된 Reference 5개

| 순위 | 영역 | 후보 (폴더) | 확보 커밋 | 라이선스 / 판정 | 참고할 구조·알고리즘 | 통합 난이도·위험 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 수식 → SQL 변환 | Baserow 수식 모듈 (`baserow/`) | `ae95e51` (2026-10-09, develop) | MIT Expat / 허용형. `premium/`·`enterprise/` 별도 라이선스, `docs/` CC BY-SA 4.0은 받지 않음. `circular_reference_checker.py`는 Apache 2.0 파생 헤더(Apache 2.0도 허용형) | `formula/ast/{tree,function,function_defs,visitors}.py`, `formula/expression_generator/generator.py`, `formula/parser/update_field_names.py`, `fields/dependencies/circular_reference_checker.py` | 중간. Django ORM → SQLAlchemy 번역, 파서는 ANTLR(우리는 lark). 순환 검사기는 f-string raw SQL이라 알고리즘만 참고. 수식 범위(미결정 2번)에 따라 lookup·집계 모듈이 참고 대상이 될 수 있음 |
| 2 | 수식 파서 | lark 공식 examples (`lark/`) | `9a4fb9c` (2026-08-27) | MIT / 허용형 | `examples/calc.py`, `examples/advanced/{create_ast,error_reporting_lalr,error_handling,_json_parser}.py`, `lark/parsers/lalr_interactive_parser.py` | 낮음~중간. 엑셀 수식 전체를 다룬 허용형 완성 문법 없음, 문법·변환기 직접 작성. 순환 검출은 lark 범위 밖. `_json_parser`를 import하는 두 예제는 받은 파일만으로 실행 불가 |
| 3 | Superset Embedded | apache/superset (`superset/`) | `e229ea4` (2026-10-11, master) | Apache 2.0 / 허용형 (NOTICE 동봉) | `superset-embedded-sdk/src/index.ts`, `superset-embedded-sdk/src/guestTokenRefresh.ts`(+`.test.ts`), `superset-embedded-sdk/README.md`, `superset/security/api.py`, `superset/security/guest_token.py` | 중간. RLS `clause`가 SQL 문자열이고 서버 검증이 없음. 팀 웹서버 운영 조건(5절 4번), Explore 제공 방식(5절 7번) 미결정. master와 배포본(SDK 0.4.0, Superset 6.1.0) 차이 가능 |
| 4 | 엑셀 가져오기 | Grist (`grist-core/`) | `6dfae2f` (2026-10-09) | Apache 2.0 / 허용형 (NOTICE 동봉). `ext/` 비공개 확장은 받지 않음 | `sandbox/grist/imports/{import_xls,import_utils}.py`, `sandbox/grist/parse_data.py`, `app/client/components/Importer.ts` | 중간. 알고리즘 참고는 쉽고 UI 흐름 이식은 큼. Grist 내부 구조에 묶여 복사 불가·재작성 전제 |
| 5 | 붙여넣기 입력 그리드 | react-datasheet-grid (`react-datasheet-grid/`) | `862a1bb` (2026-03-03) | MIT / 허용형 | `src/utils/copyPasting.ts`, `src/components/DataSheetGrid.tsx` | 낮음~중간. AG Grid 구현 사례가 아님. 파서에 한계가 있어 그대로 이식 불가(아래 참고) |

전체 커밋 해시는 각 폴더 README에 있다. 라이선스 근거는 모두 확보한 원본 `LICENSE`(와 `NOTICE`)로 확인했다.

## 확보 결과 (2026-10-11)

| 폴더 | 받은 파일 | 제외 확인 |
| --- | --- | --- |
| `references/baserow/` | 소스 7 + `LICENSE` | `premium/`, `enterprise/`, `docs/` 없음 |
| `references/lark/` | 소스 6 (추가 확보 1 포함) + `LICENSE` | 없음(NOTICE 없음) |
| `references/superset/` | 소스·README·테스트 6 (추가 확보 2 포함) + `LICENSE.txt` + `NOTICE` | - |
| `references/grist-core/` | 소스 4 + `LICENSE.txt` + `NOTICE.txt` | `ext/` 없음 |
| `references/react-datasheet-grid/` | 소스 2 + `LICENSE` | - |

- 파일은 업스트림에서 `git`으로 해당 커밋의 파일을 그대로 꺼내 경로를 유지해 저장했고 수정하지 않았다. 파일별 크기와 SHA-256은 각 README에 있다.
- 폴더 안 `README.md`와 `references/README.md`는 이 저장소에서 작성한 것이다.
- **추가 확보 (2026-10-11, 사용자 승인, 같은 커밋·같은 방식):** lark `examples/advanced/_json_parser.py`(`error_reporting_lalr.py`·`error_handling.py`가 import하는 문법), Superset `superset-embedded-sdk/src/guestTokenRefresh.ts`와 `guestTokenRefresh.test.ts`(`getGuestTokenRefreshTiming` 정의). 해시와 README를 갱신했다. 원본 기준 토큰 갱신 시점은 `max(10초, exp - 현재시각) - 5초`, `exp` 파싱 실패 시 5분 - 5초, 재시도 대기 10초이며 `jwt-decode`에 의존한다. 이로써 아래 "원본에서 찾지 못함"의 `getGuestTokenRefreshTiming` 항목은 해소됐다.
- **받지 않기로 한 것(사용자 지시):** Baserow의 `baserow/core/` 아래 레지스트리·ANTLR 생성 파서. 해당 정의(`formula_function_registry`, `MaximumFormulaSizeError`, 생성 파서)는 `references/`로 확인할 수 없다.

## 원본 대조 결과

요약 도구가 읽은 내용으로 쓴 비교표 서술을 확보한 원본과 주장 단위로 대조했다(reviewer 수행, 추가 스팟 확인은 메인이 수행).

**건수: 일치 87 / 부분 일치 9 / 불일치 1 / 원본에서 찾지 못함 2.** 추천 순서와 5개 후보의 허용형 판정은 바뀌지 않는다. 비교표와 다른 점은 다음과 같다.

**불일치 1건**
- **react-datasheet-grid `parseTextPlainData`:** 비교표는 "큰따옴표 안의 탭·줄바꿈을 셀 내용으로 유지"라고 했으나, 실제로는 **줄바꿈만** 유지된다. 탭은 따옴표 상태와 무관하게 셀을 나눈다(`"a\tb"\tc` → 3셀, 따옴표도 안 벗겨짐). 한 줄짜리 따옴표 셀(`"abc"`, `"He said ""hi"""`)은 바깥 따옴표와 `""`가 그대로 남는다. 파일에서 직접 확인했다. 파서가 작아 재작성하기 쉽다는 평가는 유지되지만 그대로 이식하지 않고 탭·따옴표·`\r` 테스트 케이스를 직접 작성한다.

**부분 일치 9건 (보정)**
- **Baserow 라이선스:** `circular_reference_checker.py`는 `Copyright 2020, Jack Linke`, Apache 2.0 파생 코드(`OmenApps/django-postgresql-dag`의 재귀 CTE) 헤더가 있다. 비교표는 MIT Expat로만 적었다. 판정은 유지된다.
- **Baserow `circular_reference_checker.py`가 f-string으로 raw SQL을 조립한다**(`# noqa: S608`). SQL 문자열 조립 금지 원칙과 충돌하는 패턴이므로 알고리즘만 참고한다.
- **Baserow 파서는 ANTLR이다.** 비교표의 "미확인"이 해소됐다. 공백·주석 보존 방식을 lark로 옮기려면 별도 방안이 필요하다.
- **Baserow 파일 귀속:** 세 이름(`check_arg_type_valid`, `type_function_given_typed_args`, `to_django_expression_given_args`)은 모두 `tree.py`에 있지만 DB 식 변환의 실제 구현은 `function.py`·`function_defs.py`에 있다. `field_by_id`는 이름 변경 시 갱신되지 않는다. `MaximumFormulaSizeError`의 "수식이 너무 큼" 문구는 받은 파일에서 확인되지 않는다.
- **Grist `headers_guess`:** 기준이 "비어 있지 않은 셀 수의 최빈값"이 아니라 후보 행의 **마지막 비어 있지 않은 셀 위치+1이 `modal-1` 이상**이다. 헤더 앞 행은 버려진다. **`ColumnDetector`:** 90% 미달 시 타입은 Text가 아니라 `Any`다.
- **Grist `Importer.ts`:** "Match on"이라는 UI 문구는 없다(실제: "Merge rows that match these fields:").
- **Superset:** RLS `dataset`의 정수 제약 근거는 `guest_token.py`(`Optional[str]`)가 아니라 `api.py`다.

**원본에서 찾지 못함 2건**
- lark README의 "standalone tool은 MPL 2.0" 서술(업스트림 README를 받지 않았다). 단, `lalr_interactive_parser.py`에 `###{standalone` 표식 구간이 있다.
- `getGuestTokenRefreshTiming` 정의(받지 않은 `guestTokenRefresh` 파일에 있었음 → 추가 확보로 해소).

**보강된 위험 (Superset)**
- 서버는 RLS `clause`를 검증하지 않는다(`api.py`에 "check rls rules for validity?" TODO뿐). 감사 로그에도 `clause` 본문을 남기지 않는다. 검증은 `GUEST_TOKEN_VALIDATOR_HOOK`으로 추가할 수 있다.
- 모르는 RLS 키는 400이다.

## Gate ③ 인계 사항

원본 대조에서 나온 세 가지는 설계 전에 반드시 반영한다(`docs/gate-status.md`의 인계 사항과 같은 내용).

1. **붙여넣기 파서의 따옴표 안 탭 처리:** react-datasheet-grid의 `parseTextPlainData`는 따옴표 안의 줄바꿈만 셀 내용으로 유지하고 **탭은 따옴표 안에서도 셀을 나눈다.** 한 줄짜리 따옴표 셀은 따옴표와 `""`가 그대로 남고 `\r`은 전부 제거된다. 엑셀은 `"`가 든 셀을 따옴표로 감싸 복사하므로 그대로 이식하면 데이터가 깨진다. 붙여넣기 파서 설계(모듈 경계와 테스트 기준)에 탭·따옴표·`\r` 케이스를 요구사항으로 넣는다.
2. **Baserow 순환 검사기의 f-string raw SQL:** `circular_reference_checker.py`는 SQL을 f-string으로 조립한다(`# noqa: S608`). SQL 문자열 조립 금지 원칙과 충돌하므로 **알고리즘(경로 배열로 순환 판정)만 참고**하고, 구현은 SQLAlchemy 표현식(`cte(recursive=True)`) 또는 파이썬 그래프 탐색으로 설계한다. 이 파일은 Apache 2.0 파생 헤더도 있다.
3. **Superset RLS `clause` 서버 미검증:** 서버는 `clause`를 검증하지 않고(`api.py`의 "check rls rules for validity?" TODO) 감사 로그에도 본문을 남기지 않는다. 검증은 `GUEST_TOKEN_VALIDATOR_HOOK`으로 추가할 수 있다. `clause`는 정수 ID와 화이트리스트 식별자만으로 만들고 문자열 값 처리 방식을 설계에 명시한다.

그 밖의 인계 사항:

- **RLS `clause`와 `CREATE VIEW`의 SQL 문자열 렌더링 문제:** Gate ③에서 **PostgreSQL 공식 문서와 SQLAlchemy 공식 문서로 근거를 확인한 뒤** 설계한다. 현재 근거는 2012년 pgsql-general 스레드 요약뿐이다(`CREATE VIEW`에 bind parameter를 쓸 수 없다는 취지). 이 환경에서 postgresql.org가 열리지 않아 현행 공식 문서는 확인하지 못했다.
- **수식 범위(브리프 5절 2번):** 정해져야 Baserow에서 참고할 모듈 범위(lookup·집계 포함 여부)를 확정한다.
- **수식 미리보기·자동완성 경로(5절 6번)와 Explore 제공 방식(5절 7번):** Gate ③에서 결정한다.
- **AG Grid 붙여넣기:** AG Grid Community에는 클립보드·범위 선택·일괄 편집·.xlsx 내보내기가 없다(AG Grid 저장소 README와 문서 원본의 `enterprise: true` 기준). 붙여넣기는 브라우저 paste 이벤트로 직접 구현한다. AG Grid Community 위에서 붙여넣기를 구현한 사례는 이번 조사에서 확보하지 못했다. `applyTransaction` 등 사용할 API는 구현 전 `ag-grid-community` 패키지 타입 정의로 에디션을 재확인한다.

## 비추천·탈락한 후보 (요약)

| 후보 | 영역 | 라이선스 | 이유 |
| --- | --- | --- | --- |
| `formulas` (vinci1it2000) | 수식 파서 | EUPL 1.1+ / **비추천** | 브리프 4.5절이 배제한 라이브러리. 구조만 읽는 경우에도 소스 복사·번역 이식·의존성 추가 불가 |
| `pycel` (dgorissen) | 수식 파서 | GPL-3.0 / **비추천** | 소스 복사 불가, 유지 정체 |
| `xlcalculator` (bradbase) | 수식 파서 | 불명확 | LICENSE 첫머리에 tokenizer·parsing·shunting 코드는 다른 라이선스라는 예외 문구가 있으나 그 내용은 LICENSE에 없음 |
| XLParser | 수식 파서 | MPL 2.0 / 주의 | C#·Irony 기반, 사용자 확인 필요한 라이선스, 소스 복사 불가 |
| frictionless-py | 엑셀 가져오기 | MIT | 차점. 가져오기 UI 흐름이 없고 프레임워크가 커 Grist보다 참고 가치가 낮음. 보조 참고로는 유효 |
| react-spreadsheet-import | 엑셀 가져오기 | MIT | 마지막 커밋 2024-08-23, Chakra UI 의존. 단계 구성 참고용 |
| messytables | 엑셀 가져오기 | 불명확 | 2019년 이후 유지 중단 |
| sqlglot / Ibis / PyPika | 수식 → SQL | MIT / Apache 2.0 / Apache 2.0 | SQLAlchemy 식 객체 생성 원칙과 맞지 않거나(sqlglot) 추상화가 큼(Ibis), SQLAlchemy와 역할이 겹침(PyPika). 신규 의존성 도입은 사용자 결정 사항 |
| dwickyfp/superset-embedded-dashboard, preset-io/embedded-example | Superset Embedded | 불명확(LICENSE 없음/미확인) | 흐름 이해용으로만 열람. 하드코딩 계정, Preset 호스팅 API 대상 등으로 추천하지 않음 |

## 조사의 한계

- 이 환경에서 ag-grid.com, docs.python.org, preset.io, frictionlessdata.io, postgresql.org 등은 열리지 않았다. SQLAlchemy 공식 문서, `graphlib` 문서, 현행 PostgreSQL `CREATE VIEW` 문서는 읽지 못했다.
- 조사 단계의 소스 요약은 요약 도구 기반이었고, 위 대조로 확보한 원본 기준으로 보정했다. 코드를 실행해 검증한 항목은 없다. FastAPI의 guest token 발급 흐름과 AG Grid 붙여넣기 구현 방식은 소스와 문서를 읽고 세운 설계 추정이다.
- 이번 조사는 저장 전 수식 평가(미리보기), 열 이름 자동완성, "예시 값" 후보 산출의 참고 사례를 다루지 않았다. `InteractiveParser.accepts()`는 구문 토큰 힌트만 준다.
- ag-grid-community 36.2.0의 게시일, glide-data-grid 커밋 이력, Ibis·PyPika 릴리스 날짜, Superset `GUEST_TOKEN_JWT_EXP_SECONDS` 기본값(커뮤니티 주장 300초, 미검증), openpyxl 수식 Tokenizer 파일 경로는 미확인이다.
