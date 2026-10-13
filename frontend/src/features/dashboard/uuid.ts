const CANONICAL = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** 붙여넣은 번호의 앞뒤 공백을 지우고 소문자로 바꾼다. 서버는 소문자 36자 정규형만 받는다(E4). */
export function normalizeEmbeddedUuid(text: string): string {
  return text.trim().toLowerCase();
}

/** 소문자 36자 정규형(하이픈 포함)인지. 입력은 normalizeEmbeddedUuid를 거친 값. */
export function isCanonicalUuid(text: string): boolean {
  return CANONICAL.test(text);
}

export const UUID_FORMAT_HELP = "임베드 번호는 하이픈이 있는 36자(예: 1a2b3c4d-1234-5678-9abc-0123456789ab)여야 합니다.";
