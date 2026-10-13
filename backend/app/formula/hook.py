"""정의 변경 훅(04 §3·§5, 07 §8): 수식·의존을 쓰고 뷰 `dv_`·`de_`를 만든다.

dataset의 정의 변경 진입점(`datasets` 행 잠금 -> 버전 확인 -> 열 변경 -> **훅** -> `def_hash`
기록)이 같은
트랜잭션 안에서 부른다. 훅이 하는 일:

1. 저장된 수식 전부를 현재 열 이름·태그로 **다시 컴파일**한다(열 이름 변경은 AST가 열 번호 참조라
   그대로 통과, 태그 변경·계산 열 결과 형 변경은 `SUMTAG` 펼침과 형 검사에 반영된다). 하나라도
   실패하면 `FORMULA_CIRCULAR`/`FORMULA_INVALID`로 올려 열 변경까지 전부 롤백한다.
2. 방금 만든·고친 수식(`session.info`의 보류 항목)을 `formulas`에 쓰고, 의존이 바뀐 계산 열의
  `formula_deps`를 다시 쓰고, 결과 형이 바뀐 계산 열의 `dataset_columns.type`을 dataset
  service로 갱신한다.
3. 뷰 정의와 정의 해시를 만든다. 해시가 저장된 `def_hash`와 같고 뷰가 있으면 DDL을 건너뛴다. 아니면
   `ddl.create_view`로 `dv_`·`de_`를 만든다(완화책 ③ 확인 포함). PostgreSQL이 아닌 시험 엔진
   (SQLite)에서는 뷰 DDL을 하지 않는다.
4. 돌려주는 해시를 진입점이 `datasets.def_hash`에 기록한다.

`session.info` 키: `PENDING_KEY`(계산 열 만들기·고치기가 넘기는 새 수식), `FORCE_KEY`(해시가
같아도 뷰를
다시 만든다: D10 다시 시도).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import ddl
from app.core.errors import (
    FieldErrorCode,
    formula_circular,
    formula_invalid,
    validation_failed,
)
from app.dataset import service as dataset_service
from app.dataset.service import DefinitionView
from app.formula import repo
from app.formula.api import CompileResult, ConstProbe
from app.formula.literals import render_literal_sql
from app.formula.repo import StoredFormula
from app.formula.status import ViewStatus
from app.formula.views import (
    FormulaCompileFailure,
    ViewPlan,
    build_column_infos,
    build_plan,
    compile_all,
    source_columns,
    source_table,
)

logger = logging.getLogger(__name__)

PENDING_KEY = "formula.pending"
FORCE_KEY = "formula.force_rebuild"


@dataclass(frozen=True)
class PendingFormula:
    """방금 컴파일에 성공한 새 수식(아직 `formulas`에 쓰지 않았다)."""

    column_id: int
    expression: str
    result: CompileResult


def is_postgresql(session: Session) -> bool:
    return session.get_bind().dialect.name == "postgresql"


def make_probe(session: Session) -> ConstProbe:
    """상수 부분식의 오류 조건을 DB 상수 SELECT 한 번으로 평가한다(읽기만 한다).

    실패해도 트랜잭션이 깨지지 않게 SAVEPOINT 안에서 실행한다(`convert.run_const_probes`가 실패하면
    조건을 하나씩 다시 평가한다).
    """

    def probe(conditions):  # type: ignore[no-untyped-def]
        statement = sa.select(
            *[sa.cast(c, sa.Boolean).label(f"p{i}") for i, c in enumerate(conditions)]
        )
        with session.begin_nested():
            return list(session.execute(statement).one())

    return probe


def failure_to_error(failure: FormulaCompileFailure, *, edited_column_id: int | None):
    """컴파일 실패를 업무 오류로 바꾼다. 순환이면 `FORMULA_CIRCULAR`(열 이름 경로)다."""
    circular = next((i for i in failure.issues if i.code == "CIRCULAR"), None)
    if circular is not None:
        return formula_circular(list(circular.path))
    errors = []
    for issue in failure.issues:
        item = issue.as_dict()
        if failure.column_id != edited_column_id:
            # 편집 중인 수식이 아닌 다른 계산 열의 문제: 위치는 그 수식의 것이라 쓰지 않는다.
            item["message"] = f"'{failure.column_name}' 열의 수식 문제: {item['message']}"
            item["start"] = 0
            item["end"] = 0
        errors.append(item)
    return formula_invalid(errors)


def _write_changes(
    session: Session,
    defn: DefinitionView,
    existing: dict[int, StoredFormula],
    pending: PendingFormula | None,
    plan_results: dict[int, CompileResult],
) -> None:
    """보류 수식을 쓰고 의존·결과 형을 바뀐 만큼만 고친다."""
    if pending is not None:
        stored = StoredFormula(
            pending.column_id,
            pending.expression,
            pending.result.ast_json,
            pending.result.ast_hash,
        )
        if pending.column_id in existing:
            repo.update_formula(session, stored)
        else:
            repo.insert_formula(session, stored)
    deps_now = repo.load_deps(session, defn.dataset_id)
    columns = {c.id: c for c in defn.columns}
    for column_id, result in plan_results.items():
        if tuple(sorted(result.deps)) != deps_now.get(column_id, ()):
            repo.replace_deps(session, column_id, result.deps)
        column = columns[column_id]
        if result.result_type is not None and result.result_type != column.type:
            if column.tag is not None and result.result_type != "number":
                # 구분 태그는 숫자 열에만 붙는다(06 §3-3). 태그를 먼저 지워야 한다.
                raise validation_failed([("expression", FieldErrorCode.BAD_FORMAT)])
            dataset_service.set_formula_result_type(session, column_id, result.result_type)


def apply_views(session: Session, defn: DefinitionView, plan: ViewPlan, *, force: bool) -> bool:
    """뷰를 (필요하면) 만들거나 바꾼다. DDL을 실행했으면 True."""
    conn = session.connection()
    if (
        not force
        and plan.def_hash == defn.def_hash
        and ddl.view_column_names(conn, "dv", defn.dataset_id) is not None
        and ddl.view_column_names(conn, "de", defn.dataset_id) is not None
    ):
        return False
    ddl.create_view(
        conn, "dv", defn.dataset_id, plan.dv, render=render_literal_sql, echo=plan.echo_dv
    )
    ddl.create_view(
        conn, "de", defn.dataset_id, plan.de, render=render_literal_sql, echo=plan.echo_de
    )
    return True


def apply_definition(session: Session, dataset_id: int, *, status: ViewStatus | None) -> str:
    """훅 본문. 뷰 정의 해시를 돌려준다."""
    pending: PendingFormula | None = session.info.pop(PENDING_KEY, None)
    force = bool(session.info.pop(FORCE_KEY, False))
    defn = dataset_service.read_definition(session, dataset_id)
    existing = repo.load_formulas(session, dataset_id)
    stored = dict(existing)
    if pending is not None:
        stored[pending.column_id] = StoredFormula(
            pending.column_id,
            pending.expression,
            pending.result.ast_json,
            pending.result.ast_hash,
        )
    infos = build_column_infos(defn, stored)
    ds = source_table(defn)
    postgresql = is_postgresql(session)
    probe = make_probe(session) if postgresql else None
    try:
        results = compile_all(infos, source_columns(defn, ds), probe)
    except FormulaCompileFailure as failure:
        raise failure_to_error(
            failure, edited_column_id=pending.column_id if pending is not None else None
        ) from None
    _write_changes(session, defn, existing, pending, results)
    plan = build_plan(defn, ds, results)
    if postgresql:
        apply_views(session, defn, plan, force=force)
    if status is not None:
        event.listen(session, "after_commit", lambda _s: status.ok(dataset_id), once=True)
    return plan.def_hash


class FormulaDefinitionHook:
    """`DefinitionHooks`에 등록하는 훅. 뷰 대조 결과(`ViewStatus`)를 커밋 뒤에 갱신한다."""

    def __init__(self, status: ViewStatus | None = None) -> None:
        self.status = status

    def __call__(self, session: Session, dataset_id: int) -> str:
        return apply_definition(session, dataset_id, status=self.status)
