"""순환 검사와 참조 사슬 깊이(07 §7). 파이썬 그래프 탐색이며 SQL·SQLAlchemy 표현식은 쓰지 않는다.

그래프: 노드 = 열, 간선 = 계산 열 -> 참조 열(`formula_deps`). `SUMTAG`는 호출하는 쪽에서 태그 열
전부로 펼친
뒤 넘긴다(그래서 합계 열이 자기 태그를 합산하면 자기 참조가 되어 순환으로 거부된다). FU-1은 같은 행
간선뿐이라
**모든 순환(자기 참조 포함)을 금지**한다. 표준 라이브러리 `graphlib`을 쓴다.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter

MAX_CHAIN_DEPTH = 10  # 07 §7 [제안]: 루트 아래로 따라갈 수 있는 계산 열 단계


@dataclass(frozen=True)
class GraphResult:
    cycle: tuple[int, ...] | None  # [루트, …, 루트]처럼 처음과 끝이 같은 경로
    order: tuple[int, ...]  # 루트가 참조하는 계산 열을 의존되는 쪽 먼저 나열(루트 제외)
    chain: int  # 루트 아래 계산 열 단계 수(루트가 원본 열만 읽으면 0)


def analyze_graph(
    root_id: int,
    root_refs: Iterable[int],
    is_formula: Callable[[int], bool],
    deps_of: Callable[[int], tuple[int, ...]],
) -> GraphResult:
    """루트 수식(`root_id`, 직접 참조 `root_refs`)에서 닿는 열 그래프를 검사한다.

    `is_formula(id)`가 참인 열만 `deps_of(id)`(그 열 수식의 직접 참조)로 따라간다. 루트의 저장된 옛
    수식은
    무시하고 `root_refs`를 쓴다(편집 중인 새 수식).
    """
    root_refs = tuple(dict.fromkeys(root_refs))
    sorter: TopologicalSorter[int] = TopologicalSorter()
    sorter.add(root_id, *root_refs)
    deps: dict[int, tuple[int, ...]] = {root_id: root_refs}
    stack = list(root_refs)
    while stack:
        column_id = stack.pop()
        if column_id in deps:
            continue
        if is_formula(column_id):
            deps[column_id] = tuple(dict.fromkeys(deps_of(column_id)))
            sorter.add(column_id, *deps[column_id])
            stack.extend(deps[column_id])
        else:
            deps[column_id] = ()
    try:
        order = tuple(sorter.static_order())
    except CycleError as exc:
        return GraphResult(cycle=_normalize_cycle(exc.args[1], root_id), order=(), chain=0)
    levels: dict[int, int] = {}
    for column_id in order:  # 의존되는 쪽이 먼저 나온다
        if column_id == root_id or is_formula(column_id):
            levels[column_id] = 1 + max((levels[d] for d in deps[column_id]), default=0)
        else:
            levels[column_id] = 0
    formula_order = tuple(c for c in order if c != root_id and is_formula(c))
    return GraphResult(cycle=None, order=formula_order, chain=levels[root_id] - 1)


def _normalize_cycle(cycle: list[int], root_id: int) -> tuple[int, ...]:
    """순환 경로를 루트에서 시작하게 돌린다(루트가 순환에 있으면). 처음과 끝이 같다."""
    # graphlib은 "앞이 뒤의 선행 노드"인 순서(참조당하는 쪽 -> 참조하는 쪽)로 준다. 참조 방향으로
    # 뒤집는다.
    path = list(cycle)
    if path and path[0] == path[-1]:
        path = path[:-1]
    path.reverse()
    if root_id in path:
        index = path.index(root_id)
        path = path[index:] + path[:index]
    return (*path, path[0])
