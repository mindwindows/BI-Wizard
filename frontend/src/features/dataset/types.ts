/** 05 §1 공통 형태(Column·Dataset)와 §2-2(B1~B6) 응답 형태. 계약에 없는 필드는 가정하지 않는다. */
export type DateUnit = "day" | "month" | "year";
export type ColumnType = "text" | "number" | "date" | "boolean" | "choice";
export type ColumnKind = "raw" | "formula";

export const DATE_UNIT_LABELS: Record<DateUnit, string> = { day: "일", month: "월", year: "연" };
export const DATE_UNITS: DateUnit[] = ["day", "month", "year"];

export const COLUMN_TYPE_LABELS: Record<ColumnType, string> = {
  text: "글자",
  number: "숫자",
  date: "날짜",
  boolean: "예/아니오",
  choice: "선택 목록",
};
export const COLUMN_TYPES: ColumnType[] = ["text", "number", "date", "boolean", "choice"];
export const COLUMN_KIND_LABELS: Record<ColumnKind, string> = { raw: "입력 열", formula: "계산 열" };

/** 05 §1 이름 규칙: 데이터셋 이름 100자, 열 이름 100자. 열 구분 태그는 06 §3-3에 따라 50자. */
export const DATASET_NAME_MAX = 100;
export const COLUMN_NAME_MAX = 100;
export const TAG_MAX = 50;

/**
 * 05 공통 형태 Column.rules. number {min, max, decimals} / text {max_length} / date {min, max} / choice {options[]}.
 * number의 min·max는 05 §1에 따라 십진 문자열로 보낸다(읽을 때는 숫자도 받아 문자열로 바꾼다).
 */
export type ColumnRules = Record<string, unknown>;

export interface Column {
  id: number;
  display_name: string;
  type: ColumnType;
  kind: ColumnKind;
  required: boolean;
  rules: ColumnRules | null;
  tag: string | null;
  position: number;
}

/** 05 §1 Dataset.status (FU-2b). 화면 용어: active = "사용 중", archived = "보관됨". */
export type DatasetStatus = "active" | "archived";
export const DATASET_STATUS_LABELS: Record<DatasetStatus, string> = { active: "사용 중", archived: "보관됨" };

export interface Dataset {
  id: number;
  team_id: number;
  name: string;
  date_unit: DateUnit;
  base_date_column_id: number | null;
  status: DatasetStatus;
  def_version: number;
  created_by: { id: number; display_name: string };
  created_at: string;
}

export interface DatasetDetail extends Dataset {
  team: { id: number; code: string; name: string };
  columns: Column[];
  permissions: { define: boolean; enter: boolean };
}

/** B5·B6 응답 */
export interface ColumnSaved {
  column: Column;
  def_version: number;
}
