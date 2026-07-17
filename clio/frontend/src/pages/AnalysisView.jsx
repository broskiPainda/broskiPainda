import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getCachedCase, getReport, streamAnalysis } from "../api.js";
import AnalogueCard from "../components/AnalogueCard.jsx";
import BaseRateTable from "../components/BaseRateTable.jsx";
import CounterfactualTree from "../components/CounterfactualTree.jsx";

const STEP_NAMES = {
  2: "Nominating historical analogues",
  3: "Verifying against Wikipedia & Wikidata",
  4: "Scoring structural similarity",
  5: "Building base rates from conflict data",
  6: "Generating counterfactuals",
  7: "Synthesizing report",
};

export default function AnalysisView() {
  const { scenarioId } = useParams();
  const [log, setLog] = useState([]);
  const [report, setReport] = useState(null);
  const [cases, setCases] = useState({});
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(true);

  useEffect(() => {

    let cancelled = false;
    const controller = new AbortController();

    setLog([]);
    setReport(null);
    setCases({});
    setError(null);
    setRunning(true);

    async function run() {
      try {
        const existing = await getReport(scenarioId).catch(() => null);
        if (existing) {
          if (!cancelled) {
            setReport(existing);
            setRunning(false);
          }
          return;
        }

        for await (const evt of streamAnalysis(scenarioId, { signal: controller.signal })) {
          if (cancelled) return;
          if (evt.event === "report_ready") {
            setReport(evt.data);
          } else if (evt.event === "pipeline_error") {
            setError(evt.data.error);
          } else {
            setLog((prev) => [...prev, evt]);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setRunning(false);
      }
    }

    run();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [scenarioId]);

  useEffect(() => {
    if (!report) return;
    const idsNeeded = report.matched_cases.map((m) => m.case_id).filter((id) => !cases[id]);
    if (idsNeeded.length === 0) return;
    idsNeeded.forEach((id) => {
      getCachedCase(id)
        .then((c) => setCases((prev) => ({ ...prev, [id]: c })))
        .catch(() => {});
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report]);

  return (
    <section className="max-w-4xl mx-auto space-y-8 pb-24 print:pb-4">
      <div className="flex items-center justify-between print:hidden">
        <h1 className="font-display text-2xl">Analysis</h1>
        {report && (
          <button
            onClick={() => window.print()}
            className="text-xs border border-parchment/30 rounded px-3 py-1.5 hover:bg-parchment/10"
          >
            Export PDF
          </button>
        )}
      </div>

      {running && (
        <div className="border border-parchment/15 rounded p-4">
          <h2 className="font-display text-lg mb-2">Progress</h2>
          <ul className="text-sm space-y-1 max-h-64 overflow-y-auto">
            {log.map((evt, i) => (
              <li key={i} className="text-parchment/80">
                {evt.event === "step_started" && (
                  <span>▸ {STEP_NAMES[evt.data.step] || evt.data.name}…</span>
                )}
                {evt.event === "step_completed" && (
                  <span className="text-parchment/50">
                    ✓ {STEP_NAMES[evt.data.step] || evt.data.name} complete
                  </span>
                )}
                {evt.event === "candidate_verified" && (
                  <span className="text-emerald-300">✓ verified: {evt.data.name}</span>
                )}
                {evt.event === "candidate_dropped" && (
                  <span className="text-amber-300">✗ dropped: {evt.data.name} ({evt.data.reason})</span>
                )}
              </li>
            ))}
            {log.length === 0 && <li className="text-parchment/40">Starting…</li>}
          </ul>
        </div>
      )}

      {error && (
        <div className="border border-red-400/40 rounded p-4 text-sm text-red-300">{error}</div>
      )}

      {report && (
        <>
          <div>
            <h2 className="font-display text-xl mb-3">Analogues</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {report.matched_cases.map((m) => (
                <AnalogueCard key={m.case_id} matched={m} caseData={cases[m.case_id]} />
              ))}
            </div>
          </div>

          {report.best_analogue_deep_dive && (
            <div>
              <h2 className="font-display text-xl mb-2">Best-analogue deep dive</h2>
              <p className="text-sm text-parchment/80">{report.best_analogue_deep_dive}</p>
            </div>
          )}

          {report.negative_analogue_warning && (
            <div className="border border-red-400/30 rounded p-4">
              <h2 className="font-display text-lg mb-2 text-red-300">Where you might be misled</h2>
              <p className="text-sm text-parchment/80">{report.negative_analogue_warning}</p>
            </div>
          )}

          <div>
            <h2 className="font-display text-xl mb-3">Verdict</h2>
            <div className="space-y-4">
              {report.option_assessments.map((oa) => (
                <div key={oa.option_id} className="border border-parchment/15 rounded p-4">
                  <h3 className="font-display text-lg mb-1">{oa.option_label}</h3>
                  <p className="text-xs uppercase tracking-wide text-parchment/50 mb-1">
                    Decision-quality assessment (not an outcome prediction)
                  </p>
                  <p className="text-sm mb-2">{oa.decision_quality_summary}</p>
                  <p className="text-sm text-parchment/70 mb-3">{oa.supporting_reasoning}</p>
                  <h4 className="text-sm font-display mb-2">Counterfactual branches</h4>
                  <CounterfactualTree counterfactuals={oa.counterfactuals} />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h2 className="font-display text-xl mb-3">Base rates</h2>
            <BaseRateTable table={report.base_rate_table} />
          </div>

          {report.red_team_paragraph && (
            <div className="border border-parchment/15 rounded p-4">
              <h2 className="font-display text-lg mb-2">Red team: the case against this analysis</h2>
              <p className="text-sm text-parchment/80">{report.red_team_paragraph}</p>
            </div>
          )}

          <footer className="fixed bottom-0 left-0 right-0 bg-navy/95 border-t border-parchment/20 px-4 py-3 text-xs text-parchment/70 print:static print:bg-white print:text-black">
            <div className="max-w-4xl mx-auto space-y-1">
              <p>
                <strong>Confidence:</strong> {report.confidence_statement}
              </p>
              <p>
                <strong>What would change this:</strong> {report.what_would_change_assessment}
              </p>
              <p className="text-parchment/50">{report.disclaimer}</p>
            </div>
          </footer>
        </>
      )}
    </section>
  );
}
