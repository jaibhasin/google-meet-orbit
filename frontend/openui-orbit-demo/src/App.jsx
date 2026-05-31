import { defineComponent, createLibrary, Renderer } from "@openuidev/react-lang";
import { z } from "zod/v4";
import { orbitDemoData } from "./data/orbitDemoData";
import { useState } from "react";

const meterTone = {
  high: "var(--brand-cyan)",
  medium: "var(--brand-blue)",
  warning: "var(--brand-orange)",
  low: "var(--brand-green)",
};

const formatValue = (value) => {
  if (typeof value !== "string") return value;
  if (value.includes("%")) return value;
  return value;
};

const ProgressRing = ({ value, tone = "medium" }) => {
  const numeric = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div className="progress-wrap" role="img" aria-label={`confidence ${numeric}`}>
      <div
        className="progress-fill"
        style={{
          width: `${numeric}%`,
          background:
            tone === "warning" ? "var(--brand-orange)" : tone === "low" ? "var(--brand-green)" : meterTone[tone],
        }}
      />
    </div>
  );
};

const MetricCard = ({ metric }) => {
  const tone = metric.tone || "medium";

  return (
    <article className={`metric-card tone-${tone}`}>
      <div className="metric-head">
        <p className="metric-label">{metric.label}</p>
        <span className={`signal-dot signal-${tone}`} />
      </div>
      <p className="metric-value">{formatValue(metric.value)}</p>
      <ProgressRing value={metric.score} tone={tone} />
      <p className="metric-note">{metric.note}</p>
    </article>
  );
};

const PipelineStep = ({ initiative }) => {
  return (
    <article className="pipeline-card">
      <header>
        <h4>{initiative.name}</h4>
        <span className={`pill pill-${initiative.score >= 85 ? "high" : initiative.score >= 70 ? "medium" : "warning"}`}>
          {initiative.score}
        </span>
      </header>
      <p>Stage: {initiative.stage}</p>
      <div className="pipeline-row">
        <span>Last discussed: {initiative.lastDiscussed}</span>
        <span className="muted">Confidence {initiative.confidence}%</span>
      </div>
      <p className="muted">Blocker: {initiative.blocker}</p>
      <ProgressRing value={initiative.score} tone={initiative.score >= 85 ? "high" : initiative.score >= 70 ? "medium" : "warning"} />
    </article>
  );
};

const RadarCard = ({ card }) => {
  return (
    <article className="radar-card">
      <h4>{card.title}</h4>
      <p>status: {card.status}</p>
      <p>momentum: {card.momentum}</p>
      <p>owner: {card.owner}</p>
      <p>blocker: {card.blocker}</p>
      <p className="muted">last update: {card.lastUpdate}</p>
    </article>
  );
};

const DecisionCard = ({ decision }) => {
  return (
    <article className="decision-card">
      <header>
        <h4>{decision.text}</h4>
        <span className={`pill pill-${decision.confidence >= 85 ? "high" : decision.confidence >= 70 ? "medium" : "warning"}`}>
          {decision.confidence}%
        </span>
      </header>
      <div className="kv-grid">
        <span>
          owner: <strong>{decision.owner}</strong>
        </span>
        <span>
          source: <strong>{decision.sourceMeeting}</strong>
        </span>
      </div>
      <p className="muted">{decision.rationale}</p>
    </article>
  );
};

const OpenLoopCard = ({ loop }) => {
  return (
    <article className="open-loop-card">
      <h4>{loop.title}</h4>
      <p>
        <span className="label">Impact:</span> {loop.impact}
      </p>
      <p>
        <span className="label">Suggested action:</span> {loop.action}
      </p>
      <p className="meta">urgency: {loop.urgency}</p>
    </article>
  );
};

const SelfLoopNode = ({ item }) => {
  return (
    <article className="self-loop-node">
      <p className="small-label">{item.stage}</p>
      <h4>{item.title}</h4>
      <p className="muted">{item.detail}</p>
    </article>
  );
};

const CostBar = ({ item }) => (
  <article className="cost-card">
    <p>{item.label}</p>
    <p className={`cost-value cost-${item.tone}`}>{item.value}</p>
  </article>
);

const TeamCard = ({ person }) => {
  return (
    <article className="team-card">
      <header>
        <h4>{person.person}</h4>
        <span className={`load-pill load-${person.load}`}>{person.load}</span>
      </header>
      {person.openActions !== undefined && (
        <p>
          <span className="label">Open actions:</span> {person.openActions}
          {person.blocked !== undefined ? `, blocked: ${person.blocked}` : ""}
        </p>
      )}
      {person.decisionsContributed !== undefined && (
        <p>
          <span className="label">Decisions contributed:</span> {person.decisionsContributed}
        </p>
      )}
      {person.unresolvedQuestions !== undefined && <p>unresolved question: {person.unresolvedQuestions}</p>}
      {person.projectUpdates !== undefined && <p>project updates: {person.projectUpdates}</p>}
    </article>
  );
};

