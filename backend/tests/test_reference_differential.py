"""`REF` 차분 시험(07 §6 "REF 전용 묶음", 03b 32-4): 미리보기 = 뷰 = 파이썬 독립 기대값.

묶음(`tests/reference_bundle.py`)은 기준값 항목 4개(값 0개 항목, 1900·9999 경계, 38자리 포함),
날짜 단위 일·월·연 x 숫자 열 값 5종 = 데이터셋 15개, 수식 42개(`REF` 단독, 숙주 수식,
`IF`·`IFERROR`, 계산 열 참조)다. 각 칸을 세 길로 읽어 모두 같아야 한다.

1. 미리보기 경로: 상수를 바인드로 보내는 읽기 SELECT(`service.preview`와 같은 방식)
2. 뷰 경로: 리터럴로 렌더된 뷰 정의(`dv_`·`de_`)를 읽은 결과
3. 파이썬 독립 기대값: `Decimal` 사전 `{(항목, 연도): 값}`과 행의 `date.year`만으로 계산(SQL 불사용)

비교 항목은 값의 글자 표기, `pg_typeof`, 오류 코드, DB 예외 여부다. 이어서 기준값을 정정·추가한 뒤
(뷰 재생성 없이) 같은 비교를 되풀이한다. 요약은 터미널 요약에 나온다(`tests/conftest.py`).
"""

from __future__ import annotations

import collections
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.auth.models import CurrentUser
from app.dataset import service as dataset_service
from app.db_metadata import DYNAMIC_SCHEMA
from app.ddl import column_name, error_column_name, error_view_name, view_name
from app.formula import compile_formula, repo
from app.formula.errors import CELL_ERROR_BY_NUMBER
from app.formula.hook import apply_definition, make_probe
from app.formula.refenv import load_env
from app.formula.views import build_column_infos, compile_all, source_columns, source_table
from app.reference import service as reference_service
from tests.audit_helpers import Ctx
from tests.conftest import Db
from tests.formula_api_helpers import insert_rows
from tests.reference_bundle import (
    DATASETS_PER_UNIT,
    DATES,
    FORMULAS,
    ITEMS,
    NESTED,
    PRELIM,
    PRELIM_NAMES,
    REJECTED,
    REJECTED_WITHOUT_BASE_DATE,
    Formula,
    Row,
    rows_for,
    values_match,
)
from tests.reference_helpers import add_item, add_value, item_rows, value_rows
from tests.test_reference_pg import make_ref_dataset, view_def

pytestmark = pytest.mark.slow

SUMMARY: dict[str, Any] = {}  # conftest의 터미널 요약이 읽는다
CHUNK = 8  # 한 문장에 담는 수식 수


@pytest.fixture
def db(pg_app_engine, pg_owner_engine, clean_pg):
    yield Db("pg", pg_app_engine, pg_owner_engine)


def seed_reference_items(db: Db, user_id: int) -> dict[str, int]:
    ids = {}
    for name, per_year in ITEMS.items():
        ids[name] = add_item(db, name, user_id)
        for year, value in per_year.items():
            add_value(db, ids[name], year, value, user_id)
    return ids


