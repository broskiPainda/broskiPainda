const AXIS_LABELS = {
  decision: "Decision quality",
  execution: "Execution",
  outcome: "Outcome",
};

/** Renders a primary case's own decision/execution/outcome assessments —
 * explicitly not an outcome prediction; decision quality is scored on
 * soundness given information available at the time. */
export default function AssessmentScores({ assessments }) {
  if (!assessments || assessments.length === 0) {
    return <p className="text-sm text-parchment/50 italic">No assessments recorded.</p>;
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {assessments.map((a) => (
        <div key={a.axis} className="border border-parchment/15 rounded p-3">
          <div className="flex items-baseline justify-between mb-1">
            <span className="text-xs uppercase tracking-wide text-parchment/50">
              {AXIS_LABELS[a.axis] || a.axis}
            </span>
            <span className="font-mono text-lg">{a.score_1_10}/10</span>
          </div>
          <p className="text-sm text-parchment/80">{a.reasoning}</p>
        </div>
      ))}
    </div>
  );
}
