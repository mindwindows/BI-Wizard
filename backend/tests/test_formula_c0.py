"""C0 정적 검사(07 §1·§3·§7): 이름·타입·인수·상수·글자 규칙·순환·사슬·크기 상한·상수 부분식 오류.

모든 거부는 `{code, message, start, end}`(위치는 원문 코드포인트 번호)로 확인한다. DB 없이 실행하고,
상수 부분식 검사는 SQLite 상수 SELECT로 대신 평가한다.
"""

import pytest

from app.formula import ColumnInfo, check_formula, compile_formula, render_text
from app.formula.analyze import MAX_EXPANDED_NODES
from app.formula.cycles import MAX_CHAIN_DEPTH
from tests.formula_helpers import (
    CHOICE,
    COST,
    DAY,
    FLAG,
    NAME,
    SALES,
    SqliteProbe,
    formula_column,
    standard_columns,
    with_formulas,
)


def issues_of(expression, columns=None, **kwargs):
    result = compile_formula(
        expression, columns if columns is not None else standard_columns(), **kwargs
    )
    assert not result.ok, f"거부돼야 하는데 통과했다: {expression!r}"
    return [(i.code, i.start, i.end) for i in result.issues]


def codes_of(expression, columns=None, **kwargs):
    return [code for code, _s, _e in issues_of(expression, columns, **kwargs)]


def ok_result(expression, columns=None, **kwargs):
    result = compile_formula(
        expression, columns if columns is not None else standard_columns(), **kwargs
    )
    assert result.ok, [i.as_dict() for i in result.issues]
    return result


# --- 이름 ----


def test_unknown_column_reports_position_and_suggests_similar_names():
    result = compile_formula("[매출] + [매출액]", standard_columns())
    (issue,) = result.issues
    assert (issue.code, issue.start, issue.end) == ("UNKNOWN_COLUMN", 7, 12)
    assert "'매출액' 열을 찾을 수 없습니다" in issue.message
    assert "[매출]" in issue.message  # 비슷한 이름 안내


def test_column_name_suggestion_ignores_case_and_surrounding_spaces():
    columns = [ColumnInfo(1, "Net Sales", "number")]
    (issue,) = compile_formula("[net sales ]", columns).issues
    assert "[Net Sales]" in issue.message


def test_empty_and_control_character_column_names():
    assert issues_of("[]") == [("EMPTY_COLUMN_NAME", 0, 2)]
    assert issues_of("[a\nb]") == [("COLUMN_NAME_INVALID", 0, 5)]


def test_column_names_are_matched_after_nfc_normalization():
    import unicodedata

    nfd = unicodedata.normalize("NFD", "매출")
    assert ok_result(f"[{nfd}] + 1").deps == (SALES,)


def test_unknown_function_suggests_and_is_case_insensitive_for_known_ones():
    (issue,) = compile_formula("ROUDN([매출], 1)", standard_columns()).issues
    assert (issue.code, issue.start, issue.end) == ("UNKNOWN_FUNCTION", 0, 14)
    assert "ROUND" in issue.message
    assert ok_result("round([매출], 1)").result_type == "number"
    assert codes_of("NEG(1)") == ["UNKNOWN_FUNCTION"]  # 내부 연산자 이름은 함수로 부를 수 없다
    assert codes_of("TRUE(1)") == ["UNKNOWN_FUNCTION"]


def test_multiple_errors_are_collected_in_position_order():
    result = compile_formula('[매출] + "a" + NOPE(1) + [없음]', standard_columns())
    assert [(i.code, i.start, i.end) for i in result.issues] == [
        ("ARG_TYPE", 7, 10),
        ("UNKNOWN_FUNCTION", 13, 20),
        ("UNKNOWN_COLUMN", 23, 27),
    ]


def test_syntax_errors_stop_at_the_first_one_and_use_the_same_format():
    result = compile_formula("[매출] +", standard_columns())
    assert [(i.code, i.start, i.end) for i in result.issues] == [("UNEXPECTED_END", 6, 6)]
    assert result.ast is None and result.value is None


