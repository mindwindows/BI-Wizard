"""미리보기 결과 vs 뷰 읽기 결과 차분(differential) 전수 시험(07 §6, 04 §8 합격 기준 "불일치 0건").

사전 전체(연산자 포함) x 인수 구성 x 값 변형 x 출처(수식 상수 / 원본 열 값 / 계산 열 참조
펼침)를 `tests/formula_matrix.py`가 사전에서 **자동으로** 만든다(인수 2개까지 전수, 3개 이상은
쌍별). 묶음마다 데이터셋 하나를 만들어 원본 열 값 행들을 넣고, 수식 열들을 저장한 뒤 정의 변경
훅이 뷰 `dv_`·`de_`를 만든다. 비교 대상은 같은 표현식 객체를

- **미리보기 경로**: 상수를 바인드로 보내는 읽기 SELECT(`service.preview`가 실행하는 것과 같은 방식)
- **뷰 경로**: 리터럴로 렌더된 뷰 정의(`dv_`·`de_`)를 읽은 결과

로 실행한 것이다. 값의 글자 표기(`CAST(… AS TEXT)`), `pg_typeof`, 오류 코드, DB 예외 여부가 모두
같아야 한다. 수식 거부(C0)는 컴파일 단계라 두 경로가 공유하므로 거부된 수를 따로 센다(거부
사례의 양쪽 거부는 `test_formula_cases_views.py`가 API로 확인한다).

실행 시간이 길어 `slow` 표시를 달았지만 기본 `REQUIRE_PG=1` 전체 실행에 포함한다. 결과 요약(수식 수,
비교한 칸 수, 불일치, 오류 정규화 건수)은 시험 출력 끝에 나온다.
"""

from __future__ import annotations

import collections
from decimal import Decimal
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.dataset import service as dataset_service
from app.db_metadata import DYNAMIC_SCHEMA, dataset_columns
from app.ddl import column_name, error_column_name, error_view_name, view_name
from app.formula import LITERALS, compile_formula, get_default_registry, repo
from app.formula.errors import CELL_ERROR_BY_NUMBER
from app.formula.hook import apply_definition, make_probe
from app.formula.literals import LITERALS as _LITERALS  # noqa: F401
from app.formula.views import build_column_infos, compile_all, source_columns, source_table
from tests.conftest import Db
from tests.formula_matrix import (
    CALC,
    COL,
    TAGS,
    VARIANTS,
    Group,
    all_groups,
    column_names,
    total_formulas,
)

pytestmark = pytest.mark.slow

SUMMARY: dict[str, Any] = {}  # conftest의 터미널 요약이 읽는다


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


# --- 생성기 자체 시험(DB 없음) ----


def test_matrix_is_generated_from_the_dictionary_for_every_entry():
    registry = get_default_registry()
    generated = {g.spec_name for g in all_groups()}
    assert generated == {spec.name for spec in registry.specs()}, "사전 항목이 행렬에 빠졌다"


def test_matrix_covers_all_value_variants_and_sources_for_two_argument_entries():
    groups = [g for g in all_groups() if g.spec_name == "+"]
    assert len(groups) == 1
    combos = groups[0].combos
    sources = {(c.args[0].source, c.args[1].source) for c in combos}
    assert len(sources) == 9  # 두 인수의 출처 3 x 3을 전수
    consts = {c.args[0].value for c in combos if c.args[0].source == "const"}
    assert consts == set(VARIANTS["number"])
    assert len(combos) == (len(VARIANTS["number"]) + 2) ** 2  # 전수
    assert len(groups[0].rows) == (len(VARIANTS["number"]) + 1) ** 2  # 열 값 x 빈 값 전수


def test_three_argument_entries_cover_every_pair_of_choices():
    groups = [g for g in all_groups() if g.spec_name == "DATE"]
    (group,) = groups
    choices = [{(c.args[i].source, c.args[i].value) for c in group.combos} for i in range(3)]
    for i, j in ((0, 1), (0, 2), (1, 2)):
        covered = {
            ((c.args[i].source, c.args[i].value), (c.args[j].source, c.args[j].value))
            for c in group.combos
        }
        assert covered == {(a, b) for a in choices[i] for b in choices[j]}
    assert len(group.combos) < len(choices[0]) * len(choices[1]) * len(choices[2])  # 전수보다 적다


