# lark — 수식 파서 참고

| 항목 | 내용 |
| --- | --- |
| 출처 URL | https://github.com/lark-parser/lark |
| 확보 커밋 | `9a4fb9c7458e8155636773a3cded0016d52516da` (2026-08-27, 기본 브랜치 HEAD) |
| 확보일 | 2026-10-11 |
| 라이선스 | MIT (`LICENSE` 원본 동봉, 저작권 Erez Shinan). NOTICE 파일 없음 |
| 목적 | 브리프 4.5절 수식 파서: 우선순위 계층 문법, 파스 트리 → AST 변환, 오류를 사람이 읽는 말로 바꾸기, 편집기 자동 완성용 힌트의 구현 방식을 참고 |
| 승인 | Gate ① (2026-10-11) 사용자 승인, `docs/decisions/02-tech-reference.md` |

## 참고할 위치
- `examples/calc.py` — LALR 문법, 연산자 우선순위 계층, `Transformer` 평가
- `examples/advanced/create_ast.py` — 파스 트리를 dataclass AST로 변환
- `examples/advanced/error_reporting_lalr.py` — `UnexpectedInput.match_examples()`로 오류 유형 분류
- `examples/advanced/error_handling.py` — `on_error` 기반 오류 처리
- `lark/parsers/lalr_interactive_parser.py` — `InteractiveParser.accepts()` (구문 토큰 수준 힌트만 제공, 열 이름·예시 값 후보는 제공하지 않음)

## 받지 않은 것 / 주의
- `lark.tools.standalone`(독립 실행 파서 생성기)은 README상 MPL 2.0 별도 표기가 있어 쓰지 않으며 받지 않았다.
- 엑셀 수식 전체를 다룬 허용형 완성 문법은 이 후보에 없다. 문법은 직접 작성한다(브리프 4.5절).
- `examples/advanced/error_reporting_lalr.py`와 `error_handling.py`는 `_json_parser`(`examples/advanced/_json_parser.py`)의 문법을 import한다. 이 파일은 1차 지목 목록에 없어 처음에는 받지 않았다가, 2026-10-11 사용자 승인으로 같은 커밋에서 추가 확보했다. 두 예제는 이 파일(`from lark import Lark, Transformer, v_args`만 import)과 함께 읽는다.
- `lalr_interactive_parser.py`는 파일 안에 `###{standalone` 표식 구간이 있다(standalone 생성기 출력에 포함되는 부분). 이 파일을 참고만 하며 `lark.tools.standalone`은 쓰지 않는다.
- 순환 참조 검출은 lark 범위 밖이다(`references/baserow/`의 `circular_reference_checker.py` 참고).

## 사용 규칙
- 원본 그대로 보관한다. **파일을 수정하지 않는다.**
- lark 자체는 MIT 의존성으로 쓴다. 예제는 구조 참고용이며, 복사 시 MIT 저작권 고지를 유지한다.

## 파일 목록과 무결성

| 파일 | 크기(바이트) | SHA-256 |
| --- | --- | --- |
| `LICENSE` | 1055 | `2eee60f52d4e11357bf89e72b034d050e285e47fda1361e5662fb322ee27d771` |
| `examples/advanced/_json_parser.py` | 1765 | `61e41e8d4d42bfd5976eb6bdcce2fdccb7979017e333635d3d2f1f87fb7fb016` |
| `examples/advanced/create_ast.py` | 2444 | `e957912fcd5eb1bf98b52a9acdd63c8c8cdf965f5a2c4623e335faac000f1210` |
| `examples/advanced/error_handling.py` | 1067 | `0c7d757e8fbf22755444ab4af1acd0012b8b0f0d63d6b1db70f8274a9f3d400c` |
| `examples/advanced/error_reporting_lalr.py` | 2272 | `0fe15ec285d94a266c491d884d1183228ab6c2b5b97ead36ed016419991f0916` |
| `examples/calc.py` | 1625 | `7e64ee6f71ca8191826eacbc48195836ac6f278ba6ec69277d2025eaec508b55` |
| `lark/parsers/lalr_interactive_parser.py` | 5741 | `0cf508d964e1937c95a8027aba2aeade6a9934ca0dbb55d1364550fefe8d3eb7` |