# --- 타입·인수 ----


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ('[매출] + "a"', [("ARG_TYPE", 7, 10)]),
        ('"a" + [매출]', [("ARG_TYPE", 0, 3)]),
        ("[매출] + TRUE", [("ARG_TYPE", 7, 11)]),
        ("[일자] + 1", [("ARG_TYPE", 0, 4)]),
        ("[이름] * 2", [("ARG_TYPE", 0, 4)]),
        ("-[이름]", [("ARG_TYPE", 1, 5)]),
        ("[매출] & [이름]", [("ARG_TYPE", 0, 4)]),
        ('"x" & [매출]', [("ARG_TYPE", 6, 10)]),
        ("IF([매출], 1, 2)", [("ARG_TYPE", 3, 7)]),
        ("AND([매출], [사용])", [("ARG_TYPE", 4, 8)]),
        ("NOT([매출])", [("ARG_TYPE", 4, 8)]),
        ("LEN([매출])", [("ARG_TYPE", 4, 8)]),
        ("LEFT([이름], [이름])", [("ARG_TYPE", 11, 15)]),
        ("YEAR([매출])", [("ARG_TYPE", 5, 9)]),
        ('DATE("2026", 1, 1)', [("ARG_TYPE", 5, 11)]),
        ("ABS([이름])", [("ARG_TYPE", 4, 8)]),
        ("SUM([매출], [이름])", [("ARG_TYPE", 10, 14)]),
        ("MIN([매출], [사용])", [("ARG_TYPE", 10, 14)]),
    ],
)
def test_argument_type_errors(expression, expected):
    assert issues_of(expression) == expected


def test_no_automatic_conversion_between_number_text_and_date_with_guidance():
    (number_in_text,) = compile_formula('"a" & 1', standard_columns()).issues
    assert "자동으로 바꾸지 않습니다" in number_in_text.message
    (text_in_number,) = compile_formula('1 + "2"', standard_columns()).issues
    assert "글자를 숫자로 자동으로 바꾸지 않습니다" in text_in_number.message
    (date_text,) = compile_formula('[일자] = "2026-01-01"', standard_columns()).issues
    assert date_text.code == "TYPE_MISMATCH"
    assert "DATE(연, 월, 일)" in date_text.message  # 날짜-글자 직접 비교 거부와 안내
    (number_text,) = compile_formula('[매출] = "1"', standard_columns()).issues
    assert number_text.code == "TYPE_MISMATCH"
    assert "자동으로 바뀌지 않습니다" in number_text.message


@pytest.mark.parametrize(
    "expression",
    ['[이름] < "a"', "[이름] >= [이름]", "[사용] > [사용]", "TRUE < FALSE"],
)
def test_ordering_comparison_is_for_numbers_and_dates_only(expression):
    result = compile_formula(expression, standard_columns())
    assert [i.code for i in result.issues] == ["ARG_TYPE"] * len(result.issues) != []
    assert "크기 비교" in result.issues[0].message or "숫자·날짜" in result.issues[0].message


def test_equality_works_on_every_type_but_only_with_the_same_type():
    for left, right in [
        ("[매출]", "[비용]"),
        ("[이름]", "[구분]"),
        ("[일자]", "[일자]"),
        ("[사용]", "TRUE"),
    ]:
        assert ok_result(f"{left} = {right}").result_type == "boolean"
    assert codes_of("[이름] = [매출]") == ["TYPE_MISMATCH"]
    assert codes_of("[사용] = 1") == ["TYPE_MISMATCH"]
    assert codes_of("IF(TRUE, [매출], [이름])") == ["TYPE_MISMATCH"]
    assert codes_of('IFERROR([매출], "x")') == ["TYPE_MISMATCH"]


