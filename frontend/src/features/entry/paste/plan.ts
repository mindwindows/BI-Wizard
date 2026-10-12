import type { Column } from "../../dataset/types";
import type { PasteRequest, PasteRow, Row } from "../types";
import { pasteCellValue } from "../values";

/** 05 C4 요청 상한(승인 A): 5,000행, 요청 본문 1MiB. 서버가 다시 검증한다. */
export const MAX_PASTE_ROWS = 5000;
export const MAX_PASTE_BYTES = 1024 * 1024;

export interface PasteInput {
  /** 파서 결과(행 x 열 문자열) */
  matrix: string[][];
  /** 화면에 보이는 열(위치 순, 계산 열 포함) */
  columns: Column[];
  /** 현재 쪽의 저장된 행(화면 순서) */
  savedRows: Row[];
  /** 붙여넣기 시작 행: 저장된 행의 순번, null이면 새 행 영역(맨 아래 입력 줄·임시 행)에서 시작 */
  startRow: number | null;
  /** 붙여넣기 시작 열: columns 안의 순번 */
  startColumn: number;
  /** 이 쪽이 마지막 쪽인가(끝을 넘는 줄을 새 행으로 만들 수 있는 조건) */
  isLastPage: boolean;
  baseDateColumnId: number | null;
  expectedVersion: number;
}

export interface PasteProblem {
  /** 붙여넣은 내용의 줄 번호(1부터). 줄과 무관하면 없음 */
  line?: number;
  column?: string;
  message: string;
}

export interface PastePlan {
  request: PasteRequest;
  columnNames: string[];
  existingRows: number;
  newRows: number;
  /** request.rows[i]가 가리키는 저장된 행의 순번(새 행이면 null) */
  rowSlots: (number | null)[];
}

export type PasteBuild = { ok: true; plan: PastePlan } | { ok: false; problems: PasteProblem[] };

const MAX_REPORTED = 20;

export function utf8Length(text: string): number {
  return new TextEncoder().encode(text).length;
}

/**
 * 붙여넣기 요청(C4)을 만든다. 저장하지 않고 서버에 보낼 내용과 확인창에 보여 줄 요약만 계산한다.
 * - 현재 선택 칸부터 아래/오른쪽으로 채운다. 쪽 끝을 넘는 줄은 마지막 쪽에서만 새 행(row_id=null)이 된다.
 * - 기존 행은 row_id와 화면 이전 값(expected[])을 싣고, 값은 문자열|null 그대로 보낸다.
 * - 서버 호출 전에 막는 것: 5,000행/1MiB 초과, 계산 열·기존 행의 기준 날짜 열 변경(같은 값은 통과)·새 행의 기준 날짜 열 누락, 열/행 부족, 칸 수가 모자란 기존 행, 모호한 숫자·날짜.
 */