class Bundle:
    """데이터셋 한 개의 준비·저장·비교."""

    def __init__(self, ctx: Ctx, db: Db) -> None:
        self.ctx, self.db = ctx, db
        self.stats: collections.Counter[str] = collections.Counter()
        self.mismatches: list[str] = []
        self.exceptions: list[str] = []
        self.errors: collections.Counter[str] = collections.Counter()

    def build(self, unit: str, shift: int) -> tuple[int, dict[str, int]]:
        ds = make_ref_dataset(self.ctx, f"REF {unit} {shift}", unit, value_name="x")
        rows = rows_for(unit, shift)
        insert_rows(self.db, ds["id"], [{ds["date"]: r.date, ds["value"]: r.x} for r in rows])
        return ds["id"], {"date": ds["date"], "value": ds["value"]}

    def save(self, dataset_id: int, formulas: list[tuple[str, Formula]]) -> dict[int, Formula]:
        """수식을 컴파일해(환경 포함) 저장 표에 직접 넣는다. 열 번호 -> 수식."""
        saved: dict[int, Formula] = {}
        with Session(self.db.engine) as session:
            defn = dataset_service.read_definition(session, dataset_id)
            infos = build_column_infos(defn, repo.load_formulas(session, dataset_id))
            sources = source_columns(defn, source_table(defn))
            probe, env = make_probe(session), load_env(session, defn)
            for name, formula in formulas:
                result = compile_formula(
                    formula.expression, infos, source_columns=sources, const_probe=probe, env=env
                )
                assert result.ok, (formula.expression, [i.as_dict() for i in result.issues])
                assert len(result.reference_uses) >= 1 or "REF" not in formula.expression
                column_id = self.db.add_formula_column(
                    dataset_id,
                    name,
                    result.ast_json,
                    expression=formula.expression,
                    column_type=result.result_type or "number",
                    position=1000 + len(saved),
                    deps=tuple(result.deps),
                )
                saved[column_id] = formula
            session.rollback()
        return saved

    def make_views(self, dataset_id: int) -> None:
        with Session(self.db.engine) as session:
            apply_definition(session, dataset_id, status=None)
            session.commit()

    def compare(
        self,
        dataset_id: int,
        saved: dict[int, Formula],
        rows: list[Row],
        items: dict[str, dict[int, str]],
    ) -> None:
        """수식을 `CHUNK`개씩 나눠 읽는다(한 문장이 너무 커져 계획 시간이 길어지는 것을 막는다)."""
        ids = list(saved)
        for start in range(0, len(ids), CHUNK):
            self._compare_chunk(dataset_id, ids[start : start + CHUNK], saved, rows, items)

    def _compare_chunk(
        self,
        dataset_id: int,
        ids: list[int],
        saved: dict[int, Formula],
        rows: list[Row],
        items: dict[str, dict[int, str]],
    ) -> None:
        with Session(self.db.engine) as session:
            defn = dataset_service.read_definition(session, dataset_id)
            infos = build_column_infos(defn, repo.load_formulas(session, dataset_id))
            ds = source_table(defn)
            results = compile_all(
                infos,
                source_columns(defn, ds),
                make_probe(session),
                env=load_env(session, defn),
            )
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
            bound_cols: list[Any] = [ds.c.row_id]
            view_cols: list[Any] = [dv.c.row_id]
            date_col = column_name(next(c.id for c in defn.columns if c.display_name == "일자"))
            bound_cols.append(ds.c[date_col])
            for cid in ids:
                result = results[cid]
                value = result.value
                error = (
                    result.error
                    if result.error is not None
                    else sa.cast(sa.null(), sa.SmallInteger())
                )
                bound_cols += [
                    value,
                    value.cast(sa.Text),
                    sa.func.pg_typeof(value).cast(sa.Text),
                    error,
                ]
                v = dv.c[column_name(cid)]
                view_cols += [
                    v,
                    v.cast(sa.Text),
                    sa.func.pg_typeof(v).cast(sa.Text),
                    de.c[error_column_name(cid)],
                ]
            bound_stmt = sa.select(*bound_cols).select_from(ds).order_by(ds.c.row_id)
            view_stmt = (
                sa.select(*view_cols)
                .select_from(dv.join(de, de.c.row_id == dv.c.row_id))
                .order_by(dv.c.row_id)
            )
            try:
                bound = session.execute(bound_stmt).all()
                viewed = session.execute(view_stmt).all()
            except Exception as exc:
                session.rollback()
                self.exceptions.append(f"{type(exc).__name__}: {str(exc)[:200]}")
                return
            session.rollback()
        assert len(bound) == len(viewed) == len(rows)
        by_date = {r.date: r for r in rows}
        for brow, vrow in zip(bound, viewed, strict=True):
            assert brow[0] == vrow[0]
            for k, cid in enumerate(ids):
                formula = saved[cid]
                b = tuple(brow[2 + 4 * k : 6 + 4 * k])  # (값, 글자, 형, 오류)
                v = tuple(vrow[1 + 4 * k : 5 + 4 * k])
                label = f"{formula.expression} (행 {brow[0]})"
                self.stats["cells"] += 1
                if b[1:] != v[1:]:  # 값의 글자 표기·pg_typeof·오류 코드
                    self.mismatches.append(f"{label}: 바인드 {b[1:]} != 뷰 {v[1:]}")
                if b[0] is not None and b[3] is not None:
                    self.mismatches.append(f"{label}: 값과 오류가 동시에 있다 {b}")
                # 파이썬 독립 기대값
                expected = formula.oracle(items)(by_date[brow[1]])
                actual_error = CELL_ERROR_BY_NUMBER[int(b[3])] if b[3] is not None else None
                if actual_error is not None:
                    self.errors[actual_error] += 1
                if b[0] is None and b[3] is None:
                    self.stats["blank_cells"] += 1
                if actual_error != expected.err or not values_match(
                    b[0], expected.value, approx=formula.approx
                ):
                    self.mismatches.append(
                        f"{label}: DB {b[0]!r}/{actual_error} != "
                        f"기대 {expected.value!r}/{expected.err}"
                    )


