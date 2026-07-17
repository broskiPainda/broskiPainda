const DIMENSION_LABELS = {
  power_asymmetry: "Power asymmetry",
  alliance_architecture: "Alliance architecture",
  domestic_constraints: "Domestic constraints",
  geography: "Geography",
  time_pressure: "Time pressure",
  information_environment: "Information environment",
  escalation_position: "Escalation position",
  economic_interdependence: "Economic interdependence",
  third_party_involvement: "Third-party involvement",
  regime_types: "Regime types",
  stakes_framing: "Stakes framing",
  technology_era: "Technology era",
};

export const DIMENSION_KEYS = Object.keys(DIMENSION_LABELS);

/** editable=true renders each chip as a text input; otherwise as read-only chips. */
export default function DimensionChips({ dimensions, onChange, editable = false }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      {DIMENSION_KEYS.map((key) => (
        <div key={key} className="rounded border border-parchment/20 px-3 py-2">
          <div className="text-xs uppercase tracking-wide text-parchment/50 mb-1">
            {DIMENSION_LABELS[key]}
          </div>
          {editable ? (
            <input
              className="w-full bg-transparent text-sm outline-none border-b border-transparent focus:border-parchment/40"
              value={dimensions?.[key] ?? ""}
              onChange={(e) => onChange?.(key, e.target.value)}
              placeholder="(unspecified)"
            />
          ) : (
            <div className="text-sm">{dimensions?.[key] || "(unspecified)"}</div>
          )}
        </div>
      ))}
    </div>
  );
}
