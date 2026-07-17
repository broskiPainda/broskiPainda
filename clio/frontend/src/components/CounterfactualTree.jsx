const PLAUSIBILITY_COLOR = {
  low: "text-parchment/40",
  medium: "text-amber-300",
  high: "text-emerald-300",
};

export default function CounterfactualTree({ counterfactuals }) {
  if (!counterfactuals || counterfactuals.length === 0) {
    return <p className="text-sm text-parchment/50 italic">No counterfactual branches generated.</p>;
  }

  return (
    <div className="space-y-2">
      {counterfactuals.map((cf, i) => (
        <details key={i} className="border border-parchment/15 rounded px-3 py-2">
          <summary className="cursor-pointer text-sm flex items-center justify-between gap-2">
            <span>{cf.changed_variable}</span>
            <span className={`text-xs uppercase ${PLAUSIBILITY_COLOR[cf.plausibility] || ""}`}>
              {cf.plausibility} plausibility
            </span>
          </summary>
          <p className="text-sm text-parchment/80 mt-2">{cf.narrative}</p>
          {cf.key_assumptions?.length > 0 && (
            <ul className="mt-2 text-xs text-parchment/60 list-disc list-inside">
              {cf.key_assumptions.map((a, j) => (
                <li key={j}>{a}</li>
              ))}
            </ul>
          )}
        </details>
      ))}
    </div>
  );
}
