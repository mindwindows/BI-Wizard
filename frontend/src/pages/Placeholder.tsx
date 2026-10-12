import { useParams } from "react-router-dom";

/** 후속 단위에서 채우는 화면의 자리표시. */
export function Placeholder({ screen, title, unit }: { screen: string; title: string; unit: string }) {
  const params = useParams();
  const paramText = Object.entries(params)
    .map(([key, value]) => `${key}=${value}`)
    .join(", ");
  return (
    <section data-testid={`screen-${screen}`}>
      <h1>
        {screen} {title}
      </h1>
      <p className="muted">아직 구현되지 않았습니다({unit}에서 채웁니다).</p>
      {paramText ? <p className="muted">{paramText}</p> : null}
    </section>
  );
}
