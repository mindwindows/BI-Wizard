/** 시각 ISO 8601(+09:00)에서 날짜(YYYY-MM-DD)만 쓴다. 서버가 이미 한국 시간으로 준다(05 §1). */
export const formatDate = (iso: string): string => (typeof iso === "string" ? iso.slice(0, 10) : "");
