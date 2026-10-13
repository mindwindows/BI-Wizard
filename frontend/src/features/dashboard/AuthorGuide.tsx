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
        <li data-testid="number-format-guide">
          <strong>숫자를 소수 몇 자리로 보이게 하려면:</strong> 차트마다 지정하는 곳이 다릅니다. 선·막대·혼합 차트는 차트 설정의 <code>y_axis_format</code>(혼합 차트는 보조 축도 따로), 큰 숫자 차트도 <code>y_axis_format</code>, 원형 차트는 <code>number_format</code>, 표 차트는 열 설정(<code>column_config</code>)에서 열마다 형식을 정합니다. 형식은 <code>,.2f</code>(쉼표 + 소수 2자리)처럼 쓰고, 소수는 최대 6자리까지(<code>,.6~f</code>는 끝의 0을 뺀 최대 6자리) 지정할 수 있습니다. 지정하지 않은 Superset 기본 표시는 포털 그리드 규칙(소수 6자리, 쉼표)과 다릅니다. 데이터베이스에 저장된 값의 전체 자릿수는 약 16자리에서 끊깁니다.
        </li>
        <li>Superset은 별도 로그인이 필요합니다. 차트를 다 만들었으면 관리자에게 대시보드 연결을 요청하세요.</li>
      </ul>
    </details>
  );
}