@pytest.mark.parametrize(
    ("expression", "code"),
    [
        ("ROUND(1)", "ARG_COUNT"),
        ("ROUND(1, 2, 3)", "ARG_COUNT"),
        ("IF(TRUE, 1)", "ARG_COUNT"),
        ("MIN(1)", "ARG_COUNT"),
        ("MAX()", "ARG_COUNT"),
        ("SUM()", "ARG_COUNT"),
        ("AND(TRUE)", "ARG_COUNT"),
        ("NOT()", "ARG_COUNT"),
        ("LEN([이름], 1)", "ARG_COUNT"),
        ("DATE(1, 2)", "ARG_COUNT"),
        ("SUMTAG()", "ARG_COUNT"),
    ],
)
def test_argument_count_errors_cover_the_whole_call(expression, code):
    (found, start, end) = issues_of(expression)[0]
    assert (found, start, end) == (code, 0, len(expression))


def test_argument_count_messages_say_how_many_are_needed():
    (issue,) = compile_formula("MIN(1)", standard_columns()).issues
    assert "2개 이상" in issue.message and "1개가 들어 있습니다" in issue.message
    (issue,) = compile_formula("ROUND(1)", standard_columns()).issues
    assert "2개" in issue.message


def test_result_types():
    cases = {
        "[매출] + 1": "number",
        "[이름] & [구분]": "text",
        "[매출] > 1": "boolean",
        "DATE(2026, 1, 1)": "date",
        "IF([사용], [일자], [일자])": "date",
        "IFERROR([매출], 0)": "number",
        "LEN([이름])": "number",
        "TRIM([이름])": "text",
        "YEAR([일자])": "number",
        'SUMTAG("t")': None,
    }
    for expression, expected in cases.items():
        if expected is None:
            continue
        assert ok_result(expression).result_type == expected, expression


def test_choice_columns_are_text_and_unsupported_types_are_rejected():
    assert ok_result('[구분] = "A"').result_type == "boolean"
    assert ok_result("LEN([구분])").result_type == "number"
    columns = [*standard_columns(), ColumnInfo(9, "이상한", "json")]
    assert codes_of("[이상한]", columns) == ["COLUMN_TYPE_UNSUPPORTED"]


# --- 상수 규칙 ----


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("ROUND(1.5, [매출])", [("CONST_REQUIRED", 11, 15)]),
        ("ROUND(1.5, 1 + 1)", [("CONST_REQUIRED", 11, 16)]),
        ("ROUND(1.5, 11)", [("CONST_RANGE", 11, 13)]),
        ("ROUND(1.5, -11)", [("CONST_RANGE", 11, 14)]),
        ("ROUND(1.5, 0.5)", [("CONST_RANGE", 11, 14)]),
        ("ROUNDUP(1.5, 100)", [("CONST_RANGE", 13, 16)]),
        ("ROUNDDOWN(1.5, -10.5)", [("CONST_RANGE", 15, 20)]),
        ('SUMTAG("매출" & "x")', [("CONST_REQUIRED", 7, 17)]),
        ("SUMTAG([이름])", [("CONST_REQUIRED", 7, 11)]),
        ('SUMTAG("' + "가" * 51 + '")', [("CONST_RANGE", 7, 60)]),
    ],
)
def test_constant_only_arguments(expression, expected):
    assert issues_of(expression) == expected


def test_signed_constants_and_range_edges_are_accepted():
    for digits in ("-10", "10", "0", "-1", "+3"):
        assert ok_result(f"ROUND([매출], {digits})").result_type == "number"


@pytest.mark.parametrize(
    ("constant", "reason"),
    [
        ('"a\\b"', "역슬래시"),
        ('"a\\\'b"', "역슬래시"),
        ('"줄\n바꿈"', "제어 문자"),
        ('"탭\t"', "제어 문자"),
        ('"\x00"', "NUL"),
        ('"a\x7fb"', "제어 문자"),
        ('"영\u200b너비"', "서식 문자"),
        ('"방향\u202e"', "서식 문자"),
        ('"BOM\ufeff"', "서식 문자"),
        ('"줄\u2028"', "줄 구분"),
        ('"문단\u2029"', "문단 구분"),
        ('"' + "가" * 201 + '"', "200자"),
        ('"\ud800"', "잘못된 문자"),
    ],
)
def test_text_constant_rules_reject_dangerous_or_invisible_characters(constant, reason):
    expression = f"{constant} & {constant}"
    found = issues_of(expression)
    assert {code for code, _s, _e in found} == {"TEXT_CONSTANT_INVALID"}
    assert len(found) == 2
    assert reason in compile_formula(expression, standard_columns()).issues[0].message
    assert found[0][1:] == (0, len(constant))


