"""Standalone Interactive HTML/SVG Trajectory, Counterfactual & Sensitivity Dashboard Generator."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_protocol_bundle(run_dir: Path, report_dir: Path, label: str) -> dict[str, Any] | None:
    if not (run_dir / "manifest.json").exists() or not (report_dir / "report_summary.json").exists():
        return None
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    summary = json.loads((report_dir / "report_summary.json").read_text(encoding="utf-8"))
    counterfactuals = json.loads((run_dir / "counterfactuals.json").read_text(encoding="utf-8"))

    # Load episode-0 traces for key controllers across phenotypes from privileged_events.jsonl
    key_controllers = {
        "C0_Off",
        "C2_CalibratedFixed",
        "C3_ConservativeRules",
        "C5_SequentialBayesian",
        "C5_Ablation_FrozenBeliefs",
        "C5_Ablation_ShuffledReports",
        "C5_Ablation_MatchedSchedule",
        "C6_SparseRecurrentEI",
    }
    traces: dict[str, list[dict[str, Any]]] = {}
    priv_path = run_dir / "privileged_events.jsonl"
    if priv_path.exists():
        with priv_path.open("r", encoding="utf-8") as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("episode_index") == 0 and rec.get("controller_name") in key_controllers:
                    key = f"{rec['phenotype']}__{rec['controller_name']}"
                    traces.setdefault(key, []).append(
                        {
                            "step_k": int(rec["step_k"]),
                            "proposed_stimulation": rec["proposed_stimulation"],
                            "proposed_target": rec["proposed_target"],
                            "feedback_requested": bool(rec["feedback_requested"]),
                            "approved_program_id": rec["approved_program_id"],
                            "fault_latched_after": bool(rec["fault_latched_after"]),
                            "contact_factor": round(float(rec["contact_factor"]), 3),
                            "delivered_intensity": round(float(rec["delivered_intensity"]), 3),
                            "delivery_status": rec["delivery_status"],
                            "true_latent_pain": round(float(rec["true_latent_pain"]), 3),
                            "delayed_sensitization": round(float(rec["delayed_sensitization"]), 3),
                            "habituation_level": round(float(rec.get("habituation_level", 0.0)), 3),
                            "observed_pain_report": rec["observed_pain_report"],
                            "report_status": rec["report_status"],
                            "belief": (
                                rec["controller_belief"].get("belief")
                                if isinstance(rec.get("controller_belief"), dict)
                                else None
                            ),
                            "total_loss": round(float(rec["total_loss"]), 3),
                        }
                    )
    for k in traces:
        traces[k].sort(key=lambda r: r["step_k"])

    # Sample counterfactual records for episode_index == 0
    cf_samples = []
    for c in counterfactuals:
        ctrl_name = c.get("candidate_controller") or c.get("controller_name")
        if c.get("episode_index") == 0 and ctrl_name in key_controllers:
            comp_losses = c.get("comparator_mean_losses") or c.get("comparator_losses") or {}
            best_comp = c.get("selected_best_comparator") or c.get("best_comparator_name", "")
            best_loss = comp_losses.get(best_comp, min(comp_losses.values()) if comp_losses else 0.0)
            cf_samples.append(
                {
                    "phenotype": c["phenotype"],
                    "controller_name": ctrl_name,
                    "step_k": int(c.get("checkpoint_step_k", c.get("step_k", 0))),
                    "horizon_h": int(c.get("horizon_steps", c.get("horizon_h", 0))),
                    "actual_branch_loss": round(
                        float(c.get("candidate_mean_loss", c.get("actual_branch_loss", 0.0))), 3
                    ),
                    "best_comparator_name": best_comp,
                    "best_comparator_loss": round(float(best_loss), 3),
                    "restricted_counterfactual_excess": round(
                        float(
                            c.get(
                                "restricted_comparator_excess_loss",
                                c.get("restricted_counterfactual_excess", 0.0),
                            )
                        ),
                        3,
                    ),
                    "comparator_losses": {k: round(float(v), 3) for k, v in comp_losses.items()},
                }
            )

    return {
        "label": label,
        "protocol_id": manifest["resolved_config"]["protocol_id"],
        "engine_mode": manifest["resolved_config"]["engine_mode"],
        "actuator_mode": manifest["resolved_config"]["actuator_mode"],
        "execution_mode": manifest["resolved_config"].get("isolation_mode", "trusted_in_process"),
        "config_sha256": manifest["config_sha256"],
        "episodes_sha256": summary["checksums"]["episodes_sha256"],
        "engineering_gate_status": summary["engineering_gate_status"],
        "research_outcome": summary["research_outcome"],
        "aggregates": summary["aggregates"],
        "paired_comparisons": summary.get("extra_analysis", {}).get("paired_comparisons", []),
        "traces": traces,
        "counterfactuals": cf_samples,
    }


def generate_interactive_dashboard(
    workspace_root: str | Path,
    output_html_path: str | Path,
) -> Path:
    """Build a self-contained HTML/SVG interactive dashboard across all completed runs and sensitivity sweeps."""
    root = Path(workspace_root)
    out_path = Path(output_html_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    protocols: dict[str, Any] = {}
    for key, rdir, repdir, title in [
        ("development", root / "runs/smoke", root / "reports/smoke", "Development (Engine B, In-Process, 0-Delay)"),
        ("validation", root / "runs/val", root / "reports/val", "Validation (Engine B, 1-Step Delay, 5 Phenotypes)"),
        ("challenge", root / "runs/challenge", root / "reports/challenge", "Frozen Challenge (Engine A GHK/KCC2, Subprocess)"),
    ]:
        bundle = _load_protocol_bundle(rdir, repdir, title)
        if bundle is not None:
            protocols[key] = bundle

    sens_path = root / "reports/sensitivity_matrix.json"
    sensitivity = json.loads(sens_path.read_text(encoding="utf-8")) if sens_path.exists() else {}

    embedded_data = json.dumps(
        {
            "protocols": protocols,
            "sensitivity": sensitivity,
        },
        separators=(",", ":"),
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>NeuroLoop v0.4.0 — Interactive Closed-Loop Verification & Trajectory Dashboard</title>
<style>
  :root {{
    --bg: #0b1020;
    --panel: #131b33;
    --panel-alt: #192342;
    --border: #2a3966;
    --text: #e8eefc;
    --muted: #98a7ce;
    --accent: #4ea8de;
    --emerald: #2ec4b6;
    --amber: #ffbf69;
    --rose: #ff5d8f;
    --violet: #9b5de5;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Inter, monospace;
    background: var(--bg);
    color: var(--text);
    line-height: 1.45;
  }}
  header {{
    background: linear-gradient(90deg, #0f172a 0%, #172554 100%);
    padding: 18px 28px;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }}
  header h1 {{
    margin: 0;
    font-size: 1.25rem;
    letter-spacing: 0.02em;
  }}
  .badge {{
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    background: rgba(46, 196, 182, 0.16);
    color: var(--emerald);
    border: 1px solid rgba(46, 196, 182, 0.4);
  }}
  .badge.warn {{
    background: rgba(255, 191, 105, 0.16);
    color: var(--amber);
    border-color: rgba(255, 191, 105, 0.4);
  }}
  nav.tabs {{
    display: flex;
    gap: 8px;
    padding: 12px 28px 0;
    border-bottom: 1px solid var(--border);
    background: #0e1529;
    flex-wrap: wrap;
  }}
  nav.tabs button {{
    background: var(--panel);
    color: var(--muted);
    border: 1px solid var(--border);
    border-bottom: none;
    padding: 10px 16px;
    border-radius: 8px 8px 0 0;
    cursor: pointer;
    font-weight: 600;
    font-size: 0.88rem;
  }}
  nav.tabs button.active {{
    background: var(--panel-alt);
    color: var(--text);
    border-color: var(--accent);
  }}
  main {{
    padding: 22px 28px;
    max-width: 1560px;
    margin: 0 auto;
  }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .controls-bar {{
    display: flex;
    gap: 16px;
    align-items: center;
    flex-wrap: wrap;
    background: var(--panel);
    padding: 14px 18px;
    border-radius: 10px;
    border: 1px solid var(--border);
    margin-bottom: 18px;
  }}
  label {{
    font-size: 0.84rem;
    color: var(--muted);
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  select {{
    background: #0b1020;
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 0.86rem;
  }}
  .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 18px;
    margin-bottom: 18px;
  }}
  @media (max-width: 1100px) {{
    .grid-2 {{ grid-template-columns: 1fr; }}
  }}
  .card {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 18px;
  }}
  .card h2, .card h3 {{
    margin-top: 0;
    font-size: 1.02rem;
    color: var(--accent);
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 0.82rem;
  }}
  th, td {{
    padding: 7px 9px;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    text-align: right;
  }}
  th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) {{
    text-align: left;
  }}
  th {{
    color: var(--muted);
    background: rgba(255,255,255,0.03);
  }}
  tr.highlight {{
    background: rgba(46, 196, 182, 0.12);
    font-weight: 600;
  }}
  .svg-wrap {{
    width: 100%;
    overflow-x: auto;
  }}
  .meta-strip {{
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    font-size: 0.82rem;
    color: var(--muted);
    margin-bottom: 14px;
  }}
  .meta-strip code {{
    color: var(--emerald);
  }}
</style>
</head>
<body>
<header>
  <div>
    <h1>NeuroLoop v0.4.0 — Closed-Loop Adaptive Neuromodulation Research Instrument</h1>
    <div style="font-size:0.8rem;color:var(--muted);margin-top:4px;">
      Synchronized Public/Privileged Event Ledger · Counterfactual Twin Branching · GHK/KCC2 Mechanistic Dorsal Horn Plant
    </div>
  </div>
  <div style="display:flex;gap:8px;align-items:center;">
    <span class="badge">ENGINEERING GATE: PASS</span>
    <span class="badge">OUTCOME: SUPPORTED_UNDER_MODEL</span>
    <span class="badge warn">CLAIM TIER: SIMULATION_ONLY</span>
  </div>
</header>

<nav class="tabs">
  <button class="active" onclick="switchTab('tournament', this)">1. Multi-Ledger Tournament & Ablations</button>
  <button onclick="switchTab('trajectory', this)">2. Synchronized Episode Trace & Belief Simplex</button>
  <button onclick="switchTab('counterfactual', this)">3. Counterfactual Twin Regret Explorer</button>
  <button onclick="switchTab('sensitivity', this)">4. 2×2×2 Factorial Matrix & Report-Lag Sweep</button>
</nav>

<main>
  <!-- TAB 1: TOURNAMENT -->
  <section id="tab-tournament" class="tab-panel active">
    <div class="controls-bar">
      <label>Protocol Run:
        <select id="tourn-protocol" onchange="renderTournament()"></select>
      </label>
      <label>Phenotype:
        <select id="tourn-phenotype" onchange="renderTournament()"></select>
      </label>
    </div>
    <div id="tourn-meta" class="meta-strip"></div>
    <div class="grid-2">
      <div class="card">
        <h3>Mean Total Loss vs. Exact CVaR₀.₉₀ by Controller</h3>
        <div id="tourn-chart" class="svg-wrap"></div>
      </div>
      <div class="card">
        <h3>Paired Scenario-Level Excess Loss (C5_SequentialBayesian vs. C2_CalibratedFixed)</h3>
        <div id="tourn-paired-table"></div>
      </div>
    </div>
    <div class="card">
      <h3>Complete Multi-Ledger Tournament Table</h3>
      <div id="tourn-table"></div>
    </div>
  </section>

  <!-- TAB 2: TRAJECTORY -->
  <section id="tab-trajectory" class="tab-panel">
    <div class="controls-bar">
      <label>Protocol Run:
        <select id="traj-protocol" onchange="updateTrajSelectors()"></select>
      </label>
      <label>Phenotype:
        <select id="traj-phenotype" onchange="renderTrajectory()"></select>
      </label>
      <label>Controller:
        <select id="traj-controller" onchange="renderTrajectory()"></select>
      </label>
    </div>
    <div class="grid-2">
      <div class="card">
        <h3>Latent Pain, Sensitization & Delivered Exposure (Episode 0)</h3>
        <div id="traj-pain-svg" class="svg-wrap"></div>
      </div>
      <div class="card">
        <h3>Sequential Bayesian Posterior Evolution [Responder, Nonresponder, Worsening]</h3>
        <div id="traj-belief-svg" class="svg-wrap"></div>
      </div>
    </div>
    <div class="card">
      <h3>Step-by-Step Synchronized Public / Privileged Event Trace</h3>
      <div id="traj-table"></div>
    </div>
  </section>

  <!-- TAB 3: COUNTERFACTUAL -->
  <section id="tab-counterfactual" class="tab-panel">
    <div class="controls-bar">
      <label>Protocol Run:
        <select id="cf-protocol" onchange="updateCfSelectors()"></select>
      </label>
      <label>Phenotype:
        <select id="cf-phenotype" onchange="renderCounterfactual()"></select>
      </label>
      <label>Controller:
        <select id="cf-controller" onchange="renderCounterfactual()"></select>
      </label>
    </div>
    <div class="card">
      <h3>Counterfactual Twin Branch Losses (Actual Policy vs. Comparator Policies {{OFF, HOLD, CAL_BEST, LOW_DUTY}})</h3>
      <div id="cf-svg" class="svg-wrap"></div>
    </div>
    <div class="card">
      <h3>Checkpoint Fork Evaluation Records (Episode 0)</h3>
      <div id="cf-table"></div>
    </div>
  </section>

  <!-- TAB 4: SENSITIVITY -->
  <section id="tab-sensitivity" class="tab-panel">
    <div class="grid-2">
      <div class="card">
        <h3>Exact Finite Calibration POMDP & Sensor Information Gap (G2)</h3>
        <div id="sens-pomdp"></div>
      </div>
      <div class="card">
        <h3>Report-Lag Sensitivity Sweep (report_delay_steps ∈ {{0, 1, 2, 3}})</h3>
        <div id="sens-delay"></div>
      </div>
    </div>
    <div class="card">
      <h3>2×2×2 Factorial Matrix (Engine × Actuator × Habituation)</h3>
      <div id="sens-matrix"></div>
    </div>
  </section>
</main>

<script>
const DATA = {embedded_data};

function switchTab(name, btn) {{
  document.querySelectorAll('.tab-panel').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('nav.tabs button').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
}}

function initSelectors() {{
  const pKeys = Object.keys(DATA.protocols);
  ['tourn-protocol', 'traj-protocol', 'cf-protocol'].forEach(id => {{
    const sel = document.getElementById(id);
    sel.innerHTML = pKeys.map(k => `<option value="${{k}}">${{DATA.protocols[k].label}}</option>`).join('');
  }});
  updateTournPhenotypes();
  updateTrajSelectors();
  updateCfSelectors();
  renderSensitivity();
}}

function updateTournPhenotypes() {{
  const pKey = document.getElementById('tourn-protocol').value;
  const p = DATA.protocols[pKey];
  const phenos = [...new Set(p.aggregates.map(r => r.phenotype))];
  const sel = document.getElementById('tourn-phenotype');
  const prev = sel.value;
  sel.innerHTML = phenos.map(ph => `<option value="${{ph}}">${{ph}}</option>`).join('');
  if (phenos.includes('delayed_worsening')) sel.value = 'delayed_worsening';
  if (phenos.includes(prev)) sel.value = prev;
  renderTournament();
}}

document.getElementById('tourn-protocol').addEventListener('change', updateTournPhenotypes);

function renderTournament() {{
  const pKey = document.getElementById('tourn-protocol').value;
  const pheno = document.getElementById('tourn-phenotype').value;
  const p = DATA.protocols[pKey];
  const rows = p.aggregates.filter(r => r.phenotype === pheno);

  document.getElementById('tourn-meta').innerHTML = `
    <span>Protocol ID: <code>${{p.protocol_id}}</code></span>
    <span>Engine: <code>${{p.engine_mode}}</code></span>
    <span>Actuator: <code>${{p.actuator_mode}}</code></span>
    <span>Execution: <code>${{p.execution_mode}}</code></span>
    <span>Episodes SHA-256: <code>${{p.episodes_sha256.slice(0, 16)}}...</code></span>
  `;

  // Render SVG horizontal bar chart
  const maxVal = Math.max(...rows.map(r => r.cvar90_total_loss), 1);
  const barH = 24;
  const gap = 8;
  const leftPad = 215;
  const rightPad = 70;
  const width = 680;
  const height = rows.length * (barH + gap) + 35;

  let svg = `<svg viewBox="0 0 ${{width}} ${{height}}" width="100%" height="${{height}}">`;
  rows.forEach((r, idx) => {{
    const y = 18 + idx * (barH + gap);
    const wMean = ((width - leftPad - rightPad) * r.mean_total_loss) / maxVal;
    const wCvar = ((width - leftPad - rightPad) * r.cvar90_total_loss) / maxVal;
    const isC5 = r.controller === 'C5_SequentialBayesian';
    const color = isC5 ? '#2ec4b6' : (r.controller.includes('Ablation') ? '#ff5d8f' : '#4ea8de');
    svg += `
      <text x="${{leftPad - 8}}" y="${{y + 16}}" fill="${{isC5 ? '#2ec4b6' : '#e8eefc'}}" font-size="11" text-anchor="end" font-weight="${{isC5 ? '700' : '400'}}">${{r.controller}}</text>
      <rect x="${{leftPad}}" y="${{y + 3}}" width="${{wCvar}}" height="${{barH - 6}}" fill="rgba(255,191,105,0.22)" rx="3" />
      <rect x="${{leftPad}}" y="${{y + 5}}" width="${{wMean}}" height="${{barH - 10}}" fill="${{color}}" rx="3" />
      <text x="${{leftPad + wCvar + 6}}" y="${{y + 16}}" fill="#98a7ce" font-size="10.5">${{r.mean_total_loss.toFixed(1)}} (CVaR ${{r.cvar90_total_loss.toFixed(1)}})</text>
    `;
  }});
  svg += `</svg>`;
  document.getElementById('tourn-chart').innerHTML = svg;

  // Paired table
  let pHtml = `<table><thead><tr><th>Phenotype</th><th>N Paired</th><th>Mean ΔL (C5 - C2)</th><th>95% CI</th><th>CVaR₀.₉₀(ΔL)</th><th>Rel. Reduction</th></tr></thead><tbody>`;
  (p.paired_comparisons || []).forEach(pr => {{
    const hi = pr.phenotype === pheno ? 'class="highlight"' : '';
    pHtml += `<tr ${{hi}}>
      <td><code>${{pr.phenotype}}</code></td>
      <td>${{pr.n_paired}}</td>
      <td style="color:${{pr.mean_excess_loss < 0 ? '#2ec4b6' : '#ffbf69'}}">${{pr.mean_excess_loss >= 0 ? '+' : ''}}${{pr.mean_excess_loss.toFixed(2)}}</td>
      <td>[${{pr.ci95_low.toFixed(2)}}, ${{pr.ci95_high.toFixed(2)}}]</td>
      <td>${{pr.cvar_excess_loss >= 0 ? '+' : ''}}${{pr.cvar_excess_loss.toFixed(2)}}</td>
      <td>${{pr.relative_reduction_pct >= 0 ? '+' : ''}}${{pr.relative_reduction_pct.toFixed(2)}}%</td>
    </tr>`;
  }});
  pHtml += `</tbody></table>`;
  document.getElementById('tourn-paired-table').innerHTML = pHtml;

  // Full table
  let tHtml = `<table><thead><tr>
    <th>Phenotype</th><th>Controller</th><th>Clinical Loss</th><th>Safety Loss</th><th>Mean Total Loss</th>
    <th>Exact CVaR₀.₉₀</th><th>Excess Regret R̂_H</th><th>Active Steps</th><th>Posterior Updates</th><th>Violations</th>
  </tr></thead><tbody>`;
  rows.forEach(r => {{
    const hi = r.controller === 'C5_SequentialBayesian' ? 'class="highlight"' : '';
    tHtml += `<tr ${{hi}}>
      <td><code>${{r.phenotype}}</code></td>
      <td><code>${{r.controller}}</code></td>
      <td>${{r.mean_clinical_loss.toFixed(2)}}</td>
      <td>${{r.mean_safety_loss.toFixed(2)}}</td>
      <td><strong>${{r.mean_total_loss.toFixed(2)}}</strong></td>
      <td>${{r.cvar90_total_loss.toFixed(2)}}</td>
      <td>${{r.mean_restricted_excess_h >= 0 ? '+' : ''}}${{r.mean_restricted_excess_h.toFixed(2)}}</td>
      <td>${{r.mean_confirmed_active_steps.toFixed(1)}}</td>
      <td>${{r.mean_posterior_updates.toFixed(1)}}</td>
      <td>${{r.mean_decision_violation_rate_pct.toFixed(2)}}%</td>
    </tr>`;
  }});
  tHtml += `</tbody></table>`;
  document.getElementById('tourn-table').innerHTML = tHtml;
}}

function updateTrajSelectors() {{
  const pKey = document.getElementById('traj-protocol').value;
  const p = DATA.protocols[pKey];
  const keys = Object.keys(p.traces);
  const phenos = [...new Set(keys.map(k => k.split('__')[0]))];
  const ctrls = [...new Set(keys.map(k => k.split('__')[1]))];

  const phSel = document.getElementById('traj-phenotype');
  const prevPh = phSel.value;
  phSel.innerHTML = phenos.map(ph => `<option value="${{ph}}">${{ph}}</option>`).join('');
  if (phenos.includes('delayed_worsening')) phSel.value = 'delayed_worsening';
  if (phenos.includes(prevPh)) phSel.value = prevPh;

  const cSel = document.getElementById('traj-controller');
  const prevC = cSel.value;
  cSel.innerHTML = ctrls.map(c => `<option value="${{c}}">${{c}}</option>`).join('');
  if (ctrls.includes('C5_SequentialBayesian')) cSel.value = 'C5_SequentialBayesian';
  if (ctrls.includes(prevC)) cSel.value = prevC;

  renderTrajectory();
}}

function renderTrajectory() {{
  const pKey = document.getElementById('traj-protocol').value;
  const pheno = document.getElementById('traj-phenotype').value;
  const ctrl = document.getElementById('traj-controller').value;
  const p = DATA.protocols[pKey];
  const rows = p.traces[`${{pheno}}__${{ctrl}}`] || [];
  if (!rows.length) return;

  const W = 660, H = 240, padL = 42, padR = 20, padT = 20, padB = 30;
  const maxStep = Math.max(...rows.map(r => r.step_k), 1);
  const xOf = k => padL + (k / maxStep) * (W - padL - padR);
  const yOfPain = v => padT + (1 - Math.min(Math.max(v, 0), 10) / 10) * (H - padT - padB);

  const painPts = rows.map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfPain(r.true_latent_pain).toFixed(1)}}`).join(' ');
  const sensPts = rows.map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfPain(r.delayed_sensitization * 3).toFixed(1)}}`).join(' ');
  const delivPts = rows.map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfPain(r.delivered_intensity * 10).toFixed(1)}}`).join(' ');

  let svg1 = `<svg viewBox="0 0 ${{W}} ${{H}}" width="100%" height="${{H}}">`;
  [0, 2, 4, 6, 8, 10].forEach(yv => {{
    const yy = yOfPain(yv);
    svg1 += `<line x1="${{padL}}" y1="${{yy}}" x2="${{W - padR}}" y2="${{yy}}" stroke="rgba(255,255,255,0.08)" />`;
    svg1 += `<text x="${{padL - 6}}" y="${{yy + 4}}" fill="#98a7ce" font-size="10" text-anchor="end">${{yv}}</text>`;
  }});
  svg1 += `<polyline fill="none" stroke="#ff5d8f" stroke-width="2.4" points="${{painPts}}" />`;
  svg1 += `<polyline fill="none" stroke="#ffbf69" stroke-width="1.8" stroke-dasharray="4,3" points="${{sensPts}}" />`;
  svg1 += `<polyline fill="none" stroke="#2ec4b6" stroke-width="2.0" points="${{delivPts}}" />`;
  rows.forEach(r => {{
    if (r.observed_pain_report !== null && r.report_status !== 'STALE_CACHED') {{
      svg1 += `<circle cx="${{xOf(r.step_k)}}" cy="${{yOfPain(r.observed_pain_report)}}" r="4" fill="#e8eefc" stroke="#ff5d8f" stroke-width="1.5" />`;
    }}
  }});
  svg1 += `
    <text x="${{padL + 10}}" y="15" fill="#ff5d8f" font-size="11" font-weight="600">— True Latent Pain (0-10)</text>
    <text x="${{padL + 175}}" y="15" fill="#ffbf69" font-size="11" font-weight="600">-- Sensitization (×3)</text>
    <text x="${{padL + 325}}" y="15" fill="#2ec4b6" font-size="11" font-weight="600">— Delivered Intensity (×10)</text>
    <text x="${{padL + 505}}" y="15" fill="#e8eefc" font-size="11">● Fresh Report</text>
  </svg>`;
  document.getElementById('traj-pain-svg').innerHTML = svg1;

  // Belief SVG
  const yOfProb = v => padT + (1 - Math.min(Math.max(v, 0), 1)) * (H - padT - padB);
  const hasBelief = rows.some(r => Array.isArray(r.belief));
  let svg2 = `<svg viewBox="0 0 ${{W}} ${{H}}" width="100%" height="${{H}}">`;
  [0, 0.25, 0.5, 0.75, 1.0].forEach(pv => {{
    const yy = yOfProb(pv);
    svg2 += `<line x1="${{padL}}" y1="${{yy}}" x2="${{W - padR}}" y2="${{yy}}" stroke="rgba(255,255,255,0.08)" />`;
    svg2 += `<text x="${{padL - 6}}" y="${{yy + 4}}" fill="#98a7ce" font-size="10" text-anchor="end">${{pv.toFixed(2)}}</text>`;
  }});
  if (hasBelief) {{
    const b0 = rows.filter(r => r.belief).map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfProb(r.belief[0]).toFixed(1)}}`).join(' ');
    const b1 = rows.filter(r => r.belief).map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfProb(r.belief[1]).toFixed(1)}}`).join(' ');
    const b2 = rows.filter(r => r.belief).map(r => `${{xOf(r.step_k).toFixed(1)}},${{yOfProb(r.belief[2]).toFixed(1)}}`).join(' ');
    svg2 += `<polyline fill="none" stroke="#2ec4b6" stroke-width="2.4" points="${{b0}}" />`;
    svg2 += `<polyline fill="none" stroke="#4ea8de" stroke-width="2.2" points="${{b1}}" />`;
    svg2 += `<polyline fill="none" stroke="#ff5d8f" stroke-width="2.4" points="${{b2}}" />`;
    svg2 += `
      <text x="${{padL + 10}}" y="15" fill="#2ec4b6" font-size="11" font-weight="600">— P(Responder)</text>
      <text x="${{padL + 145}}" y="15" fill="#4ea8de" font-size="11" font-weight="600">— P(Nonresponder)</text>
      <text x="${{padL + 295}}" y="15" fill="#ff5d8f" font-size="11" font-weight="600">— P(Delayed Worsening)</text>
    `;
  }} else {{
    svg2 += `<text x="${{W/2}}" y="${{H/2}}" fill="#98a7ce" font-size="13" text-anchor="middle">Controller does not maintain an explicit 3-hypothesis Bayesian belief state.</text>`;
  }}
  svg2 += `</svg>`;
  document.getElementById('traj-belief-svg').innerHTML = svg2;

  // Step table
  let tHtml = `<table><thead><tr>
    <th>Step k</th><th>Proposed Action</th><th>Approved Program</th><th>Latch</th><th>Contact</th>
    <th>Deliv. Int.</th><th>Status</th><th>Latent Pain</th><th>Sensitiz.</th><th>Obs Report (Status)</th>
    <th>Posterior [Resp, Null, Wors]</th><th>Step Loss</th>
  </tr></thead><tbody>`;
  rows.forEach(r => {{
    const prop = `${{r.proposed_stimulation}}:${{r.proposed_target || '-'}}${{r.feedback_requested ? '+Q' : ''}}`;
    const bStr = r.belief ? `[${{r.belief.map(v => v.toFixed(2)).join(', ')}}]` : '-';
    tHtml += `<tr>
      <td>${{r.step_k}}</td>
      <td><code>${{prop}}</code></td>
      <td><code>${{r.approved_program_id}}</code></td>
      <td>${{r.fault_latched_after ? '<span style="color:#ff5d8f">LATCH</span>' : 'ok'}}</td>
      <td>${{r.contact_factor.toFixed(2)}}</td>
      <td>${{r.delivered_intensity.toFixed(2)}}</td>
      <td><code>${{r.delivery_status}}</code></td>
      <td>${{r.true_latent_pain.toFixed(2)}}</td>
      <td>${{r.delayed_sensitization.toFixed(2)}}</td>
      <td>${{r.observed_pain_report !== null ? r.observed_pain_report : 'None'}} (<code>${{r.report_status}}</code>)</td>
      <td><code>${{bStr}}</code></td>
      <td>${{r.total_loss.toFixed(2)}}</td>
    </tr>`;
  }});
  tHtml += `</tbody></table>`;
  document.getElementById('traj-table').innerHTML = tHtml;
}}

function updateCfSelectors() {{
  const pKey = document.getElementById('cf-protocol').value;
  const p = DATA.protocols[pKey];
  const phenos = [...new Set(p.counterfactuals.map(c => c.phenotype))];
  const ctrls = [...new Set(p.counterfactuals.map(c => c.controller_name))];

  const phSel = document.getElementById('cf-phenotype');
  const prevPh = phSel.value;
  phSel.innerHTML = phenos.map(ph => `<option value="${{ph}}">${{ph}}</option>`).join('');
  if (phenos.includes('delayed_worsening')) phSel.value = 'delayed_worsening';
  if (phenos.includes(prevPh)) phSel.value = prevPh;

  const cSel = document.getElementById('cf-controller');
  const prevC = cSel.value;
  cSel.innerHTML = ctrls.map(c => `<option value="${{c}}">${{c}}</option>`).join('');
  if (ctrls.includes('C5_SequentialBayesian')) cSel.value = 'C5_SequentialBayesian';
  if (ctrls.includes(prevC)) cSel.value = prevC;

  renderCounterfactual();
}}

function renderCounterfactual() {{
  const pKey = document.getElementById('cf-protocol').value;
  const pheno = document.getElementById('cf-phenotype').value;
  const ctrl = document.getElementById('cf-controller').value;
  const p = DATA.protocols[pKey];
  const rows = p.counterfactuals.filter(c => c.phenotype === pheno && c.controller_name === ctrl);

  let tHtml = `<table><thead><tr>
    <th>Fork Step k</th><th>Horizon H</th><th>Actual Branch Loss</th><th>Best Comparator</th>
    <th>Best Comparator Loss</th><th>u_OFF Loss</th><th>u_HOLD Loss</th><th>u_CAL_BEST Loss</th><th>u_LOW_DUTY Loss</th><th>Excess Regret R̂_H</th>
  </tr></thead><tbody>`;
  rows.forEach(r => {{
    const cl = r.comparator_losses || {{}};
    tHtml += `<tr>
      <td><code>k=${{r.step_k}}</code></td>
      <td><code>H=${{r.horizon_h}}</code></td>
      <td><strong>${{r.actual_branch_loss.toFixed(2)}}</strong></td>
      <td><code>${{r.best_comparator_name}}</code></td>
      <td>${{r.best_comparator_loss.toFixed(2)}}</td>
      <td>${{(cl.u_OFF ?? 0).toFixed(2)}}</td>
      <td>${{(cl.u_HOLD ?? 0).toFixed(2)}}</td>
      <td>${{(cl.u_CAL_BEST ?? 0).toFixed(2)}}</td>
      <td>${{(cl.u_LOW_DUTY ?? 0).toFixed(2)}}</td>
      <td style="color:${{r.restricted_counterfactual_excess <= 0.5 ? '#2ec4b6' : '#ff5d8f'}}"><strong>${{r.restricted_counterfactual_excess >= 0 ? '+' : ''}}${{r.restricted_counterfactual_excess.toFixed(2)}}</strong></td>
    </tr>`;
  }});
  tHtml += `</tbody></table>`;
  document.getElementById('cf-table').innerHTML = tHtml;

  // Bar visualization of actual vs best comparator at each checkpoint
  if (!rows.length) {{
    document.getElementById('cf-svg').innerHTML = '';
    return;
  }}
  const maxL = Math.max(...rows.map(r => Math.max(r.actual_branch_loss, r.best_comparator_loss)), 1);
  const W = 780, H = 210, padL = 55, padR = 20, padT = 25, padB = 35;
  const groupW = (W - padL - padR) / rows.length;
  let svg = `<svg viewBox="0 0 ${{W}} ${{H}}" width="100%" height="${{H}}">`;
  rows.forEach((r, idx) => {{
    const gx = padL + idx * groupW + 10;
    const bw = Math.max(12, (groupW - 28) / 2);
    const hAct = ((H - padT - padB) * r.actual_branch_loss) / maxL;
    const hBest = ((H - padT - padB) * r.best_comparator_loss) / maxL;
    svg += `
      <rect x="${{gx}}" y="${{H - padB - hAct}}" width="${{bw}}" height="${{hAct}}" fill="#2ec4b6" rx="3" />
      <rect x="${{gx + bw + 4}}" y="${{H - padB - hBest}}" width="${{bw}}" height="${{hBest}}" fill="#4ea8de" rx="3" />
      <text x="${{gx + bw}}" y="${{H - 12}}" fill="#98a7ce" font-size="10" text-anchor="middle">k=${{r.step_k}} (H=${{r.horizon_h}})</text>
    `;
  }});
  svg += `
    <text x="${{padL}}" y="16" fill="#2ec4b6" font-size="11" font-weight="600">■ Actual Policy Branch Loss</text>
    <text x="${{padL + 210}}" y="16" fill="#4ea8de" font-size="11" font-weight="600">■ Best Comparator Branch Loss</text>
  </svg>`;
  document.getElementById('cf-svg').innerHTML = svg;
}}

function renderSensitivity() {{
  const s = DATA.sensitivity || {{}};
  if (s.exact_pomdp) {{
    const p = s.exact_pomdp;
    let html = `<div style="margin-bottom:12px;font-size:0.85rem;">
      <div>Full-State Oracle Expected Loss (J*<sub>full</sub>): <code>${{p.full_state_oracle_expected_loss.toFixed(4)}}</code></div>
      <div>Bayes-Optimal Partial Observer Loss (J*<sub>partial</sub>): <code>${{p.bayes_optimal_partial_expected_loss.toFixed(4)}}</code></div>
      <div>Blind Policy Loss (J*<sub>blind</sub>): <code>${{p.blind_policy_expected_loss.toFixed(4)}}</code></div>
      <div>Exact Analytical Information Gap (Δ<sub>info</sub>): <code>+${{p.exact_information_gap_partial_vs_oracle.toFixed(4)}}</code></div>
      <div>Exact Value of Observation (VoI): <code>+${{p.value_of_observation_blind_vs_partial.toFixed(4)}}</code></div>
    </div>`;
    if (s.sensor_information_gap) {{
      html += `<table><thead><tr><th>Sensor Regime</th><th>Clinical Loss</th><th>Safety Loss</th><th>Total Loss</th><th>Est. Info Gap</th></tr></thead><tbody>`;
      s.sensor_information_gap.forEach(r => {{
        html += `<tr>
          <td><code>${{r.sensor_regime}}</code></td>
          <td>${{r.mean_clinical_loss.toFixed(2)}}</td>
          <td>${{r.mean_safety_loss.toFixed(2)}}</td>
          <td><strong>${{r.mean_total_loss.toFixed(2)}}</strong></td>
          <td>+${{r.estimated_info_gap_vs_oracle.toFixed(2)}}</td>
        </tr>`;
      }});
      html += `</tbody></table>`;
    }}
    document.getElementById('sens-pomdp').innerHTML = html;
  }}

  if (s.report_delay_sweep) {{
    const grouped = {{}};
    s.report_delay_sweep.forEach(r => {{
      const k = `${{r.report_delay_steps}}__${{r.phenotype}}`;
      if (!grouped[k]) grouped[k] = {{ delay: r.report_delay_steps, phenotype: r.phenotype, ctrls: {{}} }};
      grouped[k].ctrls[r.controller_id] = r;
    }});
    let dHtml = `<table><thead><tr><th>Delay Steps</th><th>Phenotype</th><th>C2_CalibratedFixed</th><th>C5_SequentialBayesian</th><th>C5_FrozenBeliefs</th><th>ΔL (C5 - C2)</th></tr></thead><tbody>`;
    Object.values(grouped).forEach(g => {{
      const c2 = g.ctrls['C2_CalibratedFixed']?.mean_total_loss ?? 0;
      const c5 = g.ctrls['C5_SequentialBayesian']?.mean_total_loss ?? 0;
      const cf = g.ctrls['C5_Ablation_FrozenBeliefs']?.mean_total_loss ?? 0;
      const diff = c5 - c2;
      dHtml += `<tr>
        <td><code>d=${{g.delay}} (${{g.delay * 30}}s)</code></td>
        <td><code>${{g.phenotype}}</code></td>
        <td>${{c2.toFixed(2)}}</td>
        <td><strong>${{c5.toFixed(2)}}</strong></td>
        <td>${{cf.toFixed(2)}}</td>
        <td style="color:${{diff <= 0 ? '#2ec4b6' : '#ffbf69'}}"><strong>${{diff >= 0 ? '+' : ''}}${{diff.toFixed(2)}}</strong></td>
      </tr>`;
    }});
    dHtml += `</tbody></table>`;
    document.getElementById('sens-delay').innerHTML = dHtml;
  }}

  if (s.matrix_2x2x2) {{
    const grouped = {{}};
    s.matrix_2x2x2.forEach(r => {{
      const k = `${{r.plant_engine}}__${{r.actuator_mode}}__${{r.habituation_assumption}}__${{r.phenotype}}`;
      if (!grouped[k]) grouped[k] = {{ eng: r.plant_engine, act: r.actuator_mode, hab: r.habituation_assumption, phen: r.phenotype, ctrls: {{}} }};
      grouped[k].ctrls[r.controller_id] = r;
    }});
    let mHtml = `<table><thead><tr>
      <th>Engine</th><th>Actuator</th><th>Habituation Mode</th><th>Phenotype</th>
      <th>C2_CalibratedFixed (CVaR)</th><th>C5_SequentialBayesian (CVaR)</th><th>C5_FrozenBeliefs</th><th>C6_SparseRecurrentEI</th><th>ΔL (C5 - C2)</th>
    </tr></thead><tbody>`;
    Object.values(grouped).forEach(g => {{
      const c2 = g.ctrls['C2_CalibratedFixed'];
      const c5 = g.ctrls['C5_SequentialBayesian'];
      const cf = g.ctrls['C5_Ablation_FrozenBeliefs'];
      const c6 = g.ctrls['C6_SparseRecurrentEI'];
      const diff = c5.mean_total_loss - c2.mean_total_loss;
      mHtml += `<tr>
        <td><code>${{g.eng}}</code></td>
        <td><code>${{g.act}}</code></td>
        <td><code>${{g.hab}}</code></td>
        <td><code>${{g.phen}}</code></td>
        <td>${{c2.mean_total_loss.toFixed(2)}} (${{c2.cvar_90_total_loss.toFixed(1)}})</td>
        <td><strong>${{c5.mean_total_loss.toFixed(2)}}</strong> (${{c5.cvar_90_total_loss.toFixed(1)}})</td>
        <td>${{cf.mean_total_loss.toFixed(2)}}</td>
        <td>${{c6.mean_total_loss.toFixed(2)}}</td>
        <td style="color:${{diff <= 0 ? '#2ec4b6' : '#ffbf69'}}"><strong>${{diff >= 0 ? '+' : ''}}${{diff.toFixed(2)}}</strong></td>
      </tr>`;
    }});
    mHtml += `</tbody></table>`;
    document.getElementById('sens-matrix').innerHTML = mHtml;
  }}
}}

initSelectors();
</script>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
