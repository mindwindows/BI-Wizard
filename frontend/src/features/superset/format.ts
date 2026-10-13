/** 시각 ISO 8601에서 날짜와 분까지만 보여 준다(서버가 한국 시간으로 준다, 05 §1). 값이 없으면 빈 문자열. */
export const formatMinute = (iso: string | null | undefined): string =>
  typeof iso === "string" && iso.length >= 16 ? iso.slice(0, 16).replace("T", " ") : (iso ?? "");
