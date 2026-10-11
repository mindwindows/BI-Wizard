import json
from refparser import parse, PasteError

C = []
def case(name, desc, raw, expected, notes, error=None, ref_diff=None):
    C.append(dict(name=name, description=desc, raw=raw, expected=expected, notes=notes, **({"expected_error": error} if error else {}), **({"reference_parser_diff": ref_diff} if ref_diff else {})))

EXCEL = "Excel 복사 형식(가정)"
case("basic_table_crlf", "일반 표 2x2. Excel은 행마다 CRLF를 붙이고 마지막 행 뒤에도 CRLF를 붙인다(가정).", "a\tb\r\nc\td\r\n", [["a","b"],["c","d"]], "끝의 빈 행이 생기지 않아야 한다(골든).")
case("basic_table_lf_no_trailing", "LF만 쓰고 마지막 개행이 없는 형식(웹 앱·Teams 등에서 올 수 있는 형태, 가정).", "a\tb\nc\td", [["a","b"],["c","d"]], "행 끝의 개행 유무와 관계없이 같은 결과(골든 1).")
case("typical_korean_header_table", "한글 열 이름과 숫자가 있는 전형적인 월별 표(표시된 값 그대로 복사됨, 가정).", "월\t매출\t비용\r\n2026-01-01\t1000\t800\r\n2026-02-01\t1200\t900\r\n", [["월","매출","비용"],["2026-01-01","1000","800"],["2026-02-01","1200","900"]], "파서는 문자열만 돌려준다. 숫자·날짜 해석은 열 타입 쪽(요구 6).")
case("comma_in_cell", "쉼표가 있는 셀. 탭 구분 텍스트에서는 쉼표 때문에 따옴표로 감싸지 않는다(가정).", "서울, 강남\t1,234\r\n", [["서울, 강남","1,234"]], "쉼표는 구분자가 아니다. CSV 파서를 재사용하면 안 되는 이유.")
case("quote_in_cell", "셀 값 He said \"hi\". Excel은 따옴표를 포함한 셀을 감싸고 \" 를 \"\" 로 바꾼다(가정).", "\"He said \"\"hi\"\"\"\tx\r\n", [["He said \"hi\"","x"]], "골든 5. 한 줄짜리 따옴표 셀도 따옴표를 벗긴다(참고 코드는 남김).")
case("quote_wrapped_value", "셀 값이 \"abc\"(따옴표 포함). Excel 직렬화는 \"\"\"abc\"\"\".", "\"\"\"abc\"\"\"", [["\"abc\""]], "골든 `\"\"\"abc\"\"\"`: 바깥 따옴표 제거 + \"\"→\".")
case("newline_in_cell_altenter", "셀 안 줄바꿈(Alt+Enter). 셀 안에는 LF, 행 끝은 CRLF. 따옴표로 감싸진다(가정).", "\"line1\nline2\"\tx\r\n", [["line1\nline2","x"]], "골든 `\"l1\\nl2\"\\tx`. 한 행, 첫 셀에 \\n.")
case("newline_crlf_inside_quotes", "따옴표 안 CRLF는 LF로 정규화(요구 2).", "\"l1\r\nl2\"", [["l1\nl2"]], "골든 `\"l1\\r\\nl2\"`.")
case("lone_cr_inside_quotes", "따옴표 안 단독 CR은 보존(요구 2).", "\"a\rb\"", [["a\rb"]], "속성 시험에서 단독 CR은 허용, CRLF 쌍은 값 범위에서 제외(5-(a) 속성 시험).")
case("tab_in_cell", "셀 안에 탭이 있는 경우. Excel은 감싸는 것으로 가정하며 요구사항은 따옴표 안 탭을 셀 내용으로 본다.", "\"a\tb\"\tc\r\n", [["a\tb","c"]], "골든 6. 참고 코드(react-datasheet-grid copyPasting.ts)는 따옴표 안 탭에서도 나눠 3칸이 되므로 요구사항과 다르다.", ref_diff="참고 코드: [[\"a\",\"b\",\"c\"]]처럼 3칸으로 쪼갠다(5-(a) 서술)")
case("empty_cells_consecutive_tabs", "빈 칸(연속 탭).", "a\t\tc\r\n", [["a","","c"]], "골든 3.")
case("empty_first_and_last", "첫 칸과 끝 칸이 빈 행.", "\tb\t\r\n", [["","b",""]], "탭으로 끝나면 빈 셀 하나(골든 `a\\t`).")
case("row_ending_with_empty_cell", "끝 빈 칸으로 끝나는 행.", "a\t\r\n", [["a",""]], "골든 `a\\t` → [a, \"\"].")
case("row_ending_with_empty_cell_no_newline", "탭으로 끝나는 입력(개행 없음).", "a\t", [["a",""]], "골든 `a\\t`.")
case("no_trailing_newline", "마지막 행에 개행이 없다.", "a\tb", [["a","b"]], "행 끝 개행 유무 무관.")
case("trailing_crlf", "마지막 행 뒤 CRLF 하나.", "a\tb\r\n", [["a","b"]], "마지막 구분자 하나는 무시(요구 1).")
case("crlf_lf_cr_mixed", "행 구분 CRLF, LF, 단독 CR이 섞인 입력(따옴표 밖).", "a\r\nb\nc\rd", [["a"],["b"],["c"],["d"]], "골든 `a\\rb` → [[a],[b]]. 참고 코드는 CR을 모두 지워 합친다.", ref_diff="참고 코드: `a\\rb` → [[\"ab\"]]")
case("blank_middle_row", "중간 빈 행은 보존.", "a\r\n\r\nb\r\n", [["a"],[""],["b"]], "골든 `a\\n\\nb`.")
case("two_trailing_newlines", "끝에 개행 두 개: 하나는 마지막 구분자로 무시, 나머지는 빈 행.", "a\r\n\r\n", [["a"],[""]], "요구 1을 직접 적용한 파생 사례(골든 표에는 없음, 직접 적용 결과).")
case("only_newline", "개행 한 글자만.", "\n", [[""]], "요구 1의 직접 적용 파생 사례: 빈 셀 하나인 행 한 개. 빈 입력과 구분된다(5-(a) 속성 시험의 ③ 참고).")
case("date_formats_displayed", "표시 형식 그대로 복사되는 날짜(가정: Excel은 표시된 텍스트를 text/plain에 넣는다).", "2026-10-11\t2026/10/11\t10/11/2026\t2026년 10월 11일\r\n", [["2026-10-11","2026/10/11","10/11/2026","2026년 10월 11일"]], "파서는 변환하지 않는다. 10/11/2026은 월/일 순서가 모호 → 열 타입 쪽에서 오류 표시(요구 6).")
case("numbers_displayed", "표시된 숫자 형식: 천 단위 쉼표 소수, 소수, 음수, 지수 표기.", "1,234.50\t0.5\t-3\t1.2E+05\t1.23456789012345E+15\r\n", [["1,234.50","0.5","-3","1.2E+05","1.23456789012345E+15"]], "표시 형식에 따라 정밀도가 이미 잘렸을 수 있다(예: 1.23456789012345E+15). 숫자 해석은 파서의 책임이 아니다.")
case("percent_currency", "퍼센트와 통화(원화) 표시.", "12.5%\t₩1,000\t(1,000)\t-₩500\r\n", [["12.5%","₩1,000","(1,000)","-₩500"]], "통화 기호·괄호 음수도 문자열 그대로. 열 타입 쪽에서 규칙화.")
case("korean_and_emoji", "한글과 이모지, 한글 공백 포함.", "한글 셀\t가나다라\t😀 이모지\r\n", [["한글 셀","가나다라","😀 이모지"]], "그대로 보존.")
case("leading_trailing_spaces", "앞뒤 공백은 자르지 않는다(요구 5).", " a \t b\r\n", [[" a "," b"]], "공백 보존. 자르기는 열 타입 쪽 선택.")
case("quote_not_at_cell_start", "따옴표가 셀 중간에 있으면 글자 그대로(요구 3).", "ab\"c\td", [["ab\"c","d"]], "골든 `ab\"c\\td`.")
case("space_before_quote", "공백 뒤의 따옴표는 따옴표 셀이 아니다(셀이 `\"`로 시작하지 않음).", " \"abc\"\tx", [[" \"abc\"","x"]], "요구 2: 셀이 `\"`로 시작해야 따옴표 셀.")
case("quote_followed_by_char_backtrack", "따옴표 셀처럼 보이나 닫는 따옴표 뒤에 글자가 오는 경우 → 되돌려 읽기(요구 3).", "\"ab\"c\td", [["\"ab\"c","d"]], "골든 `\"ab\"c\\td`.")
case("quote_followed_by_space_backtrack", "닫는 따옴표 뒤 공백도 되돌려 읽기.", "\"abc\" \tx", [["\"abc\" ","x"]], "골든 `\"abc\" \\tx`.")
case("quoted_cell_then_next_row", "따옴표 셀 안 LF 뒤에 다음 행.", "\"a\nb\"\r\nc\r\n", [["a\nb"],["c"]], "따옴표 닫힌 뒤의 CRLF는 행 구분.")
case("quoted_doubled_inside", "따옴표 셀 안의 \"\" → \".", "\"a\"\"b\"", [["a\"b"]], "요구 2.")
case("empty_quoted_cell", "빈 따옴표 셀 \"\" = 빈 문자열.", "\"\"", [[""]], "골든 `\"\"` → [[\"\"]].")
case("empty_quoted_cell_then_cell", "빈 따옴표 셀 뒤에 다른 셀.", "\"\"\tx", [["","x"]], "빈 문자열 셀 + x.")
case("quoted_newline_only", "따옴표 셀 안에 줄바꿈만.", "\"\n\"", [["\n"]], "골든 `\"\\n\"`.")
case("quoted_abc_eof", "따옴표 셀이 입력 끝에서 닫힘.", "\"abc\"", [["abc"]], "닫는 따옴표 뒤가 입력 끝이면 닫는 따옴표(요구 2).")
case("ragged_rows", "행마다 셀 수가 다르다.", "a\tb\tc\r\nd\r\n", [["a","b","c"],["d"]], "들쭉날쭉 허용, 호출 쪽이 맞춤(요구 5).")
case("single_cell", "한 칸만 복사(개행 없음).", "a", [["a"]], "Excel은 한 칸 복사에도 CRLF를 붙이는 것으로 알려져 있으나(가정) 결과는 같다.")
case("single_cell_with_crlf", "한 칸만 복사(CRLF 있음).", "a\r\n", [["a"]], "끝 구분자 하나 무시.")
case("empty_input", "빈 입력.", "", [], "붙여넣기 없음(빈 배열, 오류 아님).")
case("unclosed_quote", "따옴표로 시작하지만 닫히지 않는다. 되돌려 읽기도 일어나지 않음 → 거부.", "\"abc\tdef", None, "골든 `\"abc\\tdef`(끝) → 거부 + \"따옴표가 닫히지 않았습니다\". BZ12에서 이의를 받을 수 있는 선택.", error="따옴표가 닫히지 않았습니다")
case("backtrack_then_unclosed", "첫 따옴표 셀은 되돌려 읽기로 풀리지만 다음 셀이 닫히지 않은 따옴표로 끝난다.", "\"abc\t\"def", None, "요구 3·4를 문장 그대로 적용한 파생 사례(골든 표에는 없음): 첫 셀 `\"abc`, 둘째 셀이 닫히지 않음 → 거부. 구현 합의가 필요한 모서리.", error="따옴표가 닫히지 않았습니다")
case("nul_character", "NUL 문자가 있는 입력 거부(요구 5).", "a\u0000b", None, "골든 NUL 포함 → 거부.", error="NUL 문자가 포함되어 있습니다")

# 교차 확인: 요구사항 구현(일회용 참조)과 기대값 비교
bad = 0
for c in C:
    try:
        got = parse(c["raw"])
        res = got
    except PasteError as e:
        res = None
    if res != c["expected"]:
        bad += 1
        print("불일치", c["name"], res, c["expected"])
print("케이스", len(C), "불일치", bad)
doc = {
    "_readme": "Excel 클립보드 text/plain(탭 구분) 형식을 가정한 합성 사례. 실제 Excel·Teams 클립보드로 검증하지 않음. docs/samples/README.md 참고.",
    "format": {"raw": "클립보드 text/plain 원문(JSON 문자열, \\t \\n \\r\\n 포함)", "expected": "파서가 돌려줄 행×열 문자열 2차원 배열. 거부 사례는 null + expected_error", "expected_error": "거부 사례의 메시지(문구는 예시)", "reference_parser_diff": "참고 코드(react-datasheet-grid)와 다른 점"},
    "cases": C,
}
with open("/home/user/BI-Wizard/docs/samples/clipboard-cases.json", "w", encoding="utf-8") as f:
    json.dump(doc, f, ensure_ascii=False, indent=2)
    f.write("\n")