def test_text_constant_boundaries_are_accepted():
    assert ok_result('"' + "가" * 200 + '"').result_type == "text"
    assert ok_result('"O\'Brien ""따옴표"" 100% $$ ; -- /* */ %s %(x)s"').result_type == "text"
    assert ok_result('"\u00a0\u3000 공백"').result_type == "text"  # 일반 공백류(Zs)는 허용
    assert ok_result('""').result_type == "text"


def test_text_constants_are_normalized_before_the_length_rule():
    import unicodedata

    nfd_200 = unicodedata.normalize("NFD", "한" * 200)  # NFC로는 200자, NFD로는 600코드포인트
    assert ok_result(f'"{nfd_200}"').result_type == "text"


def test_number_constants_are_limited_to_38_digits():
    assert ok_result("1" * 38).result_type == "number"
    assert ok_result("0." + "0" * 37 + "1").result_type == "number"
    assert codes_of("1" * 39) == ["NUMBER_INVALID"]
    assert codes_of("0." + "0" * 38 + "1") == ["NUMBER_INVALID"]


# --- 순환·사슬 ----


def test_self_reference_is_a_cycle_with_the_reference_position():
    columns = with_formulas((10, "합계", "[매출] + 1"))
    result = compile_formula("[합계] + 1", columns, column_id=10)
    (issue,) = result.issues
    assert (issue.code, issue.start, issue.end) == ("CIRCULAR", 0, 4)
    assert issue.path == ("합계", "합계")
    assert "합계 → 합계" in issue.message


def test_mutual_and_three_way_cycles_show_the_path_in_reference_direction():
    columns = with_formulas((10, "A", "[매출]"), (11, "B", "[A]"), (12, "C", "[B]"))
    result = compile_formula("[C] + 1", columns, column_id=10)
    (issue,) = result.issues
    assert issue.code == "CIRCULAR"
    assert issue.path == ("A", "C", "B", "A")  # A가 C를, C가 B를, B가 A를 참조한다
    assert issue.message.endswith("A → C → B → A")
    assert issue.start == 0 and issue.end == 3


def test_new_column_cannot_close_a_cycle_but_can_reference_existing_formulas():
    columns = with_formulas((10, "A", "[매출]"), (11, "B", "[A] * 2"))
    assert ok_result("[B] + [A]", columns).deps == (11, 10)


def test_cycle_in_stored_formulas_is_reported_instead_of_looping():
    base = standard_columns()
    a = formula_column(10, "A", "[매출]", base)
    b = formula_column(11, "B", "[A]", [*base, a])
    # A의 저장된 수식이 B를 가리키도록 바꿔 순환을 만든다(저장소 오염 상황).
    looped = ColumnInfo(
        10,
        "A",
        "number",
        kind="formula",
        formula=compile_formula("[B]", [*base, ColumnInfo(11, "B", "number")], build_sql=False).ast,
    )
    result = compile_formula("[B] + [A]", [*base, looped, b])
    assert [i.code for i in result.issues] == ["CIRCULAR"]


def test_reference_chain_depth_limit():
    columns = standard_columns()
    previous = "매출"
    for level in range(1, MAX_CHAIN_DEPTH + 1):
        columns.append(formula_column(100 + level, f"단계{level}", f"[{previous}] + 1", columns))
        previous = f"단계{level}"
    assert ok_result(f"[{previous}] + 1", columns).ok  # 루트 아래 10단계는 허용
    columns.append(formula_column(200, "단계11", f"[{previous}] + 1", columns))
    (issue,) = compile_formula("[단계11] + 1", columns).issues
    assert issue.code == "CHAIN_TOO_LONG"
    assert "10단계" in issue.message


