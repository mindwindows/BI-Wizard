"""수식 속 글자 상수 주입 회귀 사례(03c X-26.2의 P1~P10, 07 §4-4). 2단계의 층별 시험(L0~L3)도 같은
데이터를 쓴다.

값은 파이썬 글자 그대로다(07 §4-4의 이스케이프 표기를 풀어 쓴 값). 역슬래시 사례는 07 §4-4가 정한
"위 4개(P4·P5·P6·P10)와 `a\\b`, `a\\'b`"이다. 정상 입력(역슬래시 없음) 6종은 C0를 통과해 안전하게
리터럴로
렌더되어야 하고, 역슬래시가 있는 입력은 C0가 거부한다(완화책 ②).
"""

INJECTION_CASES: dict[str, str] = {
    "P1": "x'); DROP TABLE public.t; --",
    "P2": "x'; CREATE TABLE bi_data.evil(a int); --",
    "P3": "x' AS c; DELETE FROM public.t; --",
    "P4": "x\\'; DELETE FROM public.t; --",
    "P5": "\\'; CREATE TABLE bi_data.evil(a int); --",
    "P6": "x\\''; CREATE TABLE bi_data.evil(a int); --",
    "P7": "$$; DELETE FROM public.t; --",
    "P8": "x' || (SELECT string_agg(v, ',') FROM public.t) || '",
    "P9": "x' UNION SELECT 'leak' --",
    "P10": "x\\\\'; CREATE TABLE bi_data.evil(a int); --",
}

# 역슬래시를 포함해 거부돼야 하는 입력: 위 4개와 정상 입력으로서의 `a\b`, `a\'b`
BACKSLASH_CASES: dict[str, str] = {
    "P4": INJECTION_CASES["P4"],
    "P5": INJECTION_CASES["P5"],
    "P6": INJECTION_CASES["P6"],
    "P10": INJECTION_CASES["P10"],
    "a\\b": "a\\b",
    "a\\'b": "a\\'b",
}

# 역슬래시가 없어 C0를 통과하는 주입 시도(렌더가 안전해야 한다)
SAFE_RENDER_CASES: dict[str, str] = {
    key: value for key, value in INJECTION_CASES.items() if "\\" not in value
}


def formula_of(text: str) -> str:
    """글자를 수식의 글자 상수로 쓴다(`"`는 `""`)."""
    return '"' + text.replace('"', '""') + '"'
