import { describe, expect, it } from "vitest";

// ?raw는 vitest에서 빈 문자열이라 ?inline(처리된 CSS 문자열)을 쓴다.
const files = import.meta.glob("./styles.css", { query: "?inline", import: "default", eager: true }) as Record<string, string>;
const css = files["./styles.css"] ?? "";

/** 레이아웃 규칙은 jsdom이 계산하지 못하므로 스타일 원문에서 규칙 블록을 찾아 속성을 단정한다(눈 확인은 스크린샷). */
function rule(selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const blocks = [...css.matchAll(new RegExp(`(?:^|\\n|,\\s*)${escaped}\\s*(?:,[^{]*)?\\{([^}]*)\\}`, "g"))].map((m) => m[1]);
  expect(blocks.length, `규칙 없음: ${selector}`).toBeGreaterThan(0);
  return blocks.join("\n");
}

describe("S9 동기 목록 줄바꿈", () => {
  it("배지·버튼·날짜·헤더는 줄바꿈하지 않고 표 영역이 가로 스크롤한다", () => {
    expect(rule(".sync-table th")).toContain("white-space: nowrap");
    expect(rule(".sync-table td")).toContain("white-space: nowrap");
    expect(rule(".sync-table .badge")).toContain("white-space: nowrap");
    expect(rule(".table-scroll")).toContain("overflow-x: auto");
  });
  it("데이터셋 이름과 실패 사유 칸만 어절 단위로 줄을 바꾼다", () => {
    expect(rule(".sync-table td.sync-error")).toContain("word-break: keep-all");
    expect(rule(".sync-table td.sync-name")).toContain("white-space: normal");
  });
});

describe("안내·설명 문단", () => {
  it(".muted(S9 안내 포함)는 어절 단위로 줄을 바꾸고 긴 URL·번호는 넘치지 않게 꺾는다", () => {
    const muted = rule(".muted");
    expect(muted).toContain("word-break: keep-all");
    expect(muted).toContain("overflow-wrap: anywhere");
  });
  it("S8 폼 문단과 인라인 오류도 같은 규칙이다", () => {
    for (const selector of [".panel-form p", ".state-error-inline"]) {
      const block = rule(selector);
      expect(block, selector).toContain("word-break: keep-all");
      expect(block, selector).toContain("overflow-wrap: anywhere");
    }
  });
});

describe("S8 폼 문구", () => {
  it("오류 문구는 어절 단위로 줄을 바꾸고 폼 폭이 넓다", () => {
    expect(rule(".state-error-inline")).toContain("word-break: keep-all");
    expect(rule(".panel-form")).toMatch(/max-width:\s*(7\d\d|[89]\d\d)px/);
  });
});

describe("개발용 신원 선택 상자", () => {
  it("내용 폭 그대로 두어 잘리지 않는다", () => {
    const select = rule(".stub-switcher select");
    expect(select).toContain("width: max-content");
    expect(select).toContain("max-width: none");
    expect(rule(".stub-switcher")).toContain("white-space: nowrap");
  });
});

describe("S7 임베드 높이", () => {
  it("앱 높이를 뷰포트에 맞추고 임베드가 남는 높이를 채운다(고정 px 높이 없음)", () => {
    expect(rule(".app:has(.dashboards-page)")).toContain("height: 100vh");
    expect(rule(".app:has(.dashboards-page) > .content")).toContain("overflow: auto");
    const frame = rule(".embed-frame");
    expect(frame).toContain("flex: 1 1 auto");
    expect(frame).not.toMatch(/calc\(100vh|min-height:\s*720px/);
    expect(rule(".dashboard-list")).not.toContain("100vh");
  });
});

describe("S7 작성자 안내문 코드 표기", () => {
  it("코드 조각은 줄 중간에서 갈라지지 않고 문장은 어절 단위로 줄을 바꾼다", () => {
    expect(rule(".author-guide code")).toContain("white-space: nowrap");
    expect(rule(".author-guide ul")).toContain("word-break: keep-all");
  });
});
