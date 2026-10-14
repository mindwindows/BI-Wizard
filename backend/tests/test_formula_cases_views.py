"""K6 핵심 함수 `cases` 전부를 **실제 뷰 경유**로 실행한다(07 §2-1, §3, 04 §8).

사전의 모든 사례(`FunctionSpec.cases`, 공통 모듈 `app/formula/cases.py`)를
`test_formula_pg.py`는 열 값을
바인드한 표현식으로 평가한다. 여기서는 같은 사례를 데이터셋의 원본 열·행으로 만들고 수식 열로 저장해
정의 변경 훅이 만든 뷰 `dv_`·`de_`를 읽어 기대 값·오류 코드와 비교한다. 거부(C0) 사례는 검사(D2)와
저장(D4)이 같은 오류 코드로 거부하는지 API로 확인한다.

사례 목록은 사전에서 읽으므로 함수 항목과 `cases`가 늘면 시험이 자동으로 커진다.
"""

from __future__ import annotations

import collections
import datetime
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.dataset import service as dataset_service
from app.db_metadata import DYNAMIC_SCHEMA, dataset_columns
from app.ddl import column_name
from app.formula import CELL_ERROR_BY_NUMBER, compile_formula, get_default_registry, repo
from app.formula.cases import ERROR, OK, REJECT, Case
from app.formula.hook import apply_definition, make_probe
from app.formula.views import build_column_infos, source_columns, source_table
from tests.conftest import Db
from tests.formula_api_helpers import add_column, err, make_dataset, post_formula, view_rows
from tests.formula_runner import values_equal

REGISTRY = get_default_registry()
# 환경 함수(`REF`)의 사례는 실제 기준값 표가 필요해 `test_reference_pg.py`가 돌린다.
ALL_CASES: list[tuple[str, Case]] = [
    (spec.name, case) for spec in REGISTRY.specs() if spec.precheck is None for case in spec.cases
]
TOLERANCE = Decimal("1E-9")


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


def group_key(case: Case) -> tuple:
    return (tuple(case.cols.items()), tuple(sorted(case.tags.items())))


def groups() -> dict[tuple, list[tuple[str, Case]]]:
    found: dict[tuple, list[tuple[str, Case]]] = collections.defaultdict(list)
    for name, case in ALL_CASES:
        found[group_key(case)].append((name, case))
    return found


def db_value(column_type: str, value: Any) -> Any:
    if value is None:
        return None
    if column_type == "number":
        return Decimal(str(value))
    return value


def test_cases_cover_the_dictionary_and_include_rejections_errors_and_values():
    kinds = {case.expect for _, case in ALL_CASES}
    assert kinds == {OK, ERROR, REJECT}
    assert len(ALL_CASES) >= 200
    assert {name for name, _ in ALL_CASES} == {
        spec.name for spec in REGISTRY.specs() if spec.precheck is None
    }


def test_every_non_rejected_case_gives_the_expected_value_or_error_through_real_views(db):
    user = db.add_user("cases", "사례")
    team = db.add_team("cases_team", "사례 팀")
    checked = 0
    failures: list[str] = []
    for (cols, tags), members in groups().items():
        runnable = [(n, c) for n, c in members if c.expect != REJECT]
        if not runnable:
            continue
        dataset_id = db.add_dataset(team, f"사례 {checked}", user)
        raw: dict[str, int] = {}
        for position, (name, column_type) in enumerate(cols):
            raw[name] = db.add_column(dataset_id, name, column_type, position=position)
        if tags:
            with db.writer.begin() as conn:
                for name, tag in tags:
                    conn.execute(
                        sa.update(dataset_columns)
                        .where(dataset_columns.c.id == raw[name])
                        .values(tag=tag)
                    )
        # 사례마다 행 하나(사례 i의 열 값). 같은 데이터셋의 다른 사례의 행에서도 DB 예외가
        # 없어야 한다.
        types = dict(cols)
        rows = [
            {column_name(raw[n]): db_value(types[n], c.row.get(n)) for n in raw}
            for _, c in runnable
        ]
        table = sa.table(
            f"ds_{dataset_id}",
            sa.column("row_id"),
            *[sa.column(column_name(cid)) for cid in raw.values()],
            schema=DYNAMIC_SCHEMA,
        )
        with db.engine.begin() as conn:
            if raw:
                conn.execute(sa.insert(table), rows)
            else:
                for _ in runnable:
                    conn.execute(sa.insert(table))
        formula_ids: list[int] = []
        with Session(db.engine) as session:
            defn = dataset_service.read_definition(session, dataset_id)
            infos = build_column_infos(defn, repo.load_formulas(session, dataset_id))
            sources = source_columns(defn, source_table(defn))
            probe = make_probe(session)
            for index, (_name, case) in enumerate(runnable):
                result = compile_formula(
                    case.expression, infos, source_columns=sources, const_probe=probe
                )
                assert result.ok, (case.expression, result.issues)
                formula_ids.append(
                    db.add_formula_column(
                        dataset_id,
                        f"사례식 {index + 1}",
                        result.ast_json,
                        expression=case.expression,
                        column_type=result.result_type or "number",
                        position=100 + index,
                        deps=tuple(result.deps),
                    )
                )
            session.rollback()
        with Session(db.engine) as session:
            apply_definition(session, dataset_id, status=None)
            session.commit()
        values = view_rows(db, dataset_id)
        errors = view_rows(db, dataset_id, "de")
        assert len(values) == len(errors) == len(runnable)
        for index, ((_name, case), formula_id) in enumerate(
            zip(runnable, formula_ids, strict=True)
        ):
            actual = values[index][f"c_{formula_id}"]
            code = errors[index][f"e_{formula_id}"]
            label = f"{case.expression!r} {dict(case.row)}"
            checked += 1
            if case.expect == ERROR:
                if (
                    code is None
                    or CELL_ERROR_BY_NUMBER[int(code)] != case.error
                    or actual is not None
                ):
                    failures.append(
                        f"{label}: 오류 {case.error} 기대, 실제 값 {actual!r} 코드 {code}"
                    )
            elif code is not None or not values_equal(
                actual,
                case.value,
                # 반올림 함수는 정확한 값이어야 한다(긴 소수 사례가 허용 오차에 묻히지 않게).
                tolerance=None if case.expression.startswith("ROUND") else TOLERANCE,
            ):
                failures.append(f"{label}: 기대 {case.value!r}, 실제 {actual!r} 오류 {code}")
    assert failures == [], "\n".join(failures)
    # 거부 사례를 뺀 모든 사례를 실제로 비교했다(하한이 아니라 정확한 수).
    assert checked == len([1 for _, case in ALL_CASES if case.expect != REJECT])


