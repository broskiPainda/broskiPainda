import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createEventQuery, createScenario, updateScenario } from "../api.js";
import DimensionChips from "../components/DimensionChips.jsx";

const ROLE_LABELS = { initiator: "Initiator", target: "Target", third_party: "Third party" };

export default function ScenarioInput() {
  return (
    <div className="max-w-3xl mx-auto space-y-12">
      <ScenarioBox />
      <hr className="border-parchment/15" />
      <HistoricalEventBox />
    </div>
  );
}

function ScenarioBox() {
  const navigate = useNavigate();
  const [rawText, setRawText] = useState("");
  const [scenario, setScenario] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!rawText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const created = await createScenario(rawText);
      setScenario(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function updateActor(index, field, value) {
    setScenario((s) => {
      const actors = [...s.actors];
      actors[index] = { ...actors[index], [field]: value };
      return { ...s, actors };
    });
  }

  function updateOption(index, value) {
    setScenario((s) => {
      const options = [...s.options];
      options[index] = { ...options[index], label: value };
      return { ...s, options };
    });
  }

  function addOption() {
    setScenario((s) => ({
      ...s,
      options: [...s.options, { id: crypto.randomUUID(), label: "" }],
    }));
  }

  function updateConstraint(index, value) {
    setScenario((s) => {
      const constraints = [...s.constraints];
      constraints[index] = value;
      return { ...s, constraints };
    });
  }

  function updateDimension(key, value) {
    setScenario((s) => ({ ...s, dimensions: { ...s.dimensions, [key]: value } }));
  }

  async function handleConfirm() {
    setLoading(true);
    setError(null);
    try {
      await updateScenario(scenario.id, {
        actors: scenario.actors,
        objectives_by_actor: scenario.objectives_by_actor,
        constraints: scenario.constraints,
        options: scenario.options,
        dimensions: scenario.dimensions,
      });
      navigate(`/analysis/${scenario.id}`);
    } catch (err) {
      setError(err.message);
      setLoading(false);
    }
  }

  if (!scenario) {
    return (
      <section>
        <h1 className="font-display text-2xl mb-2">Analyze a scenario</h1>
        <p className="text-sm text-parchment/60 mb-4">
          A hypothetical or ongoing decision. Strategic-political level only — CLIO will decline
          operational or tactical military planning requests.
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <textarea
            className="w-full h-40 bg-transparent border border-parchment/30 rounded p-3 text-sm outline-none focus:border-parchment/60"
            placeholder="e.g. A mid-size power is considering a naval blockade of a smaller neighbor over a territorial dispute."
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
          {error && <p className="text-sm text-red-300">{error}</p>}
          <button
            type="submit"
            disabled={loading || !rawText.trim()}
            className="border border-parchment/40 rounded px-4 py-2 text-sm hover:bg-parchment/10 disabled:opacity-40"
          >
            {loading ? "Structuring…" : "Structure scenario"}
          </button>
        </form>
      </section>
    );
  }

  return (
    <section className="space-y-6">
      <div>
        <h1 className="font-display text-2xl mb-1">Here's how I understood your scenario</h1>
        <p className="text-sm text-parchment/60">Review and edit before analysis — garbage in, garbage out.</p>
      </div>

      <div>
        <h2 className="font-display text-lg mb-2">Actors</h2>
        <div className="space-y-2">
          {scenario.actors.map((actor, i) => (
            <div key={i} className="flex flex-wrap gap-2 items-center border border-parchment/15 rounded p-2">
              <input
                className="bg-transparent border-b border-parchment/20 text-sm outline-none px-1"
                value={actor.name}
                onChange={(e) => updateActor(i, "name", e.target.value)}
              />
              <select
                className="bg-transparent border border-parchment/20 rounded text-sm px-1 py-0.5"
                value={actor.role}
                onChange={(e) => updateActor(i, "role", e.target.value)}
              >
                {Object.entries(ROLE_LABELS).map(([value, label]) => (
                  <option key={value} value={value} className="bg-navy">
                    {label}
                  </option>
                ))}
              </select>
              <input
                className="bg-transparent border-b border-parchment/20 text-sm outline-none px-1 flex-1 min-w-[10rem]"
                value={actor.regime_type}
                onChange={(e) => updateActor(i, "regime_type", e.target.value)}
                placeholder="regime type"
              />
            </div>
          ))}
        </div>
      </div>

      <div>
        <h2 className="font-display text-lg mb-2">Options under consideration</h2>
        <div className="space-y-2">
          {scenario.options.map((option, i) => (
            <input
              key={option.id}
              className="w-full bg-transparent border-b border-parchment/20 text-sm outline-none px-1 py-1"
              value={option.label}
              onChange={(e) => updateOption(i, e.target.value)}
            />
          ))}
        </div>
        <button
          type="button"
          onClick={addOption}
          className="mt-2 text-xs underline text-parchment/60 hover:text-parchment"
        >
          + add option
        </button>
      </div>

      <div>
        <h2 className="font-display text-lg mb-2">Constraints</h2>
        <div className="space-y-1">
          {scenario.constraints.map((c, i) => (
            <input
              key={i}
              className="w-full bg-transparent border-b border-parchment/20 text-sm outline-none px-1 py-1"
              value={c}
              onChange={(e) => updateConstraint(i, e.target.value)}
            />
          ))}
        </div>
      </div>

      <div>
        <h2 className="font-display text-lg mb-2">Structural dimensions</h2>
        <DimensionChips dimensions={scenario.dimensions} onChange={updateDimension} editable />
      </div>

      {error && <p className="text-sm text-red-300">{error}</p>}

      <button
        type="button"
        onClick={handleConfirm}
        disabled={loading}
        className="border border-parchment/40 rounded px-4 py-2 text-sm hover:bg-parchment/10 disabled:opacity-40"
      >
        {loading ? "Starting analysis…" : "Confirm & Analyze"}
      </button>
    </section>
  );
}

function HistoricalEventBox() {
  const navigate = useNavigate();
  const [rawText, setRawText] = useState("");
  const [eventQuery, setEventQuery] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!rawText.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const created = await createEventQuery(rawText);
      setEventQuery(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleAnalyze() {
    navigate(`/event-analysis/${eventQuery.id}`);
  }

  function handleTryAgain() {
    setEventQuery(null);
    setError(null);
  }

  return (
    <section>
      <h1 className="font-display text-2xl mb-2">Analyze a historical decision</h1>
      <p className="text-sm text-parchment/60 mb-4">
        Something that actually happened — e.g. "the US backing the Mujahideen as a proxy
        against the USSR in Afghanistan." CLIO will research it, judge the decision quality
        given information available at the time, and surface what could have changed the
        effects.
      </p>

      {!eventQuery && (
        <form onSubmit={handleSubmit} className="space-y-3">
          <textarea
            className="w-full h-32 bg-transparent border border-parchment/30 rounded p-3 text-sm outline-none focus:border-parchment/60"
            placeholder="e.g. The USA backed the Mujahideen as a proxy against the USSR in Afghanistan."
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
          />
          {error && <p className="text-sm text-red-300">{error}</p>}
          <button
            type="submit"
            disabled={loading || !rawText.trim()}
            className="border border-parchment/40 rounded px-4 py-2 text-sm hover:bg-parchment/10 disabled:opacity-40"
          >
            {loading ? "Identifying…" : "Identify event"}
          </button>
        </form>
      )}

      {eventQuery && eventQuery.status === "not_found" && (
        <div className="border border-amber-400/30 rounded p-4 space-y-2">
          <p className="text-sm text-amber-300">
            Couldn't resolve this to one specific, verifiable event: {eventQuery.not_found_reason}
          </p>
          <button
            type="button"
            onClick={handleTryAgain}
            className="text-xs underline text-parchment/60 hover:text-parchment"
          >
            Try again
          </button>
        </div>
      )}

      {eventQuery && eventQuery.status === "identified" && (
        <div className="border border-parchment/20 rounded p-4 space-y-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-parchment/50">Resolved to</p>
            <p className="text-lg font-display">{eventQuery.resolved_name}</p>
            <p className="text-sm text-parchment/60">{eventQuery.resolved_dates}</p>
          </div>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleAnalyze}
              className="border border-parchment/40 rounded px-4 py-2 text-sm hover:bg-parchment/10"
            >
              Analyze this event
            </button>
            <button
              type="button"
              onClick={handleTryAgain}
              className="text-sm text-parchment/60 hover:text-parchment underline"
            >
              Not what you meant?
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
