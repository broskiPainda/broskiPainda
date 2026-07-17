import MachineGeneratedBadge from "./MachineGeneratedBadge.jsx";
import RadarChart from "./RadarChart.jsx";
import { DIMENSION_KEYS } from "./DimensionChips.jsx";

/** matched: MatchedCase (case_id, similarity_score, matched_dimensions, mismatched_dimensions, is_negative_analogue)
 *  caseData: full StructuredCase, may be null while loading */
export default function AnalogueCard({ matched, caseData }) {
  const matchedSet = new Set(matched.matched_dimensions || []);
  const radarDims = DIMENSION_KEYS.map((key) => ({ key, matched: matchedSet.has(key) }));

  return (
    <div
      className={`rounded border p-4 ${
        matched.is_negative_analogue ? "border-red-400/50 bg-red-950/10" : "border-parchment/20"
      }`}
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div>
          <h3 className="font-display text-lg">{caseData?.name || "Loading…"}</h3>
          {caseData && <p className="text-xs text-parchment/50">{caseData.era} · {caseData.dates}</p>}
        </div>
        <div className="text-right shrink-0">
          <div className="text-sm font-mono">{Math.round(matched.similarity_score * 100)}%</div>
          <div className="text-[10px] text-parchment/50">similarity</div>
        </div>
      </div>

      {matched.is_negative_analogue && (
        <div className="text-xs uppercase tracking-wide text-red-300 mb-2">Negative analogue</div>
      )}

      {caseData && <p className="text-sm text-parchment/80 mb-3">{caseData.summary}</p>}

      <RadarChart dimensions={radarDims} />

      <div className="mt-3 space-y-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-parchment/50 mb-1">Matched dimensions</div>
          <div className="flex flex-wrap gap-1">
            {(matched.matched_dimensions || []).map((d) => (
              <span key={d} className="text-xs rounded-full border border-emerald-400/40 text-emerald-300 px-2 py-0.5">
                {d.replace(/_/g, " ")}
              </span>
            ))}
            {(matched.matched_dimensions || []).length === 0 && (
              <span className="text-xs text-parchment/40">none</span>
            )}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wide text-parchment/50 mb-1">
            Where this analogy breaks down
          </div>
          <div className="flex flex-wrap gap-1">
            {(matched.mismatched_dimensions || []).map((d) => (
              <span key={d} className="text-xs rounded-full border border-amber-400/40 text-amber-300 px-2 py-0.5">
                {d.replace(/_/g, " ")}
              </span>
            ))}
            {(matched.mismatched_dimensions || []).length === 0 && (
              <span className="text-xs text-parchment/40">none</span>
            )}
          </div>
        </div>
      </div>

      {caseData?.source_urls?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {caseData.source_urls.map((url) => (
            <a
              key={url}
              href={url}
              target="_blank"
              rel="noreferrer"
              className="text-xs underline text-parchment/60 hover:text-parchment"
            >
              source
            </a>
          ))}
        </div>
      )}

      <div className="mt-3">
        <MachineGeneratedBadge />
      </div>
    </div>
  );
}