def test_rejected_cases_are_rejected_by_check_and_save_with_the_expected_code(api, world, db):
    rejects = [(n, c) for n, c in ALL_CASES if c.expect == REJECT]
    assert len(rejects) >= 30
    failures: list[str] = []
    seen_groups: dict[tuple, int] = {}
    for _name, case in rejects:
        key = group_key(case)
        if key not in seen_groups:
            dataset = make_dataset(api, world, f"거부 {len(seen_groups)}")
            ids = {}
            for name, column_type in case.cols.items():
                ids[name] = add_column(api, dataset["id"], name, column_type)["id"]
            for name, tag in case.tags.items():
                api(
                    "definer",
                    "PATCH",
                    f"/api/datasets/{dataset['id']}/columns/{ids[name]}",
                    json={"expected_version": _version(api, dataset["id"]), "tag": tag},
                )
            seen_groups[key] = dataset["id"]
        dataset_id = seen_groups[key]
        check = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset_id}/formulas/check",
            json={"expression": case.expression},
        ).json()
        saved = post_formula(api, dataset_id, "거부", case.expression)
        codes = [e["code"] for e in check["errors"]]
        if check["ok"] or case.error not in codes:
            failures.append(f"검사: {case.expression!r} 기대 {case.error}, 실제 {codes}")
        if saved.status_code != 422:
            failures.append(f"저장이 거부되지 않았다: {case.expression!r} {saved.status_code}")
            continue
        body = err(saved)
        saved_codes = (
            ["CIRCULAR"]
            if body["code"] == "FORMULA_CIRCULAR"
            else [e["code"] for e in body["details"]["errors"]]
        )
        if case.error not in saved_codes:
            failures.append(f"저장: {case.expression!r} 기대 {case.error}, 실제 {saved_codes}")
    assert failures == [], "\n".join(failures)


def _version(api, dataset_id: int) -> int:
    return api("definer", "GET", f"/api/datasets/{dataset_id}").json()["def_version"]


# --- K7 의미 규칙(API + 실제 뷰) ----


@pytest.fixture
def k7(api, world, db):
    dataset = make_dataset(api, world, "K7")
    ids = {
        "가": add_column(api, dataset["id"], "가")["id"],
        "나": add_column(api, dataset["id"], "나")["id"],
        "글": add_column(api, dataset["id"], "글", "text")["id"],
        "날": add_column(api, dataset["id"], "날", "date")["id"],
    }
    return dataset["id"], ids


def _first_value(db: Db, dataset_id: int, column_id: int):
    rows = view_rows(db, dataset_id)
    errors = view_rows(db, dataset_id, "de")
    return rows[0][f"c_{column_id}"], errors[0].get(f"e_{column_id}")