def test_deleted_or_invalid_referenced_formula_is_reported_at_the_reference():
    columns = standard_columns()
    broken = ColumnInfo(10, "깨진", "number", kind="formula", formula=None)
    result = compile_formula("[깨진] + 1", [*columns, broken])
    assert [(i.code, i.start, i.end) for i in result.issues] == [("REF_FORMULA_INVALID", 0, 4)]


# --- SUMTAG ---


def tagged_columns(*extra: ColumnInfo):
    return [
        ColumnInfo(1, "가", "number", tag="매출"),
        ColumnInfo(2, "나", "number", tag="매출"),
        ColumnInfo(3, "다", "number", tag="비용"),
        ColumnInfo(4, "라", "text"),
        *extra,
    ]


def test_sumtag_expands_to_the_tagged_number_columns_in_number_order():
    result = ok_result('SUMTAG("매출")', tagged_columns())
    assert result.deps == (1, 2)
    assert result.source_columns == (1, 2)
    assert result.sumtag_columns == {"매출": (1, 2)}
    assert result.ast is not None and "SUMTAG" in render_text(result.ast, tagged_columns())


def test_sumtag_includes_columns_added_later_without_editing_the_formula():
    before = ok_result('SUMTAG("매출")', tagged_columns())
    after = ok_result('SUMTAG("매출")', tagged_columns(ColumnInfo(5, "마", "number", tag="매출")))
    assert before.deps == (1, 2) and after.deps == (1, 2, 5)
    assert before.ast_json == after.ast_json  # 저장되는 AST는 같다


def test_sumtag_tag_text_never_reaches_the_sql():
    """태그 이름은 컴파일 때 열 목록으로 풀려 SQL에 글자로 나가지 않는다(07 §2-2)."""
    import sqlalchemy as sa

    from app.formula import render_literal_sql

    columns = tagged_columns()
    result = ok_result('SUMTAG("매출")', columns)
    sql = render_literal_sql(sa.select(result.value))
    assert "매출" not in sql and "c_1" in sql and "c_2" in sql and "c_3" not in sql


def test_null_constant_does_not_exist_and_empty_values_come_only_from_columns():
    assert issues_of("NULL") == [("BARE_NAME", 0, 4)]
    assert issues_of("NULL()") == [("UNKNOWN_FUNCTION", 0, 6)]
    assert issues_of("[매출] + None") == [("BARE_NAME", 7, 11)]


def test_sumtag_without_columns_is_rejected_with_the_tag_in_the_message():
    (issue,) = compile_formula('SUMTAG("없음")', tagged_columns()).issues
    assert (issue.code, issue.start, issue.end) == ("TAG_EMPTY", 0, 12)
    assert "'없음'" in issue.message


def test_sumtag_that_sums_its_own_tag_is_a_cycle():
    columns = tagged_columns()
    total = ColumnInfo(9, "합계", "number", kind="formula", tag="매출", formula=None)
    # 새 계산 열(번호 없음)이 자기 태그를 합산
    (issue,) = compile_formula(
        'SUMTAG("매출")', columns, tag="매출", column_name_hint="합계"
    ).issues
    assert issue.code == "CIRCULAR" and issue.path == ("합계", "합계")
    # 기존 계산 열이 자기 태그를 합산
    existing = [*columns, total]
    (issue,) = compile_formula('SUMTAG("매출")', existing, column_id=9).issues
    assert issue.code == "CIRCULAR" and issue.path == ("합계", "합계")
    # 다른 태그면 문제없다
    assert ok_result('SUMTAG("비용")', existing, column_id=9).deps == (3,)


def test_sumtag_over_formula_columns_checks_cycles_through_them():
    base = tagged_columns()
    derived = formula_column(9, "파생", "[가] * 2", base, tag="합산")
    columns = [*base, derived]
    assert ok_result('SUMTAG("합산") + 1', columns).deps == (9,)
    # 파생이 자기 태그를 합산하도록 수식을 바꾸면 순환
    (issue,) = compile_formula('SUMTAG("합산")', columns, column_id=9).issues
    assert issue.code == "CIRCULAR"


def test_sumtag_numeric_tags_apply_to_number_columns_only():
    columns = [ColumnInfo(1, "문자", "text", tag="t"), ColumnInfo(2, "숫자", "number", tag="t")]
    assert ok_result('SUMTAG("t")', columns).deps == (2,)


