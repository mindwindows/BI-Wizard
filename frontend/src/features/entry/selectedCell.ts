/** 그리드에서 고른 계산 열 칸. Inspector 수식 보기가 전체 값을 보여 주는 데 쓴다(값은 API가 준 십진 문자열 그대로). */
export interface SelectedCell {
  columnId: number;
  columnName: string;
  /** 저장 전 새 행이면 null */
  rowId: number | null;
  /** 기준 날짜 열 값(없으면 빈 글자) */
  period: string;
  /** 계산 오류 코드(오류 칸이면) */
  errorCode: string | null;
  /** 전체 값. 빈 값이면 null */
  full: string | null;
}