def test_blank_cells_propagate_through_min_max_sum_and_sumtag(api, db, k7):
    from tests.formula_api_helpers import add_formula, insert_rows

    dataset_id, ids = k7
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset_id}/columns/{ids['가']}",
        json={"expected_version": _version(api, dataset_id), "tag": "합계"},
    )
    api(
        "definer",
        "PATCH",
        f"/api/datasets/{dataset_id}/columns/{ids['나']}",
        json={"expected_version": _version(api, dataset_id), "tag": "합계"},
    )
    formulas = {
        "MIN": add_formula(api, dataset_id, "최소", "MIN([가], [나])")["id"],
        "MAX": add_formula(api, dataset_id, "최대", "MAX([가], [나])")["id"],
        "SUM": add_formula(api, dataset_id, "합", "SUM([가], [나])")["id"],
        "SUMTAG": add_formula(api, dataset_id, "태그합", 'SUMTAG("합계")')["id"],
        "PLUS": add_formula(api, dataset_id, "더함", "[가] + [나]")["id"],
        "ABS": add_formula(api, dataset_id, "절댓값", "ABS([나])")["id"],
    }
    insert_rows(db, dataset_id, [{ids["가"]: 5, ids["나"]: None}])
    for name, column_id in formulas.items():
        value, error = _first_value(db, dataset_id, column_id)
        assert value is None and error is None, name  # 0이 아니라 빈 값, 오류도 아님
    # 같은 계산에 값이 다 있으면 일반 결과
    db.writer.dispose()
    insert_rows(db, dataset_id, [{ids["가"]: 5, ids["나"]: 3}])
    last = view_rows(db, dataset_id)[1]
    assert (last[f"c_{formulas['MIN']}"], last[f"c_{formulas['MAX']}"]) == (3, 5)
    assert last[f"c_{formulas['SUM']}"] == 8 and last[f"c_{formulas['SUMTAG']}"] == 8


def test_text_comparison_ignores_case_and_error_cells_are_listed_in_the_checks(api, db, k7):
    from tests.formula_api_helpers import add_formula, insert_rows

    dataset_id, ids = k7
    same = add_formula(api, dataset_id, "같음", '[글] = "ABC"')["id"]
    different = add_formula(api, dataset_id, "다름", '[글] <> "abc"')["id"]
    ratio = add_formula(api, dataset_id, "비율", "1 / [가]")["id"]
    insert_rows(db, dataset_id, [{ids["글"]: "aBc", ids["가"]: 0}])
    value, _ = _first_value(db, dataset_id, same)
    assert value is True
    assert _first_value(db, dataset_id, different)[0] is False
    # 오류 칸: 뷰는 NULL을 돌려주고 de_에서 코드가 판정되며 점검 목록(D7·D8)에 노출된다.
    value, code = _first_value(db, dataset_id, ratio)
    assert value is None and code == 1
    summary = api("viewer", "GET", "/api/checks/formula-errors").json()["items"]
    assert [(i["dataset_id"], i["column_id"], i["error_count"]) for i in summary] == [
        (dataset_id, ratio, 1)
    ]
    cells = api("viewer", "GET", f"/api/datasets/{dataset_id}/formula-errors").json()["items"]
    assert [(c["column_id"], c["error"]) for c in cells] == [(ratio, "E1")]


def test_iferror_replaces_only_error_cells_and_keeps_blank_cells_blank(api, db, k7):
    from tests.formula_api_helpers import add_formula, insert_rows

    dataset_id, ids = k7
    column = add_formula(api, dataset_id, "대체", "IFERROR(1 / [가], -1)")["id"]
    insert_rows(db, dataset_id, [{ids["가"]: 0}, {ids["가"]: None}, {ids["가"]: 4}])
    values = [r[f"c_{column}"] for r in view_rows(db, dataset_id)]
    assert values[0] == -1 and values[1] is None and values[2] == Decimal("0.25")
    assert all(r[f"e_{column}"] is None for r in view_rows(db, dataset_id, "de"))
    # 대체된 칸은 더 이상 오류 칸이 아니다
    assert api("viewer", "GET", "/api/checks/formula-errors").json()["items"] == []


def test_dates_follow_the_calendar_and_range_errors_are_cell_errors(api, db, k7):
    from tests.formula_api_helpers import add_formula, insert_rows

    dataset_id, ids = k7
    month_end = add_formula(api, dataset_id, "다음달 1일", "DATE(YEAR([날]), MONTH([날]) + 1, 1)")[
        "id"
    ]
    past = add_formula(api, dataset_id, "범위밖", "DATE(YEAR([날]) - 5000, 1, 1)")["id"]
    insert_rows(db, dataset_id, [{ids["날"]: datetime.date(2024, 1, 31)}])
    value, _ = _first_value(db, dataset_id, month_end)
    assert value == datetime.date(2024, 2, 1)
    value, code = _first_value(db, dataset_id, past)
    assert value is None and code == 3  # E3 날짜 범위
