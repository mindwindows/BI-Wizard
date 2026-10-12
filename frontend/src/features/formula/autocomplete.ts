import type { Column } from "../dataset/types";
import type { FormulaErrorItem, FunctionInfo } from "./types";

/** 자동완성이 열려야 하는 자리: 함수 이름 / `[` 안의 열 이름 / SUMTAG("…") 안의 태그. */
export interface CompletionContext {
  kind: "function" | "column" | "tag";
  /** 바꿀 범위 [from, to) */
  from: number;
  to: number;
  /** 사용자가 지금까지 친 글자 */
  query: string;
}

const IDENT_TAIL = /[A-Za-z_][A-Za-z0-9_]*$/;

/**
 * 커서(caret) 위치의 자동완성 자리를 찾는다. 글자 상수 `"…"`(안의 `""`은 따옴표 하나)와 열 참조 `[…]` 안을 구별한다.
 * 함수 이름은 한 글자 이상 쳤을 때만, 열 이름은 `[`를 치자마자, 태그는 `SUMTAG("` 안에서만 연다.
 */
export function completionContext(textValue: string, caret: number): CompletionContext | null {
  const end = Math.max(0, Math.min(caret, textValue.length));
  let inString = false;
  let stringStart = -1;
  let inBracket = false;
  let bracketStart = -1;
  for (let i = 0; i < end; i += 1) {
    const ch = textValue[i];
    if (inString) {
      if (ch === '"') {
        if (textValue[i + 1] === '"' && i + 1 < end) i += 1;
        else inString = false;
      }
    } else if (inBracket) {
      if (ch === "]") inBracket = false;
    } else if (ch === '"') {
      inString = true;
      stringStart = i;
    } else if (ch === "[") {
      inBracket = true;
      bracketStart = i;
    }
  }
  if (inBracket) {
    return { kind: "column", from: bracketStart, to: end + (textValue[end] === "]" ? 1 : 0), query: textValue.slice(bracketStart + 1, end) };
  }
  if (inString) {
    if (!/SUMTAG\s*\(\s*$/i.test(textValue.slice(0, stringStart))) return null;
    return { kind: "tag", from: stringStart, to: end + (textValue[end] === '"' ? 1 : 0), query: textValue.slice(stringStart + 1, end) };
  }
  const match = IDENT_TAIL.exec(textValue.slice(0, end));
  if (!match) return null;
  const from = end - match[0].length;
  const before = textValue[from - 1];
  if (before !== undefined && /[0-9.]/.test(before)) return null; // 1E5 같은 숫자의 일부
  return { kind: "function", from, to: end, query: match[0] };
}

export interface Suggestion {
  kind: "function" | "column" | "tag";
  /** 목록에 보이는 이름 */
  label: string;
  /** 보조 설명(함수 모양, 열 종류) */
  detail: string;
  /** 수식에 넣는 글자 */
  insert: string;
  fn?: FunctionInfo;
}

const MAX_SUGGESTIONS = 8;

const norm = (value: string) => value.normalize("NFC").toLowerCase();

/** 앞부분이 같은 것을 먼저, 그다음 포함하는 것 */
function rank<T>(items: T[], name: (item: T) => string, query: string): T[] {
  const q = norm(query);
  const starts: T[] = [];
  const contains: T[] = [];
  for (const item of items) {
    const n = norm(name(item));
    if (q === "" || n.startsWith(q)) starts.push(item);
    else if (n.includes(q)) contains.push(item);
  }
  return [...starts, ...contains].slice(0, MAX_SUGGESTIONS);
}

export function suggestFunctions(functions: FunctionInfo[], query: string): Suggestion[] {
  return rank(functions, (f) => f.name, query).map((fn) => ({ kind: "function", label: fn.name, detail: fn.signature, insert: fn.name, fn }));
}

export function suggestColumns(columns: Column[], query: string): Suggestion[] {
  return rank(columns, (c) => c.display_name, query).map((c) => ({
    kind: "column",
    label: c.display_name,
    detail: c.kind === "formula" ? "계산 열" : "입력 열",
    insert: c.display_name,
  }));
}

export function suggestTags(columns: Column[], query: string): Suggestion[] {
  const tags = [...new Set(columns.map((c) => c.tag).filter((t): t is string => typeof t === "string" && t !== ""))];
  return rank(tags, (t) => t, query).map((tag) => ({ kind: "tag", label: tag, detail: "구분 태그", insert: tag }));
}

export function suggestionsFor(context: CompletionContext | null, functions: FunctionInfo[], columns: Column[]): Suggestion[] {
  if (!context) return [];
  if (context.kind === "function") return context.query === "" ? [] : suggestFunctions(functions, context.query);
  if (context.kind === "column") return suggestColumns(columns, context.query);
  return suggestTags(columns, context.query);
}

export interface Edited {
  text: string;
  caret: number;
}

/** 범위 [from, to)를 insert로 바꾼다. 커서는 넣은 글자 바로 뒤. */
export function replaceRange(textValue: string, from: number, to: number, insert: string): Edited {
  return { text: textValue.slice(0, from) + insert + textValue.slice(to), caret: from + insert.length };
}

/** 고른 제안을 수식에 넣는다. 함수는 `NAME(`(이미 `(`가 뒤에 있으면 이름만), 열은 `[이름]`, 태그는 `"태그"`. */
export function applySuggestion(textValue: string, context: CompletionContext, suggestion: Suggestion): Edited {
  if (suggestion.kind === "function") {
    const hasParen = textValue[context.to] === "(";
    const edited = replaceRange(textValue, context.from, context.to, suggestion.insert + (hasParen ? "" : "("));
    return hasParen ? { ...edited, caret: edited.caret + 1 } : edited;
  }
  if (suggestion.kind === "column") return replaceRange(textValue, context.from, context.to, `[${suggestion.insert}]`);
  return replaceRange(textValue, context.from, context.to, `"${suggestion.insert}"`);
}

/**
 * 열 이름 칩: 선택 범위에 `[열 이름]`을 넣는다. 커서가 열린 `[` 안에 있고 선택이 없으면 그 `[…`을 이어서 완성한다.
 */
export function insertColumnRef(textValue: string, selStart: number, selEnd: number, name: string): Edited {
  if (selStart === selEnd) {
    const context = completionContext(textValue, selStart);
    if (context?.kind === "column") return replaceRange(textValue, context.from, context.to, `[${name}]`);
  }
  return replaceRange(textValue, selStart, selEnd, `[${name}]`);
}

/** 서버 위치(파이썬 글자 위치 = 유니코드 코드포인트)를 JS 문자열 위치(UTF-16)로 바꾼다. 이모지 같은 글자가 없으면 같은 값이다. */
export function toUtf16Index(textValue: string, codePointIndex: number): number {
  if (codePointIndex <= 0) return 0;
  let units = 0;
  let count = 0;
  for (const ch of textValue) {
    if (count >= codePointIndex) break;
    units += ch.length;
    count += 1;
  }
  return units;
}

export interface MarkSegment {
  text: string;
  bad: boolean;
  /** 수식 끝(또는 길이 0 위치)을 가리키는 표시용 칸 */
  placeholder?: boolean;
}

export interface MarkedRange {
  start: number;
  end: number;
}

/** 오류 위치를 수식 길이 안으로 맞춘다. 길이 0 오류는 그 위치의 글자 하나(없으면 끝 표시)로 넓힌다. */
export function errorRanges(textValue: string, errors: FormulaErrorItem[]): { ranges: MarkedRange[]; atEnd: boolean } {
  const ranges: MarkedRange[] = [];
  let atEnd = false;
  for (const error of errors) {
    const start = Math.min(toUtf16Index(textValue, error.start), textValue.length);
    let end = Math.max(start, Math.min(toUtf16Index(textValue, error.end), textValue.length));
    if (end === start) {
      if (start < textValue.length) end = start + 1;
      else atEnd = true;
    }
    if (end > start) ranges.push({ start, end });
  }
  return { ranges, atEnd };
}

/** 수식을 오류 부분과 나머지로 나눈다(겹치는 오류는 합친다). 길이 0 오류가 수식 끝이면 끝 표시 칸을 붙인다. */
export function markSegments(textValue: string, errors: FormulaErrorItem[]): MarkSegment[] {
  const { ranges, atEnd } = errorRanges(textValue, errors);
  const flags = new Array<boolean>(textValue.length).fill(false);
  for (const range of ranges) for (let i = range.start; i < range.end; i += 1) flags[i] = true;
  const out: MarkSegment[] = [];
  let i = 0;
  while (i < textValue.length) {
    let j = i;
    while (j < textValue.length && flags[j] === flags[i]) j += 1;
    out.push({ text: textValue.slice(i, j), bad: flags[i] });
    i = j;
  }
  if (atEnd) out.push({ text: " ", bad: true, placeholder: true });
  return out;
}