def test_reference_bundle_preview_view_and_python_oracle_agree(ctx: Ctx, db: Db):
    seed_reference_items(db, ctx.uid("admin"))
    bundle = Bundle(ctx, db)
    formula_count = datasets = formulas_total = 0
    firsts: dict[str, tuple[int, dict[int, Formula], list[Row]]] = {}  # 단위마다 첫 데이터셋
    for unit in ("day", "month", "year"):
        for shift in range(DATASETS_PER_UNIT):
            dataset_id, _cols = bundle.build(unit, shift)
            rows = rows_for(unit, shift)
            saved = bundle.save(dataset_id, list(zip(PRELIM_NAMES, PRELIM, strict=True)))
            names = [(f"식 {i + 1}", f) for i, f in enumerate([*FORMULAS, *NESTED])]
            saved.update(bundle.save(dataset_id, names))
            bundle.make_views(dataset_id)
            bundle.compare(dataset_id, saved, rows, ITEMS)
            datasets += 1
            formulas_total += len(saved)
            formula_count = len(saved)
            firsts.setdefault(unit, (dataset_id, saved, rows))
    assert set(firsts) == {"day", "month", "year"}
    cells_before = bundle.stats["cells"]

    # --- 정정·추가 뒤(뷰 재생성 없이) 같은 비교: 일·월·연 데이터셋 각각 ----
    from tests.formula_api_helpers import dataset_hash

    before = {
        unit: (
            (view_def(db, ds_id), view_def(db, ds_id, "de")),
            dataset_hash(db, ds_id),
        )
        for unit, (ds_id, _saved, _rows) in firsts.items()
    }
    admin = CurrentUser(
        id=ctx.uid("admin"), display_name="관리자", is_admin=True, is_active=True, memberships=()
    )
    updated = {name: dict(per_year) for name, per_year in ITEMS.items()}
    ids = {r["name"]: r["id"] for r in item_rows(db)}
    value_row = next(r for r in value_rows(db) if r["item_id"] == ids["단가"] and r["year"] == 2024)
    with Session(db.engine) as session:  # 정정 1건
        reference_service.update_value(session, admin, ids["단가"], value_row["id"], value="20.5")
    updated["단가"][2024] = "20.5"
    with Session(db.engine) as session:  # 연도 추가 1건: 2027년 행이 E4에서 값으로 바뀐다
        reference_service.add_value(session, admin, ids["단가"], year=2027, value="7")
    updated["단가"][2027] = "7"
    with Session(db.engine) as session:  # 다른 항목의 없던 연도 추가: 2025년 행이 E4에서 값으로
        reference_service.add_value(session, admin, ids["공제"], year=2025, value="3.5")
    updated["공제"][2025] = "3.5"
    for unit, (ds_id, saved_ds, rows_ds) in firsts.items():
        bundle.compare(ds_id, saved_ds, rows_ds, updated)
        assert (view_def(db, ds_id), view_def(db, ds_id, "de")) == before[unit][0], unit
        assert dataset_hash(db, ds_id) == before[unit][1], unit  # 뷰 정의가 그대로다

    # --- C0 거부 사례: 모든 수식이 거부되고 코드가 기대와 같다 ----
    rejected: dict[str, str] = {}
    with Session(db.engine) as session:
        defn = dataset_service.read_definition(session, dataset_id)
        infos = build_column_infos(defn, repo.load_formulas(session, dataset_id))
        env = load_env(session, defn)
        for expression, code in REJECTED.items():
            result = compile_formula(expression, infos, build_sql=False, env=env)
            assert not result.ok, expression
            codes = [issue.code for issue in result.issues]
            assert code in codes, (expression, codes)
            rejected[expression] = code
        session.rollback()
    nodate = ctx.call(
        "definer",
        "POST",
        "/api/datasets",
        json={"team_id": ctx.world.team_a, "name": "날짜 없음 묶음", "date_unit": "day"},
    ).json()
    for expression, code in REJECTED_WITHOUT_BASE_DATE.items():
        checked = ctx.call(
            "definer",
            "POST",
            f"/api/datasets/{nodate['id']}/formulas/check",
            json={"expression": expression},
        ).json()
        assert [e["code"] for e in checked["errors"]] == [code]
        rejected[f"(기준 날짜 열 없음) {expression}"] = code

    SUMMARY.update(
        formulas=formulas_total + len(rejected),
        accepted=formulas_total,
        rejected=len(rejected),
        datasets=datasets,
        rows=sum(len(DATES[u]) for u in DATES) * DATASETS_PER_UNIT,
        formulas_per_dataset=formula_count,
        cells=bundle.stats["cells"],
        cells_before_correction=cells_before,
        blank_cells=bundle.stats["blank_cells"],
        error_cells=dict(bundle.errors),
        mismatches=len(bundle.mismatches),
        exceptions=len(bundle.exceptions),
    )
    assert bundle.exceptions == [], bundle.exceptions[:10]
    assert bundle.mismatches == [], "\n".join(bundle.mismatches[:20])
    # 오류 칸: 연도 누락(E4)과 0으로 나눔(E1)이 모두 실제로 나왔다(행렬이 경계를 건드린다)
    assert set(bundle.errors) == {"E1", "E4"}
    assert bundle.stats["cells"] > cells_before > 5000
