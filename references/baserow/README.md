# baserow — 수식 → DB 식 변환 참고

| 항목 | 내용 |
| --- | --- |
| 출처 URL | https://github.com/baserow/baserow |
| 확보 커밋 | `ae95e512e1675db6cb1b73e8ac2266b9369b4061` (2026-10-09, 기본 브랜치 `develop` HEAD) |
| 확보일 | 2026-10-11 |
| 라이선스 | 루트 `LICENSE`(원본 동봉): 디렉터리별로 갈라진다. 받은 파일이 속한 "그 외 나머지(Baserow OSE)"는 **MIT Expat**. NOTICE 파일 없음. **예외:** `circular_reference_checker.py`는 파일 헤더에 `Copyright 2020, Jack Linke`, **Apache License 2.0** 파생 코드(`OmenApps/django-postgresql-dag`의 재귀 CTE를 수정)라고 밝히며, Baserow B.V.의 수정분만 루트 LICENSE에 따른다. 나머지 6개 .py에는 별도 라이선스 헤더가 없다 |
| 목적 | 브리프 4.5절 수식 열: 타입이 붙은 AST를 DB 식 객체로 변환하는 구조, 함수 정의 레지스트리, 열 이름 변경 시 수식 갱신, 순환 참조 검사를 **구조·알고리즘 수준**에서 참고 |
| 승인 | Gate ① (2026-10-11) 사용자 승인, `docs/decisions/02-tech-reference.md` |

## 참고할 위치 (모두 `backend/src/baserow/contrib/database/` 아래)
- `formula/ast/tree.py`, `formula/ast/function.py`, `formula/ast/function_defs.py`, `formula/ast/visitors.py` — 타입 붙은 AST 노드, 함수 정의 레지스트리, 방문자
- `formula/expression_generator/generator.py` — AST → Django 식 변환(문자열 조립이 아니라 식 객체)
- `formula/parser/update_field_names.py` — 열 이름 변경 시 수식 안의 참조만 갱신
- `fields/dependencies/circular_reference_checker.py` — 열 의존 그래프 순환 검사

## 받지 않은 것 (사용자 지시)
- `premium/`, `enterprise/`: 별도 상용 라이선스. **받지 않았고 열람·참고하지 않는다.**
- `docs/`: CC BY-SA 4.0으로 허용형 목록에 없다. **받지 않았다.**

## 주의
- Baserow는 Django ORM 식으로 변환하고 우리는 SQLAlchemy 식으로 변환한다. 번역이 필요하다.
- **`circular_reference_checker.py`는 raw SQL을 f-string으로 조립한다**(`# noqa: S608`, "no user controllable input, safe" 주석). BI-Wizard의 SQL 문자열 조립 금지 원칙과 충돌하는 패턴이므로 **알고리즘(경로 배열로 순환 판정)만 참고**하고, 구현은 SQLAlchemy 표현식(`cte(recursive=True)`) 또는 파이썬 그래프 탐색으로 한다.
- 이 후보의 수식 파서는 **ANTLR**이다(`update_field_names.py`가 `baserow.core.formula.parser.generated.*`를 import하고 ANTLR 파스 트리를 방문). 생성된 파서는 `baserow/core/` 아래에 있어 받지 않았다. 공백·주석을 보존하는 이름 변경 방식을 lark로 옮기려면 공백·주석 토큰 보존 방안이 별도로 필요하다.
- `function.py`·`function_defs.py`가 DB 식 변환의 실제 구현(`ToDjangoExpressionGivenArgsMixin`, 함수별 `to_django_expression`)이고, `tree.py`는 추상 선언과 타입 검사(`check_arg_type_valid`, `type_function_given_typed_args`)를 가진다. 함수 레지스트리 객체(`formula_function_registry`)와 `MaximumFormulaSizeError` 정의는 `baserow/core/` 아래에 있어 받지 않았다.
- `field_by_id(...)`는 열 이름 변경 시 갱신 대상이 아니다(ID는 변하지 않음). `update_field_names.py`는 `field(...)`·`lookup(...)` 이름을 바꾸고, ID↔이름 상호 변환에만 `field_by_id`를 쓴다.
- 수식 범위(브리프 5절 2번)가 미결정이다. Baserow는 lookup과 집계까지 다룬다. 범위가 같은 행 계산으로 정해지면 lookup 관련 코드는 제외할 수 있고, 집계나 다른 표 참조까지 정해지면 해당 모듈도 참고 대상이 된다.
- 이 후보는 `CREATE VIEW`의 문자열 리터럴 DDL 렌더링 지점을 다루지 않는다(Gate ③에서 PostgreSQL·SQLAlchemy 공식 문서로 근거 확인 후 설계).

## 사용 규칙
- 원본 그대로 보관한다. **파일을 수정하지 않는다.** 소스 복사는 하지 않고 구조·알고리즘만 참고한다. 복사가 필요하면 MIT 저작권 고지 유지 의무를 사용자와 먼저 확인한다.

## 파일 목록과 무결성
| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `LICENSE` | 2092 | `1c1fa26d7bb6fddee61c4120803a7190ee3199ac29062bcc1ff0f00a0de08e2b` |
| `backend/src/baserow/contrib/database/fields/dependencies/circular_reference_checker.py` | 4506 | `9cca4837a502c23d206f04cb032671478c1e5bea77316375007181e49fb9fa95` |
| `backend/src/baserow/contrib/database/formula/ast/function.py` | 20834 | `7574ce6563b1acf025b9c3e3b9d93880d1d36b30906b75785c2e734c7a9ba90d` |
| `backend/src/baserow/contrib/database/formula/ast/function_defs.py` | 125915 | `5aad4e1d38670e5799377859f8ac4c6a46a72b362d1772fb6dd5da7d9773324d` |
| `backend/src/baserow/contrib/database/formula/ast/tree.py` | 22671 | `85ef3730c8fe8e9b8f73e04920bec2103534ce5337563a408145e37862a5191c` |
| `backend/src/baserow/contrib/database/formula/ast/visitors.py` | 999 | `6ba615b09586e37a69077106e0327b3a34b699637723a3efcf9d355797183021` |
| `backend/src/baserow/contrib/database/formula/expression_generator/generator.py` | 16519 | `a13d2879ab2b7debf7e250c05a9186e4cce2a8bb1219386f56b8d00f9909d3a2` |
| `backend/src/baserow/contrib/database/formula/parser/update_field_names.py` | 8491 | `5de6fd70892738b1f8f04181d72c93e90520789c8a68780b34f5a1bc74ae11c0` |