export function buildPastePlan(input: PasteInput): PasteBuild {
  const { matrix, columns, savedRows, startRow, startColumn } = input;
  if (matrix.length === 0) return { ok: false, problems: [{ message: "붙여넣을 내용이 없습니다." }] };
  if (matrix.length > MAX_PASTE_ROWS) {
    return {
      ok: false,
      problems: [{ message: `한 번에 ${MAX_PASTE_ROWS.toLocaleString("ko-KR")}행까지만 붙여넣을 수 있습니다(지금 ${matrix.length.toLocaleString("ko-KR")}행). 나누어 붙여 주세요.` }],
    };
  }
  const width = Math.max(...matrix.map((row) => row.length));
  if (startColumn < 0 || startColumn + width > columns.length) {
    return {
      ok: false,
      problems: [
        {
          message: `붙여넣을 열이 모자랍니다. 선택한 칸부터 오른쪽에 열이 ${Math.max(0, columns.length - startColumn)}개 있는데 ${width}개 열을 붙이려 합니다. 시작 칸을 더 왼쪽으로 옮겨 주세요.`,
        },
      ],
    };
  }
  const targets = columns.slice(startColumn, startColumn + width);
  const problems: PasteProblem[] = [];
  const formulaNames = targets.filter((c) => c.kind === "formula").map((c) => c.display_name);
  if (formulaNames.length > 0) {
    problems.push({ message: `계산 열에는 붙여넣을 수 없습니다(${formulaNames.join(", ")}). 입력 열만 걸치도록 시작 칸을 옮겨 주세요.` });
  }

  const firstNew = startRow === null ? 0 : savedRows.length - startRow; // 이 줄부터 새 행
  const overflowsPage = startRow !== null && startRow + matrix.length > savedRows.length;
  if (startRow !== null && startRow >= savedRows.length) {
    problems.push({ message: "붙여넣기 시작 칸이 이 쪽의 행 밖에 있습니다." });
  }
  if (overflowsPage && !input.isLastPage) {
    problems.push({
      message: `이 쪽의 남은 행(${savedRows.length - (startRow ?? 0)}개)보다 많은 ${matrix.length}줄을 붙이려 합니다. 새 행은 마지막 쪽에서만 추가할 수 있습니다. 마지막 쪽으로 이동하거나 줄 수를 줄여 주세요.`,
    });
  }
  if (problems.length > 0) return { ok: false, problems };

  const rows: PasteRow[] = [];
  const rowSlots: (number | null)[] = [];
  let existingRows = 0;
  matrix.forEach((cells, offset) => {
    const isNew = startRow === null || offset >= firstNew;
    const line = offset + 1;
    const saved = isNew ? null : savedRows[(startRow as number) + offset];
    if (saved && cells.length < width) {
      problems.push({
        line,
        message: `${line}번째 줄의 칸 수(${cells.length}개)가 다른 줄(${width}개)보다 적어 기존 행의 빈 칸을 지울 수 있습니다. 칸 수를 맞춰 다시 복사해 주세요.`,
      });
    }
    if (!saved && input.baseDateColumnId !== null) {
      // 새 행에는 기준 날짜 열 값이 필요하다(서버 REQUIRED와 같은 취지로 확인창 전에 안내한다).
      const at = targets.findIndex((t) => t.id === input.baseDateColumnId);
      if (at < 0 || (cells[at] ?? "").trim() === "") {
        problems.push({ line, message: `${line}번째 줄: 새 행에는 기준 열 값이 필요합니다. 기준 날짜 열이 함께 붙도록 시작 칸을 옮기거나 값을 채워 주세요.` });
      }
    }
    const values: (string | null)[] = [];
    for (let c = 0; c < width; c += 1) {
      const column = targets[c];
      const text = cells[c];
      if (text === undefined) {
        values.push(null); // 새 행의 모자란 칸은 미입력
        continue;
      }
      if (saved && column.id === input.baseDateColumnId) {
        // 05 C4: 서버는 저장된 값과 같은 값은 무시하고 '바꾸려 할 때'만 거부한다. 같은 값이면 그대로 통과시킨다.
        // 서버 값 표현은 YYYY-MM-DD이므로 앞뒤 공백만 뺀 글자를 정확 비교한다.
        const savedValue = saved.cells[String(column.id)];
        if (typeof savedValue === "string" && text.trim() === savedValue) {
          values.push(savedValue);
          continue;
        }
        problems.push({
          line,
          column: column.display_name,
          message: `기존 행의 기간(${column.display_name})은 붙여넣기로 바꿀 수 없습니다(저장된 값과 같으면 그대로 둡니다). 칸을 직접 고치거나 새 행으로 붙여 주세요.`,
        });
        values.push(null);
        continue;
      }
      if (!saved && column.id === input.baseDateColumnId && text.trim() === "") {
        values.push(null); // 위에서 이미 '기준 열 값이 필요합니다'로 안내했다
        continue;
      }
      const parsed = pasteCellValue(column, text);
      if (parsed.ok) values.push(parsed.value);
      else problems.push({ line, column: column.display_name, message: parsed.message });
    }
    if (saved) {
      existingRows += 1;
      rows.push({ row_id: saved.row_id, expected: targets.map((c) => saved.cells[String(c.id)] ?? null), values });
      rowSlots.push((startRow as number) + offset);
    } else {
      rows.push({ row_id: null, values });
      rowSlots.push(null);
    }
  });
  if (problems.length > 0) return { ok: false, problems: problems.slice(0, MAX_REPORTED) };

  const request: PasteRequest = { expected_version: input.expectedVersion, column_ids: targets.map((c) => c.id), rows };
  if (utf8Length(JSON.stringify(request)) > MAX_PASTE_BYTES) {
    return { ok: false, problems: [{ message: "붙여넣을 내용이 너무 커서(1MiB 초과) 보낼 수 없습니다. 나누어 붙여 주세요." }] };
  }
  return {
    ok: true,
    plan: { request, columnNames: targets.map((c) => c.display_name), existingRows, newRows: rows.length - existingRows, rowSlots },
  };
}
