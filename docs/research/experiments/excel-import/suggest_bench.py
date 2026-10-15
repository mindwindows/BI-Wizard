"""열 이름 매핑 자동 제안: 문자열 규칙만 vs difflib(표준 라이브러리) vs rapidfuzz 비교 (합성 사례).

사용: python suggest_bench.py   (rapidfuzz 필요)
정답은 손으로 만든 합성 표다. 실제 회사 엑셀의 항목 이름 분포가 아니므로 정확도 수치는 '방향'으로만 읽는다.
"""

import time

from headers import suggest_mapping

TARGETS = [
    "전기 사용량", "전기 요금", "수도 사용량", "수도 요금", "가스 사용량", "가스 요금",
    "청소 비용", "보안 비용", "주차 대수", "민원 건수",
]
# (엑셀 항목 이름, 정답 target 또는 None=짝이 없음)
PAIRS = [
    ("전기 사용량", "전기 사용량"), ("전기사용량", "전기 사용량"), ("전기 사용량(kWh)", "전기 사용량"),
    ("전기사용량 (kWh)", "전기 사용량"), ("전기_사용량", "전기 사용량"), ("전기 사용", "전기 사용량"),
    ("전기사용", "전기 사용량"), ("전력 사용량", "전기 사용량"), ("전기 요금", "전기 요금"),
    ("전기요금(원)", "전기 요금"), ("전기료", "전기 요금"), ("전기 요금 합계", "전기 요금"),
    ("수도 사용량(m3)", "수도 사용량"), ("수도사용량", "수도 사용량"), ("상수도 사용량", "수도 사용량"),
    ("수도 요금", "수도 요금"), ("수도요금(원)", "수도 요금"), ("수도료", "수도 요금"),
    ("가스 사용량", "가스 사용량"), ("가스사용량(m3)", "가스 사용량"), ("가스 요금", "가스 요금"),
    ("가스요금", "가스 요금"), ("가스료", "가스 요금"), ("청소비", "청소 비용"), ("청소 비용(원)", "청소 비용"),
    ("청소비용", "청소 비용"), ("보안 비용", "보안 비용"), ("보안비", "보안 비용"), ("경비 비용", "보안 비용"),
    ("주차 대수", "주차 대수"), ("주차대수(대)", "주차 대수"), ("주차 차량 수", "주차 대수"),
    ("민원 건수", "민원 건수"), ("민원건수(건)", "민원 건수"), ("민원 접수 건수", "민원 건수"),
    # 짝이 없어야 하는 항목(엑셀의 합계·메모·계산 행 등)
    ("합계", None), ("소계", None), ("비고", None), ("메모", None), ("전월 대비 증감률", None),
    ("목표 달성률", None), ("담당자", None), ("엘리베이터 점검 횟수", None), ("승강기 사용 요금", None),
    ("전기 사용량 전월 대비", None),
]


def evaluate(method: str, threshold: float):
    # 시트 하나에는 목표 열당 엑셀 항목이 하나뿐이므로(1:1) 사례를 한 건씩 따로 평가한다.
    # (한꺼번에 넣으면 같은 목표를 가리키는 사례 변형끼리 1:1 중복 제거에 걸려 서로를 지운다.)
    t0 = time.perf_counter()
    out = [suggest_mapping([p[0]], TARGETS, method, threshold)[0] for p in PAIRS]
    dt = time.perf_counter() - t0
    tp = fp_wrong = fn = tn = fp_extra = 0
    for (src, truth), (_, got, _) in zip(PAIRS, out, strict=True):
        if truth is None:
            if got is None:
                tn += 1
            else:
                fp_extra += 1  # 짝이 없는데 제안함(사용자가 지워야 함)
        elif got == truth:
            tp += 1
        elif got is None:
            fn += 1  # 제안 못 함(사용자가 직접 선택)
        else:
            fp_wrong += 1  # 틀린 제안(가장 해롭다)
    n_match = sum(1 for p in PAIRS if p[1])
    n_none = len(PAIRS) - n_match
    return dict(method=method, threshold=threshold, correct=tp, missed=fn, wrong=fp_wrong,
                n_match=n_match, no_pair_ok=tn, no_pair_bad=fp_extra, n_none=n_none, ms=dt * 1000)


def timing_100x100():
    from rapidfuzz import fuzz, process
    import random
    rng = random.Random(1)
    syl = "전기수도가스청소보안주차민원사용량요금비용건수대수합계소계비고"
    names = ["".join(rng.choice(syl) for _ in range(rng.randint(4, 9))) for _ in range(200)]
    src, tgt = names[:100], names[100:]
    t0 = time.perf_counter()
    for s in src:
        process.extractOne(s, tgt, scorer=fuzz.WRatio)
    t_rf = time.perf_counter() - t0
    from difflib import SequenceMatcher
    t0 = time.perf_counter()
    for s in src:
        max(SequenceMatcher(None, s, t).ratio() for t in tgt)
    t_dl = time.perf_counter() - t0
    return t_rf * 1000, t_dl * 1000


if __name__ == "__main__":
    print("| 방식 | 임계값 | 맞게 제안 | 제안 못 함 | 틀린 제안 | 짝 없음 정상 | 짝 없는데 제안 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for method, ths in (("exact", [100]), ("difflib", [60, 70, 80, 90]), ("rapidfuzz", [60, 70, 80, 90])):
        for th in ths:
            r = evaluate(method, th)
            print(f"| {r['method']} | {r['threshold']} | {r['correct']}/{r['n_match']} | {r['missed']} | "
                  f"{r['wrong']} | {r['no_pair_ok']}/{r['n_none']} | {r['no_pair_bad']} |")
    rf, dl = timing_100x100()
    print(f"\n100x100 최선 일치 탐색 시간: rapidfuzz {rf:.1f} ms, difflib {dl:.1f} ms")
