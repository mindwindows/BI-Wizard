"""복붙 파서 5-(a) 요구사항의 일회용 참조 구현(Python). 문서 기대값 교차 확인용이며 제품 코드가 아니다."""
class PasteError(Exception):
    pass

def parse(s: str):
    if "\x00" in s:
        raise PasteError("NUL")
    n = len(s)
    rows, row = [], []
    i = 0
    def at_row_start_eof(i): return i >= n
    while i < n:
        # 새 행 시작 (i는 행의 첫 글자)
        row = []
        while True:
            # 셀 시작 i
            cell_start = i
            if i < n and s[i] == '"':
                # 따옴표 셀 시도
                j = i + 1
                buf = []
                closed = False
                backtrack = False
                while j < n:
                    c = s[j]
                    if c == '"':
                        if j + 1 < n and s[j + 1] == '"':
                            buf.append('"'); j += 2; continue
                        nxt = s[j + 1] if j + 1 < n else None
                        if nxt is None or nxt in "\t\n\r":
                            closed = True; j += 1; break
                        backtrack = True; break
                    if c == "\r":
                        if j + 1 < n and s[j + 1] == "\n":
                            buf.append("\n"); j += 2; continue
                        buf.append("\r"); j += 1; continue
                    buf.append(c); j += 1
                if closed:
                    row.append("".join(buf)); i = j
                elif backtrack:
                    i = cell_start
                    j = i
                    while j < n and s[j] not in "\t\n\r":
                        j += 1
                    row.append(s[i:j]); i = j
                else:
                    raise PasteError("unclosed")
            else:
                j = i
                while j < n and s[j] not in "\t\n\r":
                    j += 1
                row.append(s[i:j]); i = j
            # 구분자
            if i >= n:
                rows.append(row); return rows
            c = s[i]
            if c == "\t":
                i += 1
                continue  # 다음 셀 (탭으로 끝나면 빈 셀 하나)
            # 행 끝
            if c == "\r" and i + 1 < n and s[i + 1] == "\n":
                i += 2
            else:
                i += 1
            rows.append(row)
            break
        # 다음 행: i>=n 이면 끝 (마지막 구분자 하나는 무시)
    return rows
