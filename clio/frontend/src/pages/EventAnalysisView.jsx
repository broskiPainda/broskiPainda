import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { getCachedCase, getEventReport, streamEventAnalysis } from "../api.js";
import AnalogueCard from "../components/AnalogueCard.jsx";
import AssessmentScores from "../components/AssessmentScores.jsx";
import BaseRateTable from "../components/BaseRateTable.jsx";
import CounterfactualTree from "../components/CounterfactualTree.jsx";
import LessonsList from "../components/LessonsList.jsx";
import MachineGeneratedBadge from "../components/MachineGeneratedBadge.jsx";

const STEP_NAMES = {
  E1: "Identifying the event",
  E2: "Verifying the primary case against sources",
  E3: "Nominating comparable historical cases",
  E4: "Verifying comparable cases",
  E5: "Scoring structural similarity",
  E6: "Building base rates from conflict data",
  E7: "Synthesizing assessment",
};

export default function EventAnalysisView() {
  const { eventQueryId } = useParams();
  const [log, setLog] = useState([]);
  const [report, setReport] = useState(null);
  const [primaryCase, setPrimaryCase] = useState(null);
  const [cases, setCases] = useState({});
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();

    setLog([]);
    setReport(null);
    setPrimaryCase(null);
    setCases({});
    setError(null);
    setRunning(true);

    async function run() {
      try {
        const existing = await getEventReport(eventQueryId).catch(() => null);
        if (existing) {
          if (!cancelled) {
            setReport(existing);
            setRunning(false);
          }
          return;
        }

        for await (const evt of streamEventAnalysis(eventQueryId, { signal: controller.signal })) {
          if (cancelled) return;
          if (evt.event === "event_report_ready") {
            setReport(evt.data);
          } else if (evt.event === "event_pipeline_error") {
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
  }, [eventQueryId]);

  useEffect(() => {
    if (!report) return;
    getCachedCase(report.primary_case_id)
      .then(setPrimaryCase)
      .catch(() => {});

    const idsNeeded = report.comparable_cases.map((m) => m.case_id).filter((id) => !cases[id]);
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
        <h1 className="font-display text-2xl">Historical Decision Analysis</h1>
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
                {evt.event === "step_started" && <span>▸ {STEP_NAMES[evt.data.step] || evt.data.name}…</span>}
                {evt.event === "step_completed" && (
                  <span className="text-parchment/50">✓ {STEP_NAMES[evt.data.step] || evt.data.name} complete</span>
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

      {error && <div className="border border-red-400/40 rounded p-4 text-sm text-red-300">{error}</div>}

      {report && (
        <>
          <div>
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <h2 className="font-display text-xl">{primaryCase?.name || "Loading…"}</h2>
                {primaryCase && <p className="text-sm text-parchment/50">{primaryCase.era} · {primaryCase.dates}</p>}
              </div>
              <MachineGeneratedBadge />
            </div>
            {primaryCase && <p className="text-sm text-parchment/80 mb-3">{primaryCase.summary}</p>}
            {primaryCase?.source_urls?.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {primaryCase.source_urls.map((url) => (
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
          </div>

          {primaryCase && (
            <div>
              <h2 className="font-display text-xl mb-1">Was the decision right or wrong?</h2>
              <p className="text-xs uppercase tracking-wide text-parchment/50 mb-3">
                Decision quality judged on soundness given information available at the time — not
                a retroactive verdict on the outcome
              </p>
              <AssessmentScores assessments={primaryCase.assessments} />
            </div>
          )}

          {report.assessment_narrative && (
            <div>
              <h2 className="font-display text-xl mb-2">Assessment</h2>
              <p className="text-sm text-parchment/80">{report.assessment_narrative}</p>
            </div>
          )}

          {primaryCase && (
            <div>
              <h2 className="font-display text-xl mb-2">What could have changed the effects</h2>
              <CounterfactualTree counterfactuals={primaryCase.counterfactuals} />
            </div>
          )}

          {primaryCase?.lessons?.length > 0 && (
            <div>
              <h2 className="font-display text-xl mb-2">Lessons</h2>
              <LessonsList lessons={primaryCase.lessons} />
            </div>
          )}

          {report.comparable_cases.length > 0 && (
            <div>
              <h2 className="font-display text-xl mb-3">Comparable historical cases</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {report.comparable_cases.map((m) => (
                  <AnalogueCard key={m.case_id} matched={m} caseData={cases[m.case_id]} />
                ))}
              </div>
            </div>
          )}

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