# --- 크기 상한 ----


def test_expanded_node_limit_counts_referenced_formulas_expanded():
    columns = standard_columns()
    columns.append(formula_column(10, "L0", "[매출] + [매출] + [매출]", columns))
    level = 0
    # 한 단계마다 세 번 참조하면 노드 수가 3배씩 늘어난다: 2,000을 넘는 첫 단계에서 거부된다.
    while True:
        level += 1
        expression = f"[L{level - 1}] + [L{level - 1}] + [L{level - 1}]"
        probe = compile_formula(expression, columns, build_sql=False)
        if not probe.ok:
            break
        assert probe.node_count <= MAX_EXPANDED_NODES
        columns.append(formula_column(10 + level, f"L{level}", expression, columns))
        assert level < 12
    (issue,) = probe.issues
    assert issue.code == "TOO_MANY_NODES"
    assert str(MAX_EXPANDED_NODES) in issue.message


def test_node_count_is_reported_for_valid_formulas():
    assert ok_result("1 + 2").node_count == 3
    assert ok_result("IF([사용], [매출], 0)").node_count == 4


def test_expanded_depth_limit_through_references():
    columns = standard_columns()
    columns.append(formula_column(10, "깊음", "ABS(" * 30 + "[매출]" + ")" * 30, columns))
    (issue,) = compile_formula("ABS(" * 20 + "[깊음]" + ")" * 20, columns).issues
    assert issue.code == "TOO_DEEP"


def test_sql_size_limit_rejects_exponentially_duplicating_formulas():
    expression = "DATE(YEAR(" * 6 + "DATE(2020, 1, 1)" + "), 1, 1)" * 6
    (issue,) = compile_formula(expression, standard_columns()).issues
    assert issue.code == "TOO_COMPLEX"


# --- 결과의 부가 정보 ----


def test_deps_and_source_columns_and_functions_used():
    columns = with_formulas((10, "이익", "[매출] - [비용]"))
    result = ok_result("ROUND([이익] / [매출], 2)", columns)
    assert result.deps == (10, SALES)
    assert result.source_columns == (SALES, COST)  # 계산 열은 펼쳐져 원본 열만 읽는다
    assert result.functions_used == {"ROUND", "/", "-"}
    assert result.result_type == "number"


def test_check_response_has_the_d2_shape():
    columns = standard_columns()
    good = compile_formula("[매출] / [비용]", columns).check_response(columns)
    assert good == {
        "ok": True,
        "result_type": "number",
        "refs": [
            {"column_id": SALES, "display_name": "매출"},
            {"column_id": COST, "display_name": "비용"},
        ],
        "errors": [],
    }
    bad = compile_formula("[매출] +", columns).check_response(columns)
    assert bad["ok"] is False and bad["result_type"] is None and bad["refs"] == []
    assert set(bad["errors"][0]) == {"code", "message", "start", "end"}


def test_check_formula_is_static_without_a_probe_and_builds_no_sql():
    result = check_formula("1 / 0", standard_columns())
    assert result.ok and result.value is None  # 상수 부분식 검사는 DB가 있을 때만
    assert not check_formula("[매출] + ", standard_columns()).ok


def test_columns_of_the_other_formula_are_not_probed():
    columns = with_formulas((10, "이익", "[매출] - [비용]"))
    result = compile_formula("[이익] * 2", columns)
    assert result.ok and not result.const_probe_skipped


# --- 상수 부분식 오류(C0가 상수 SELECT로 거부) ----


@pytest.fixture
def probe():
    probe = SqliteProbe()
    yield probe
    probe.close()


