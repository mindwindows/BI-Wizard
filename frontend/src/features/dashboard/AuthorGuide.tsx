/** 지원하는 차트 6가지(08 §5). 시험과 화면이 같은 목록을 쓴다. */
export const SUPPORTED_CHARTS = ["선", "막대", "표", "큰 숫자(추세 포함)", "원형", "혼합(막대+선)"] as const;

/**
 * 차트 작성자 안내문(08 §5). 차트는 Superset에서 만들고, 만든 차트를 담은 대시보드는 관리자가 포털에 연결한다.
 */
export function AuthorGuide() {
  return (
    <details className="author-guide" data-testid="author-guide">
      <summary>차트를 만들려면 (작성자 안내)</summary>
      <ul>
        <li>
          지원하는 차트는 <strong>{SUPPORTED_CHARTS.join(", ")}</strong> 6가지입니다. 다른 유형은 대시보드에서 정상 표시되지 않을 수 있습니다.
        </li>
        <li>만들 때 쓰는 데이터셋 이름은 <strong>[팀] 이름</strong> 형식입니다(예: [영업] 월별 매출). 포털에서 데이터셋을 만들면 자동으로 이 이름으로 등록됩니다.</li>
        <li>차트에 <strong>시간 필터</strong>가 있어야 대시보드의 날짜 필터가 적용됩니다.</li>
        <li>팀별로 나누어 보려면 <strong>team</strong> 열을 쓰세요. 대시보드 필터에서 team 열로 팀을 고를 수 있습니다.</li>
        <li>일부 화면(필터 설정의 열 선택 등)에서는 내부 번호 이름이 보입니다.</li>
        <li>지표 이름은 만든 시점의 열 표시 이름으로 굳어, 나중에 열 이름을 바꿔도 기존 차트의 이름은 그대로입니다(차트는 깨지지 않습니다).</li>
        <li>Superset은 별도 로그인이 필요합니다. 차트를 다 만들었으면 관리자에게 대시보드 연결을 요청하세요.</li>
      </ul>
    </details>
  );
}