function OrbitDashboard() {
  return (
    <div className="cockpit-shell">
      <header className="topbar">
        <p className="live-pill">
          <span className="pulse-dot" />
          {orbitDemoData.page.liveMode}
        </p>
        <div className="title-block">
          <h1>{orbitDemoData.page.title}</h1>
          <p>{orbitDemoData.page.subtitle}</p>
        </div>
      </header>

      <section className="ask-orbit">
        <input value="" placeholder={orbitDemoData.askOrbit.placeholder} readOnly />
        <div className="suggest-grid">
          {orbitDemoData.askOrbit.suggestedQuestions.map((question) => (
            <span key={question} className="suggestion-pill">
              {question}
            </span>
          ))}
        </div>
      </section>

      <section className="content-grid">
        <article className="panel span-2">
          <h2>Company Pulse</h2>
          <div className="metric-grid">
            {orbitDemoData.metrics.map((metric) => (
              <MetricCard metric={metric} key={metric.label} />
            ))}
          </div>
          <article className="insight-card">
            <h3>Signal Insight</h3>
            <p>{orbitDemoData.insights[0]}</p>
          </article>
        </article>

        <article className="panel">
          <h2>AI Cost &amp; Usage</h2>
          <div className="cost-summary">
            <p>
              Weekly AI spend: <strong>{orbitDemoData.cost.totals.weeklySpend}</strong>
            </p>
            <p>
              Cost per captured meeting: <strong>{orbitDemoData.cost.totals.perMeeting}</strong>
            </p>
            <p>
              Cost per extracted decision: <strong>{orbitDemoData.cost.totals.perDecision}</strong>
            </p>
            <p>
              Failed/retried run cost: <strong>{orbitDemoData.cost.totals.failedRetryCost}</strong>
            </p>
          </div>
          <div className="cost-bars">
            {orbitDemoData.cost.breakdown.map((item) => (
              <CostBar item={item} key={item.label} />
            ))}
          </div>
          <p className="insight-line">{orbitDemoData.cost.totals.insight}</p>
        </article>
      </section>

      <section className="panel span-3">
        <h2>Product / Project Velocity</h2>
        <div className="pipeline-track">
          {orbitDemoData.pipeline.stages.map((stage, index) => (
            <span key={`${stage}-${index}`}>{stage}</span>
          ))}
        </div>
        <div className="initiative-grid">
          {orbitDemoData.pipeline.initiatives.map((initiative) => (
            <PipelineStep initiative={initiative} key={initiative.name} />
          ))}
        </div>
        <div className="radar-area">
          <h3>Project Radar</h3>
          <div className="radar-grid">
            {orbitDemoData.projectRadar.map((item) => (
              <RadarCard card={item} key={item.title} />
            ))}
          </div>
        </div>
      </section>

      <section className="content-grid">
        <article className="panel">
          <h2>Decision Intelligence</h2>
          <div className="decision-summary">
            <span>confirmed decisions this week: {orbitDemoData.decisions.counts.confirmed}</span>
            <span>waiting for owner: {orbitDemoData.decisions.counts.waiting}</span>
            <span>low-confidence decisions: {orbitDemoData.decisions.counts.lowConfidence}</span>
            <span>reopened decisions: {orbitDemoData.decisions.counts.reopened}</span>
            <span>decision debt: {orbitDemoData.decisions.counts.debt}</span>
          </div>
          <div className="decision-stack">
            {orbitDemoData.decisions.cards.map((decision) => (
              <DecisionCard decision={decision} key={decision.text} />
            ))}
          </div>
        </article>

        <article className="panel">
          <h2>AI Cost + Team Flow</h2>
          <div className="team-signals">
            {orbitDemoData.teamFlow.metrics.map((metric) => (
              <p key={metric.label}>
                <span className="label">{metric.label}</span> {metric.value}
              </p>
            ))}
          </div>
          <div className="team-grid">
            {orbitDemoData.teamFlow.signals.map((person) => (
              <TeamCard person={person} key={person.person} />
            ))}
          </div>
          <p className="disclaimer">Orbit measures work signals, not human worth.</p>
        </article>
      </section>

      <section className="panel span-3">
        <h2>Open Loops + Self-Improvement Loop</h2>
        <div className="open-loop-grid">
          {orbitDemoData.openLoops.map((loop) => (
            <OpenLoopCard loop={loop} key={loop.title} />
          ))}
        </div>

        <h3 className="self-title">Self-Improvement Loop</h3>
        <div className="self-loop-track">
          {orbitDemoData.selfImprovementLoop.map((entry) => (
            <SelfLoopNode item={entry} key={entry.stage} />
          ))}
        </div>
      </section>
    </div>
  );
}

const OrbitCommandCenterComponent = defineComponent({
  name: "OrbitCommandCenter",
  description: "Root component for the Orbit Command Center static demo UI.",
  props: z.object({}),
  component: () => <OrbitDashboard />,
});

const orbitLibrary = createLibrary({
  root: "OrbitCommandCenter",
  componentGroups: [],
  components: [OrbitCommandCenterComponent],
});

const openUIResponse = `root = OrbitCommandCenter()`;

export default function App() {
  const [renderFailed, setRenderFailed] = useState(false);

  if (renderFailed) {
    return <OrbitDashboard />;
  }

  return (
    <Renderer
      library={orbitLibrary}
      response={openUIResponse}
      isStreaming={false}
      onError={(errors) => {
        if (errors.length) {
          console.error("OpenUI render errors:", errors);
          setRenderFailed(true);
        }
      }}
    />
  );
}
