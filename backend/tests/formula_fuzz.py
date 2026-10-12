"""무작위 수식 생성기(시험 전용, 씨앗 고정). 타입이 맞는 수식을 만들고 경계 값(0·범위 밖 날짜·긴
글자 등)을 섞는다.

1단계 DB 없는 시험(컴파일이 예외를 내지 않는지, 수식 보기 왕복)과 PostgreSQL 시험(DB 예외 0건,
미리보기-뷰 일치)이 같은 생성기를 쓴다. 수식이 거부되는 것(상수 부분식 오류 등)은 정상이다.
"""

from __future__ import annotations

import datetime
import random
from decimal import Decimal

from app.formula import ColumnInfo

FUZZ_COLUMNS = [
    ColumnInfo(1, "n1", "number"),
    ColumnInfo(2, "n2", "number"),
    ColumnInfo(3, "n3", "number"),
    ColumnInfo(4, "s1", "text"),
    ColumnInfo(5, "s2", "text"),
    ColumnInfo(6, "d1", "date"),
    ColumnInfo(7, "b1", "boolean"),
]

_NUMBERS = ["0", "1", "-1", "0.5", "2.5", "1.5", "100000", "10000", "-100000", "12", "7",
            "99999999999999999999999999999999999999", "0.0000001"]  # fmt: skip
_TEXTS = ['"a"', '""', '"  b  c "', '"O\'Brien"', '"가나다"', '"ABC"', '"' + "x" * 200 + '"']
_D = Decimal


def fuzz_rows(seed: int = 0) -> list[dict]:
    """열 값 조합(빈 값·경계 값). 열 `n1`을 기준으로 10행."""
    rnd = random.Random(seed)  # noqa: S311 - 시험 데이터 생성이며 보안과 무관하다
    rows = []
    for n1 in (None, _D(0), _D(1), _D(-1), _D("2.5"), _D("100000"), _D("1E+30"), _D("-1E+30"),
               _D("0.0000001"), _D("99999999999999999999999999999999999999")):  # fmt: skip
        rows.append(
            {
                "n1": n1,
                "n2": rnd.choice([None, _D(0), _D(3), _D(-7), _D("1E+30"), _D("12.5"), _D(10001)]),
                "n3": rnd.choice([None, _D(0), _D(1), _D(-100001), _D(100001)]),
                "s1": rnd.choice(
                    [None, "", "a", " x  y ", "O'Brien", "가나다라", "ABC", "x" * 200]
                ),
                "s2": rnd.choice([None, "", "A", "  ", "abc"]),
                "d1": rnd.choice(
                    [
                        None,
                        datetime.date(2024, 2, 29),
                        datetime.date(1, 1, 1),
                        datetime.date(9999, 12, 31),
                    ]
                ),
                "b1": rnd.choice([None, True, False]),
            }
        )
    return rows


class FormulaGenerator:
    def __init__(self, seed: int) -> None:
        self.rnd = random.Random(seed)  # noqa: S311 - 시험 데이터 생성이며 보안과 무관하다

    def formulas(self, count: int) -> list[str]:
        return [self.one() for _ in range(count)]

    def one(self) -> str:
        kind = self.rnd.choice(["num", "num", "txt", "dat", "boo"])
        builder = {"num": self.num, "txt": self.txt, "dat": self.dat, "boo": self.boo}[kind]
        return builder(self.rnd.choice([1, 2, 3, 3, 4]))

    def num(self, depth: int) -> str:
        rnd = self.rnd
        if depth <= 0 or rnd.random() < 0.25:
            return rnd.choice(["[n1]", "[n2]", "[n3]", rnd.choice(_NUMBERS), rnd.choice(_NUMBERS)])
        kind = rnd.choice(
            ["bin", "bin", "bin", "abs", "round", "agg", "len", "year", "if", "iferror", "neg"]
        )
        d = depth - 1
        if kind == "bin":
            return f"({self.num(d)} {rnd.choice('+-*/')} {self.num(d)})"
        if kind == "abs":
            return f"ABS({self.num(d)})"
        if kind == "round":
            digits = rnd.choice(["0", "1", "2", "-1", "-2", "10", "-10"])
            return f"{rnd.choice(['ROUND', 'ROUNDUP', 'ROUNDDOWN'])}({self.num(d)}, {digits})"
        if kind == "agg":
            return (
                f"{rnd.choice(['MIN', 'MAX', 'SUM'])}({self.num(d)}, {self.num(d)}, {self.num(d)})"
            )
        if kind == "len":
            return f"LEN({self.txt(d)})"
        if kind == "year":
            return f"{rnd.choice(['YEAR', 'MONTH'])}({self.dat(d)})"
        if kind == "if":
            return f"IF({self.boo(d)}, {self.num(d)}, {self.num(d)})"
        if kind == "iferror":
            return f"IFERROR({self.num(d)}, {self.num(d)})"
        return f"-{self.num(d)}"

    def txt(self, depth: int) -> str:
        rnd = self.rnd
        if depth <= 0 or rnd.random() < 0.3:
            return rnd.choice(["[s1]", "[s2]", rnd.choice(_TEXTS)])
        kind = rnd.choice(["cat", "trim", "left", "if", "iferror"])
        d = depth - 1
        if kind == "cat":
            return f"({self.txt(d)} & {self.txt(d)})"
        if kind == "trim":
            return f"TRIM({self.txt(d)})"
        if kind == "left":
            return f"{rnd.choice(['LEFT', 'RIGHT'])}({self.txt(d)}, {self.num(d)})"
        if kind == "if":
            return f"IF({self.boo(d)}, {self.txt(d)}, {self.txt(d)})"
        return f"IFERROR({self.txt(d)}, {self.txt(d)})"

    def dat(self, depth: int) -> str:
        rnd = self.rnd
        if depth <= 0 or rnd.random() < 0.3:
            year = rnd.choice(["2024", "2023", "1", "9999", "0", "10000"])
            month = rnd.choice(["1", "2", "13", "0", "12"])
            day = rnd.choice(["1", "29", "30", "31", "0", "-1", "100000"])
            return rnd.choice(["[d1]", f"DATE({year}, {month}, {day})"])
        kind = rnd.choice(["date", "if", "iferror"])
        d = depth - 1
        if kind == "date":
            return f"DATE({self.num(d)}, {self.num(d)}, {self.num(d)})"
        if kind == "if":
            return f"IF({self.boo(d)}, {self.dat(d)}, {self.dat(d)})"
        return f"IFERROR({self.dat(d)}, {self.dat(d)})"

    def boo(self, depth: int) -> str:
        rnd = self.rnd
        if depth <= 0 or rnd.random() < 0.2:
            return rnd.choice(["[b1]", "TRUE", "FALSE"])
        kind = rnd.choice(["cmp", "eqt", "eqd", "logic", "not"])
        d = depth - 1
        if kind == "cmp":
            op = rnd.choice(["<", "<=", ">", ">=", "=", "<>"])
            return f"({self.num(d)} {op} {self.num(d)})"
        if kind == "eqt":
            return f"({self.txt(d)} {rnd.choice(['=', '<>'])} {self.txt(d)})"
        if kind == "eqd":
            return f"({self.dat(d)} {rnd.choice(['=', '<>', '<', '>='])} {self.dat(d)})"
        if kind == "logic":
            return f"{rnd.choice(['AND', 'OR'])}({self.boo(d)}, {self.boo(d)})"
        return f"NOT({self.boo(d)})"