@pytest.mark.parametrize(
    ("expression", "start", "end"),
    [
        ("1 / 0", 0, 5),
        ("0 / 0", 0, 5),
        ("[매출] + 5 / (3 - 3)", 7, 17),
        ("IFERROR(1 / 0, 0)", 8, 13),
        ("IF(TRUE, 1, 1 / 0)", 12, 17),
        ('LEFT("abc", -1)', 0, 15),
        ('RIGHT("abc", 10001)', 0, 19),
        ('LEFT("abc", 1 - 2)', 0, 18),
    ],
)
def test_constant_subexpression_errors_are_rejected_before_the_database(
    probe, expression, start, end
):
    result = compile_formula(expression, standard_columns(), const_probe=probe)
    (issue,) = result.issues
    assert (issue.code, issue.start, issue.end) == ("CONSTANT_ERROR", start, end)
    assert "항상 오류" in issue.message
    assert result.ast is None


def test_constant_error_messages_name_the_reason():
    reasons = {
        "1 / 0": "0으로 나눔",
        'LEFT("a", -1)': "글자 길이",
    }
    probe_ = SqliteProbe()
    try:
        for expression, reason in reasons.items():
            (issue,) = compile_formula(expression, standard_columns(), const_probe=probe_).issues
            assert reason in issue.message
    finally:
        probe_.close()


def test_constant_subexpressions_without_errors_pass_and_column_dependent_ones_are_not_probed(
    probe,
):
    assert ok_result("1 / 2", const_probe=probe).ok
    assert probe.calls == [1]
    probe.calls.clear()
    assert ok_result("[매출] / 0", const_probe=probe).ok  # 열이 있으면 행마다 오류 칸(E1)
    assert probe.calls == []
    assert ok_result("[매출] + 1", const_probe=probe).ok and probe.calls == []


def test_only_the_innermost_constant_error_is_reported_and_probes_are_batched_by_height(probe):
    result = compile_formula("(1 / 0) / (2 / 0)", standard_columns(), const_probe=probe)
    assert [(i.code, i.start, i.end) for i in result.issues] == [
        ("CONSTANT_ERROR", 1, 6),
        ("CONSTANT_ERROR", 11, 16),
    ]
    assert probe.calls == [2]  # 높이가 같은 두 조건은 한 번의 SELECT, 바깥 식은 평가하지 않는다
    probe.calls.clear()
    ok_result("(1 / 2) / (3 / 4)", const_probe=probe)
    assert probe.calls == [2, 1]  # 안쪽 둘 -> 바깥 하나


def test_constants_inside_referenced_formulas_are_not_probed_again(probe):
    """다른 수식의 원문 위치가 섞이지 않고, 이미 저장된 수식의 상수는 다시 검사하지 않는다."""
    base = standard_columns()
    stored = compile_formula("1 / 2 + [매출]", base, build_sql=False).ast  # 위치가 남은 AST
    assert stored is not None and stored.start >= 0
    columns = [*base, ColumnInfo(10, "비율", "number", kind="formula", formula=stored)]
    result = compile_formula("[비율] * 2", columns, const_probe=probe)
    assert result.ok and probe.calls == []


def test_probe_is_skipped_and_flagged_when_not_given():
    result = ok_result("1 / 0")
    assert result.const_probe_skipped is True
    assert ok_result("[매출] / 0").const_probe_skipped is False


def test_probe_failures_become_a_rejection_instead_of_a_crash():
    def broken(conditions):
        raise RuntimeError("DB가 없다")

    result = compile_formula("1 / 2", standard_columns(), const_probe=broken)
    assert [i.code for i in result.issues] == ["CONSTANT_PROBE_FAILED"]


def test_generic_robustness_never_raises_for_odd_input():
    odd = [
        "((",
        "))",
        '"',
        "[",
        "]",
        "1 +",
        "+ +",
        "ROUND(",
        ",",
        "SUM(,)",
        "1 1",
        "\\",
        "§",
        "[a]" * 400,
    ]
    for expression in odd:
        result = compile_formula(expression, standard_columns())
        assert not result.ok and result.issues


def test_unused_column_kinds_do_not_break_name_resolution():
    columns = [
        *standard_columns(),
        ColumnInfo(CHOICE + 10, "x" * 3, "choice"),
        ColumnInfo(FLAG + 10, "y", "boolean"),
    ]
    assert ok_result("[xxx] = [xxx]", columns).result_type == "boolean"
    assert DAY and NAME