def test_matrix_size_is_reported():
    groups = all_groups()
    assert total_formulas(groups) >= 5000
    assert len(groups) >= 50


# --- 실행 ----


def sql_type(kind: str):
    return {"number": sa.Numeric, "text": sa.Text, "boolean": sa.Boolean, "date": sa.Date}[kind]


class Harness:
    def __init__(self, db: Db) -> None:
        self.db = db
        self.user = db.add_user("matrix", "행렬")
        self.team = db.add_team("matrix_team", "행렬 팀")
        self.counter = 0
        self.errors: collections.Counter[str] = collections.Counter()
        self.stats = collections.Counter()
        self.mismatches: list[str] = []
        self.exceptions: list[str] = []
        self.rejected: collections.Counter[str] = collections.Counter()

    # -- 데이터셋 만들기
    def build(self, group: Group) -> tuple[int, dict[str, int]]:
        db = self.db
        self.counter += 1
        dataset_id = db.add_dataset(self.team, f"차분 {self.counter}", self.user)
        arity = len(group.arg_types)
        names = column_names(arity)
        raw: dict[int, int] = {}  # 위치 -> 원본 열 번호
        calc: dict[int, int] = {}
        for index, (kind, name) in enumerate(zip(group.arg_types, names, strict=True)):
            if group.tags is False and self._const_only(group, index):
                continue
            raw[index] = db.add_column(dataset_id, name, kind, position=index)
            ast = {"t": "col", "id": raw[index]}
            calc[index] = db.add_formula_column(
                dataset_id,
                f"{name} 계산",
                ast,
                expression=f"[{name}]",
                column_type=kind,
                position=100 + index,
                deps=(raw[index],),
            )
        if group.tags:
            with db.writer.begin() as conn:
                conn.execute(
                    sa.update(dataset_columns)
                    .where(dataset_columns.c.id.in_(list(raw.values())))
                    .values(tag=TAGS[0])
                )
            ast = {"t": "call", "n": "*", "a": [{"t": "col", "id": raw[0]}, {"t": "num", "v": "2"}]}
            db.add_formula_column(
                dataset_id,
                "태그 계산",
                ast,
                expression="[입력1] * 2",
                position=50,
                deps=(raw[0],),
                tag=TAGS[0],
            )
        self._insert_rows(dataset_id, group, raw)
        return dataset_id, {name: raw[i] for i, name in enumerate(names) if i in raw}

    @staticmethod
    def _const_only(group: Group, index: int) -> bool:
        return all(c.args[index].source not in (COL, CALC) for c in group.combos)

    def _insert_rows(self, dataset_id: int, group: Group, raw: dict[int, int]) -> None:
        table = sa.table(
            f"ds_{dataset_id}",
            sa.column("row_id"),
            *[sa.column(column_name(cid)) for cid in raw.values()],
            schema=DYNAMIC_SCHEMA,
        )
        values = [{column_name(raw[i]): row[i] for i in raw} for row in group.rows] or [{}]
        with self.db.engine.begin() as conn:
            conn.execute(sa.insert(table), values)

    # -- 수식 저장
    def add_formulas(self, dataset_id: int, group: Group) -> list[tuple[int, str]]:
        accepted: list[tuple[int, str]] = []
        with Session(self.db.engine) as session:
            defn = dataset_service.read_definition(session, dataset_id)
            stored = repo.load_formulas(session, dataset_id)
            infos = build_column_infos(defn, stored)
            ds = source_table(defn)
            probe = make_probe(session)
            sources = source_columns(defn, ds)
            for combo in group.combos:
                result = compile_formula(
                    combo.expression, infos, source_columns=sources, const_probe=probe
                )
                if not result.ok:
                    self.rejected[result.issues[0].code] += 1
                    continue
                column_id = self.db.add_formula_column(
                    dataset_id,
                    f"식 {len(accepted) + 1}",
                    result.ast_json,
                    expression=combo.expression,
                    column_type=result.result_type or "number",
                    position=1000 + len(accepted),
                    deps=tuple(result.deps),
                )
                accepted.append((column_id, combo.expression))
            session.rollback()
        return accepted

    def make_views(self, dataset_id: int) -> None:
        with Session(self.db.engine) as session:
            apply_definition(session, dataset_id, status=None)
            session.commit()

    # -- 비교
    def compare(self, dataset_id: int, accepted: list[tuple[int, str]]) -> None:
        if not accepted:
            return
        with Session(self.db.engine) as session:
            defn = dataset_service.read_definition(session, dataset_id)
            stored = repo.load_formulas(session, dataset_id)
            infos = build_column_infos(defn, stored)
            ds = source_table(defn)
            results = compile_all(infos, source_columns(defn, ds), make_probe(session))
            ids = [cid for cid, _ in accepted]
            texts = dict(accepted)
            dv = sa.table(
                view_name(dataset_id),
                sa.column("row_id"),
                *[sa.column(column_name(c)) for c in ids],
                schema=DYNAMIC_SCHEMA,
            )
            de = sa.table(
                error_view_name(dataset_id),
                sa.column("row_id"),
                *[sa.column(error_column_name(c)) for c in ids],
                schema=DYNAMIC_SCHEMA,
            )
            bound_columns: list[Any] = [ds.c.row_id]
            view_columns: list[Any] = [dv.c.row_id]
            for cid in ids:
                result = results[cid]
                value = result.value
                error = result.error if result.error is not None else LITERALS.null("smallint")
                bound_columns += [
                    value.cast(sa.Text),
                    sa.func.pg_typeof(value).cast(sa.Text),
                    error,
                ]
                v = dv.c[column_name(cid)]
                view_columns += [
                    v.cast(sa.Text),
                    sa.func.pg_typeof(v).cast(sa.Text),
                    de.c[error_column_name(cid)],
                ]
            bound_stmt = sa.select(*bound_columns).select_from(ds).order_by(ds.c.row_id)
            view_stmt = (
                sa.select(*view_columns)
                .select_from(dv.join(de, de.c.row_id == dv.c.row_id))
                .order_by(dv.c.row_id)
            )
            try:
                bound = session.execute(bound_stmt).all()
                viewed = session.execute(view_stmt).all()
            except Exception as exc:  # DB 예외: 어느 수식인지 하나씩 찾는다
                session.rollback()
                self.exceptions.append(f"{type(exc).__name__}: {str(exc)[:200]}")
                self._find_exception_culprits(session, ds, results, ids, texts)
                return
            session.rollback()
        assert len(bound) == len(viewed)
        for brow, vrow in zip(bound, viewed, strict=True):
            assert brow[0] == vrow[0]
            for k, cid in enumerate(ids):
                b = tuple(brow[1 + 3 * k : 4 + 3 * k])
                v = tuple(vrow[1 + 3 * k : 4 + 3 * k])
                self.stats["cells"] += 1
                if b[2] is not None:
                    self.errors[CELL_ERROR_BY_NUMBER[int(b[2])]] += 1
                if b[0] is None and b[2] is None:
                    self.stats["blank_cells"] += 1
                if b[0] is not None and b[2] is not None:
                    self.mismatches.append(f"값과 오류 동시 {texts[cid]}: {b}")
                if b != v:
                    self.mismatches.append(f"{texts[cid]} (row {brow[0]}): 바인드 {b} != 뷰 {v}")

    def _find_exception_culprits(self, session, ds, results, ids, texts) -> None:
        for cid in ids:
            result = results[cid]
            error = result.error if result.error is not None else LITERALS.null("smallint")
            try:
                session.execute(sa.select(result.value.cast(sa.Text), error).select_from(ds)).all()
            except Exception as exc:
                session.rollback()
                self.exceptions.append(f"{texts[cid]}: {type(exc).__name__}")


