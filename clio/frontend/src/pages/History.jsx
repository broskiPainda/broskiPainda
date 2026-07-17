import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listHistory } from "../api.js";

const STATUS_LABELS = {
  draft: "Draft",
  confirmed: "Confirmed",
  analyzing: "Analyzing",
  complete: "Complete",
};

export default function History() {
  const [scenarios, setScenarios] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    listHistory()
      .then(setScenarios)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <section className="max-w-3xl mx-auto print:max-w-none">
      <div className="flex items-center justify-between mb-1 print:hidden">
        <h1 className="font-display text-2xl">History</h1>
        <button
          onClick={() => window.print()}
          className="text-xs border border-parchment/30 rounded px-3 py-1.5 hover:bg-parchment/10"
        >
          Export PDF
        </button>
      </div>
      <p className="text-sm text-parchment/60 mb-4 print:hidden">Past scenarios and their reports.</p>

      {loading && <p className="text-sm text-parchment/50">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!loading && scenarios.length === 0 && (
        <p className="text-sm text-parchment/50 italic">No scenarios analyzed yet.</p>
      )}

      <div className="space-y-2">
        {scenarios.map((s) => (
          <div key={s.id} className="border border-parchment/15 rounded p-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm truncate">{s.raw_text}</p>
              <p className="text-xs text-parchment/50">{STATUS_LABELS[s.status] || s.status}</p>
            </div>
            {s.status === "complete" ? (
              <Link
                to={`/analysis/${s.id}`}
                className="text-xs underline text-parchment/70 hover:text-parchment shrink-0"
              >
                view report
              </Link>
            ) : (
              <span className="text-xs text-parchment/30 shrink-0">not yet complete</span>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
