import { useEffect, useState } from "react";

import { deleteCachedCase, listCachedCases } from "../api.js";
import MachineGeneratedBadge from "../components/MachineGeneratedBadge.jsx";

export default function CaseCache() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  function reload() {
    setLoading(true);
    listCachedCases()
      .then(setCases)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }

  useEffect(reload, []);

  async function handleDelete(id) {
    try {
      await deleteCachedCase(id);
      setCases((prev) => prev.filter((c) => c.id !== id));
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRegenerate(id) {
    // Regeneration = evict from cache; the next scenario that nominates this case will
    // re-fetch and re-structure it fresh (Step 3 checks the cache before hitting the network).
    await handleDelete(id);
  }

  return (
    <section className="max-w-4xl mx-auto">
      <h1 className="font-display text-2xl mb-1">Case Cache</h1>
      <p className="text-sm text-parchment/60 mb-4">
        Every case below was fetched from open sources and structured by an LLM at query time —
        nothing here is hand-curated. Verify before relying on any of it.
      </p>

      {loading && <p className="text-sm text-parchment/50">Loading…</p>}
      {error && <p className="text-sm text-red-300">{error}</p>}
      {!loading && cases.length === 0 && (
        <p className="text-sm text-parchment/50 italic">No cases cached yet — run an analysis first.</p>
      )}

      <div className="space-y-3">
        {cases.map((c) => (
          <div key={c.id} className="border border-parchment/15 rounded p-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-display text-lg">{c.name}</h2>
                <p className="text-xs text-parchment/50">{c.era} · {c.dates}</p>
              </div>
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => handleRegenerate(c.id)}
                  className="text-xs border border-parchment/30 rounded px-2 py-1 hover:bg-parchment/10"
                >
                  Regenerate
                </button>
                <button
                  onClick={() => handleDelete(c.id)}
                  className="text-xs border border-red-400/40 text-red-300 rounded px-2 py-1 hover:bg-red-950/20"
                >
                  Delete
                </button>
              </div>
            </div>
            <p className="text-sm text-parchment/80 my-2">{c.summary}</p>
            <div className="flex flex-wrap gap-2 mb-2">
              {c.source_urls.map((url) => (
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
            <MachineGeneratedBadge />
          </div>
        ))}
      </div>
    </section>
  );
}
