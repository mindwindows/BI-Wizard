/** 05 §2-8 기준값 R1~R6 형태. 계약에 없는 필드는 가정하지 않는다. */
export interface UserRef {
  id: number;
  display_name: string;
}

/** R1·R2 */
export interface ReferenceItem {
  id: number;
  name: string;
  description: string | null;
  value_count: number;
  /** 값이 없으면 둘 다 null */
  year_min: number | null;
  year_max: number | null;
  created_by: UserRef;
  created_at: string;
}

/** R3·R4. value는 십진 문자열이다(05 §1). */
export interface ReferenceValue {
  id: number;
  item_id: number;
  year: number;
  value: string;
  created_by: UserRef;
  created_at: string;
}

/** R5 응답 */
export interface ReferenceCorrection {
  value: ReferenceValue;
  previous_value: string;
  changed: boolean;
}

/** R6 항목 */
export interface ReferenceUsageItem {
  dataset_id: number;
  dataset_name: string;
  team_id: number;
  team_name: string;
  status: string;
  column_count: number;
}

export interface ReferenceUsage {
  items: ReferenceUsageItem[];
  total: number;
  truncated: boolean;
}

export interface ReferencePage<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

/** 05 §1 이름 규칙: 항목 이름 50자, 설명 200자. 연도 범위는 R4(1900~9999). */
export const REFERENCE_NAME_MAX = 50;
export const REFERENCE_DESCRIPTION_MAX = 200;
export const YEAR_MIN = 1900;
export const YEAR_MAX = 9999;