def test_differential_matrix_has_zero_mismatches_and_zero_database_exceptions(db):
    harness = Harness(db)
    groups = all_groups()
    accepted_total = 0
    for group in groups:
        dataset_id, _columns = harness.build(group)
        accepted = harness.add_formulas(dataset_id, group)
        accepted_total += len(accepted)
        harness.make_views(dataset_id)
        harness.compare(dataset_id, accepted)
    # 요약(터미널 요약이 출력한다)
    rejected_total = sum(harness.rejected.values())
    SUMMARY.update(
        formulas=total_formulas(groups),
        accepted=accepted_total,
        rejected=rejected_total,
        rejected_by_code=dict(harness.rejected),
        cells=harness.stats["cells"],
        blank_cells=harness.stats["blank_cells"],
        error_cells=dict(harness.errors),
        mismatches=len(harness.mismatches),
        exceptions=len(harness.exceptions),
        datasets=len(groups),
    )
    assert harness.exceptions == [], harness.exceptions[:10]
    assert harness.mismatches == [], "\n".join(harness.mismatches[:20])
    assert accepted_total + rejected_total == total_formulas(groups)
    assert accepted_total >= 4000
    # 오류 칸 세 종류가 모두 실제로 나왔다(행렬이 오류 경계를 건드린다).
    assert set(harness.errors) == {"E1", "E2", "E3"}


