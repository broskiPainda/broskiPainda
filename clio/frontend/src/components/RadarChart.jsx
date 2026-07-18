const SIZE = 180;
const CENTER = SIZE / 2;
const RADIUS = SIZE / 2 - 24;

function pointFor(index, total, value) {
  const angle = (Math.PI * 2 * index) / total - Math.PI / 2;
  const r = RADIUS * value;
  return [CENTER + r * Math.cos(angle), CENTER + r * Math.sin(angle)];
}

/** dimensions: array of {key, matched: boolean}. Renders a 12-axis radar with matched=1, mismatched=0.3. */
export default function RadarChart({ dimensions }) {
  const total = dimensions.length;
  const points = dimensions.map((d, i) => pointFor(i, total, d.matched ? 1 : 0.3));
  const polygon = points.map((p) => p.join(",")).join(" ");
  const rings = [0.33, 0.66, 1];

  return (
    <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} className="mx-auto">
      {rings.map((r) => (
        <circle
          key={r}
          cx={CENTER}
          cy={CENTER}
          r={RADIUS * r}
          fill="none"
          stroke="currentColor"
          strokeOpacity={0.15}
        />
      ))}
      {dimensions.map((d, i) => {
        const [x, y] = pointFor(i, total, 1);
        return (
          <line key={d.key} x1={CENTER} y1={CENTER} x2={x} y2={y} stroke="currentColor" strokeOpacity={0.15} />
        );
      })}
      <polygon points={polygon} fill="currentColor" fillOpacity={0.25} stroke="currentColor" strokeWidth={1.5} />
      {points.map((p, i) => (
        <circle key={`pt-${dimensions[i].key}`} cx={p[0]} cy={p[1]} r={2.5} fill="currentColor" />
      ))}
      <title>
        {dimensions.map((d) => `${d.key}: ${d.matched ? "matched" : "mismatched"}`).join(", ")}
      </title>
    </svg>
  );
}
