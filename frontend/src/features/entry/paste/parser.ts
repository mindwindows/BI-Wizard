/**
 * 엑셀 붙여넣기 파서(07 §9 규칙 ①~⑦). 입력은 클립보드 text/plain뿐이고, 상태 기계로 새로 작성했다(참고 코드 이식 없음).
 * 문자열 2차원 배열만 돌려주며 숫자·날짜 해석은 하지 않는다(규칙 ⑥).
 *
 * ① 행 구분은 따옴표 밖의 \r\n, \n, 단독 \r. 끝 구분자 하나는 무시하고 빈 중간 행은 보존한다.
 * ② `"`로 시작하면 따옴표 셀: `""`는 `"`, 닫는 `"` 뒤가 탭·줄바꿈·입력 끝일 때만 닫힘. 안의 탭·줄바꿈은 내용이고 \r\n은 \n이 된다.
 * ③ 닫힘 조건이 안 맞으면 셀 시작으로 되돌려 따옴표 없는 셀로 다시 읽는다(셀마다 1회).
 * ④ 되돌림 없이 끝까지 안 닫히면 붙여넣기를 거부한다.
 * ⑤ 공백을 자르지 않고, NUL이 있으면 거부하고, 행마다 셀 수가 달라도 허용한다.
 */
export type ParseError = "NUL" | "UNCLOSED_QUOTE" | "TOO_LARGE";

/**
 * 파싱 전 입력 크기 상한(문자 수). 요청 상한은 1MiB(바이트)이지만 여기서는 UTF-16 문자 수를 세므로,
 * 4배(4Mi 문자)를 넘는 입력은 어떻게 해도 요청 상한을 넘는 것으로 보고 파싱 없이 거부한다(계획 단계가 정확한 바이트 검사를 다시 한다).
 */
export const MAX_PARSE_CHARS = 4 * 1024 * 1024;

export type ParseResult = { ok: true; rows: string[][] } | { ok: false; error: ParseError; message: string };

export const PARSE_MESSAGES: Record<ParseError, string> = {
  NUL: "붙여넣은 내용에 읽을 수 없는 문자(NUL)가 들어 있어 붙여넣지 않았습니다. 엑셀에서 다시 복사해 주세요.",
  TOO_LARGE: "붙여넣은 내용이 너무 커서(1MiB 초과) 붙여넣지 않았습니다. 나누어 복사해 주세요.",
  UNCLOSED_QUOTE: "따옴표가 닫히지 않아 붙여넣지 않았습니다. 엑셀에서 다시 복사해 주세요.",
};

const TAB = "\t";
const LF = "\n";
const CR = "\r";
const QUOTE = '"';

type Ending = "tab" | "eol" | "eof";

interface CellRead {
  value: string;
  ending: Ending;
  next: number;
}

/** 따옴표 없는 셀을 start부터 읽는다. */
function readPlain(text: string, start: number): CellRead {
  let i = start;
  while (i < text.length) {
    const ch = text[i];
    if (ch === TAB) return { value: text.slice(start, i), ending: "tab", next: i + 1 };
    if (ch === LF) return { value: text.slice(start, i), ending: "eol", next: i + 1 };
    if (ch === CR) return { value: text.slice(start, i), ending: "eol", next: text[i + 1] === LF ? i + 2 : i + 1 };
    i += 1;
  }
  return { value: text.slice(start), ending: "eof", next: text.length };
}

/** 따옴표 셀(text[start] === '"')을 읽는다. 닫힘 조건이 안 맞으면 "backtrack", 끝까지 안 닫히면 "unclosed". */
function readQuoted(text: string, start: number): CellRead | "backtrack" | "unclosed" {
  let out = "";
  let i = start + 1;
  while (i < text.length) {
    const ch = text[i];
    if (ch === QUOTE) {
      const after = text[i + 1];
      if (after === QUOTE) {
        out += QUOTE;
        i += 2;
        continue;
      }
      if (after === undefined) return { value: out, ending: "eof", next: text.length };
      if (after === TAB) return { value: out, ending: "tab", next: i + 2 };
      if (after === LF) return { value: out, ending: "eol", next: i + 2 };
      if (after === CR) return { value: out, ending: "eol", next: text[i + 2] === LF ? i + 3 : i + 2 };
      return "backtrack";
    }
    if (ch === CR && text[i + 1] === LF) {
      out += LF;
      i += 2;
      continue;
    }
    out += ch;
    i += 1;
  }
  return "unclosed";
}

export function parsePaste(text: string): ParseResult {
  if (text.length > MAX_PARSE_CHARS) return { ok: false, error: "TOO_LARGE", message: PARSE_MESSAGES.TOO_LARGE };
  if (text.includes("\u0000")) return { ok: false, error: "NUL", message: PARSE_MESSAGES.NUL };
  if (text === "") return { ok: true, rows: [] };

  const rows: string[][] = [];
  let row: string[] = [];
  let pos = 0;
  for (;;) {
    let cell: CellRead;
    if (text[pos] === QUOTE) {
      const quoted = readQuoted(text, pos);
      if (quoted === "unclosed") return { ok: false, error: "UNCLOSED_QUOTE", message: PARSE_MESSAGES.UNCLOSED_QUOTE };
      cell = quoted === "backtrack" ? readPlain(text, pos) : quoted;
    } else {
      cell = readPlain(text, pos);
    }
    row.push(cell.value);
    pos = cell.next;
    if (cell.ending === "tab") continue;
    rows.push(row);
    row = [];
    // 끝 구분자 하나는 무시한다(그 뒤에 빈 행을 만들지 않음).
    if (cell.ending === "eof" || pos >= text.length) break;
  }
  return { ok: true, rows };
}

/** 시험용 직렬화: 엑셀 방식(탭·줄바꿈·따옴표가 있는 셀만 `"`로 감싸고 안의 `"`는 `""`). */
export function serializePaste(rows: string[][], newline: "\r\n" | "\n" = "\r\n"): string {
  return rows
    .map((cells) => cells.map((cell) => (/["\t\r\n]/.test(cell) ? `"${cell.replaceAll('"', '""')}"` : cell)).join(TAB) + newline)
    .join("");
}