def test_service_preview_matches_the_view_for_a_sample_of_formulas(db):
    """`service.preview` 자체(읽기 전용·20행·형식)가 뷰 읽기와 같은 값을 주는지 표본으로
    확인한다."""
    from app.core.limits import HeavyReadLimiter
    from app.formula import service
    from app.formula.rowview import FormulaRowView

    harness = Harness(db)
    picked = 0
    limiter = HeavyReadLimiter()
    for group in all_groups():
        if group.spec_name not in {"/", "LEFT", "DATE", "ROUND", "IF", "&", "=", "SUMTAG"}:
            continue
        dataset_id, _ = harness.build(group)
        accepted = harness.add_formulas(dataset_id, group)
        harness.make_views(dataset_id)
        for column_id, expression in accepted[:: max(1, len(accepted) // 12)]:
            with Session(db.engine) as session:
                preview = service.preview(
                    session,
                    limiter,
                    user_id=1,
                    dataset_id=dataset_id,
                    expression=expression,
                    column_id=column_id,
                )
                ids = [r["row_id"] for r in preview["rows"]]
                computed = FormulaRowView().read_computed(session, dataset_id, ids, [column_id])
                session.rollback()
            for row in preview["rows"]:
                view_row = computed[row["row_id"]]
                value = view_row.values[column_id]
                assert service.format_result(preview["result_type"], value) == row["value"], (
                    expression,
                    row,
                )
                assert view_row.errors.get(column_id) == row["error"], (expression, row)
                picked += 1
        break_after = picked > 800
        if break_after:
            break
    assert picked > 300


def test_c0_rejections_are_the_same_for_check_preview_and_save(api, world, db):
    """거부는 컴파일 단계라 검사(D2)·미리보기(D3)·저장(D4) 세 길이 모두 같은 코드로 거부한다."""
    from tests.formula_api_helpers import add_column, make_dataset, post_formula

    dataset = make_dataset(api, world, "거부 일치")
    add_column(api, dataset["id"], "값")
    for expression in ("1/0", "DATE(0, 1, 1)", 'LEFT("가", -1)', "[값] + ", "[없음]"):
        base = f"/api/datasets/{dataset['id']}/formulas"
        check = api("definer", "POST", f"{base}/check", json={"expression": expression}).json()
        preview = api("definer", "POST", f"{base}/preview", json={"expression": expression})
        save = post_formula(api, dataset["id"], "거부", expression)
        assert check["ok"] is False
        assert preview.status_code == 422 and save.status_code == 422, expression
        code = check["errors"][0]["code"]
        assert preview.json()["error"]["details"]["errors"][0]["code"] == code
        assert save.json()["error"]["details"]["errors"][0]["code"] == code


# --- X-26.3의 "CAST 뒤에도 남은 22건"의 원인이 닫혔는지 (03b 5-2) ----


def _bound_and_rendered(db: Db, statement):
    """같은 SELECT를 바인드와 리터럴 렌더로 실행해 (바인드 결과, 리터럴 결과)를 돌려준다.

    리터럴 쪽은 렌더된 글자를 그대로 실행한다(시험 전용: 앱 코드는 `exec_driver_sql`을 쓰지 않는다).
    """
    from app.formula import render_literal_sql

    with db.engine.connect() as conn:
        bound = conn.execute(statement).one()
        rendered = conn.exec_driver_sql(render_literal_sql(statement)).one()
        return tuple(bound), tuple(rendered)


def test_x26_cause_1_a_plain_big_integer_bind_fails_but_the_numeric_cast_renders_and_runs_alike(db):
    """원인 1(11건): `literal(10**30)`은 BIGINT 바인드만 오류. `Decimal` CAST로 닫혔다."""
    naive = sa.select((sa.literal(10**30) + 1).label("v"))
    with db.engine.connect() as conn:
        # 대조군: 평범한 literal은 바인드로 보내면 DB가 거부하는 값이다(리터럴 렌더는 통과).
        with pytest.raises(Exception, match=r"(?i)out of range|bigint|numeric|integer"):
            conn.execute(naive).one()
    fixed = sa.select((LITERALS.number(10**30) + LITERALS.number(1)).label("v"))
    bound, rendered = _bound_and_rendered(db, fixed)
    assert bound == rendered == (Decimal(10**30 + 1),)


def test_x26_cause_2_date_and_text_comparison_is_rejected_before_the_database(api, world):
    """원인 2(3건): 날짜와 글자의 직접 비교는 C0가 거부한다(바인드/리터럴 차이가 생길 수 없다)."""
    from tests.formula_api_helpers import add_column, make_dataset

    dataset = make_dataset(api, world, "원인2")
    add_column(api, dataset["id"], "날", "date")
    for expression in ('[날] = "2024-01-01"', '[날] < "2024-01-01"', '[날] & "x"'):
        check = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/formulas/check",
            json={"expression": expression},
        ).json()
        assert check["ok"] is False and check["errors"][0]["code"] in {"TYPE_MISMATCH", "ARG_TYPE"}


def test_x26_cause_3_percent_operator_does_not_exist_and_percent_in_text_round_trips(
    api, world, db
):
    """원인 3(5건): `%` 연산자는 문법에 없다. 글자 상수 안의 `%`는 뷰에서도 그대로 왕복한다."""
    from tests.formula_api_helpers import (
        add_column,
        add_formula,
        insert_rows,
        make_dataset,
        view_rows,
    )

    dataset = make_dataset(api, world, "원인3")
    value = add_column(api, dataset["id"], "값")["id"]
    for expression in ("[값] % 7", "10 % 7"):
        check = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/formulas/check",
            json={"expression": expression},
        ).json()
        assert check["ok"] is False
    column = add_formula(api, dataset["id"], "퍼센트", '"100%" & "%%" & "%s"')["id"]
    insert_rows(db, dataset["id"], [{value: 1}])
    assert view_rows(db, dataset["id"])[0][f"c_{column}"] == "100%%%%s"
    preview = api(
        "definer",
        "POST",
        f"/api/datasets/{dataset['id']}/formulas/preview",
        json={"expression": '"100%" & "%%" & "%s"'},
    ).json()
    assert preview["rows"][0]["value"] == "100%%%%s"


def test_x26_cause_4_zero_over_zero_and_none_plus_one(api, world, db):
    """원인 4(3건): 상수 `0/0`은 C0가 거부, 열 값 0/0은 오류 칸(E1), NULL 상수는 존재하지 않는다."""
    from tests.formula_api_helpers import (
        add_column,
        add_formula,
        insert_rows,
        make_dataset,
        view_rows,
    )

    dataset = make_dataset(api, world, "원인4")
    value = add_column(api, dataset["id"], "값")["id"]
    for expression in ("0/0", "NULL + 1", "None + 1"):
        check = api(
            "definer",
            "POST",
            f"/api/datasets/{dataset['id']}/formulas/check",
            json={"expression": expression},
        ).json()
        assert check["ok"] is False, expression
    column = add_formula(api, dataset["id"], "나눔", "[값] / [값]")["id"]
    insert_rows(db, dataset["id"], [{value: 0}, {value: None}])
    values = view_rows(db, dataset["id"])
    errors = view_rows(db, dataset["id"], "de")
    assert values[0][f"c_{column}"] is None and errors[0][f"e_{column}"] == 1  # 0/0 -> E1
    assert values[1][f"c_{column}"] is None and errors[1][f"e_{column}"] is None  # 빈 값
