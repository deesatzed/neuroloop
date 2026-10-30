"""
Trace Viewer and Scientific Report Generator for NeuroLoop v0.4.0.
Reads persisted event logs and generates synchronized episode traces and
complete Markdown/JSON reports separating Engineering Gates from Research Outcomes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from neuroloop.evaluation import compute_exact_cvar


def render_episode_trace_markdown(
    privileged_events_path: str | Path,
    controller_name: str,
    phenotype: str,
    episode_index: int = 0,
    max_steps: int = 25,
) -> str:
    """
    Renders a synchronized step-by-step trace table from stored event records
    reconciling proposed action, supervisor decision, actuator delivered exposure,
    plant state, observed reports, and controller belief updates.
    """
    path = Path(privileged_events_path)
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if (
                rec["controller_name"] == controller_name
                and rec["phenotype"] == phenotype
                and rec["episode_index"] == episode_index
            ):
                rows.append(rec)
    rows.sort(key=lambda r: int(r["step_k"]))
    rows = rows[:max_steps]

    lines = [
        f"### Synchronized Episode Trace: `{controller_name}` on `{phenotype}` (Episode {episode_index})",
        "",
        "| Step | Proposed | Approved | Latch | Contact | Deliv Inten | Status | Latent Pain | Sensitiz. | Obs Report (Status) | Belief `[Resp, Null, Wors]` | Total Loss |",
        "|---:|:---|:---|:---:|---:|---:|:---|---:|---:|:---|:---|---:|",
    ]
    for r in rows:
        prop_str = f"{r['proposed_stimulation']}:{r['proposed_target'] or '-'}"
        if r["feedback_requested"]:
            prop_str += "+Q"
        latch_str = "LATCH" if r["fault_latched_after"] else ("REARM" if r["rearmed_this_step"] else "ok")
        rep_val = r["observed_pain_report"]
        rep_str = f"{rep_val} ({r['report_status']})" if rep_val is not None else f"None ({r['report_status']})"
        b_info = r.get("controller_belief")
        if b_info and "belief" in b_info:
            b_vec = b_info["belief"]
            b_str = f"[{b_vec[0]:.2f}, {b_vec[1]:.2f}, {b_vec[2]:.2f}]"
        else:
            b_str = "-"
        lines.append(
            f"| {r['step_k']} | `{prop_str}` | `{r['approved_program_id']}` | {latch_str} | "
            f"{r['contact_factor']:.2f} | {r['delivered_intensity']:.2f} | `{r['delivery_status']}` | "
            f"{r['true_latent_pain']:.2f} | {r['delayed_sensitization']:.2f} | {rep_str} | `{b_str}` | {r['total_loss']:.2f} |"
        )
    return "\n".join(lines)


def generate_experiment_report(
    run_dir: str | Path,
    report_dir: str | Path,
) -> Dict[str, Any]:
    """
    Reads stored artifacts in `run_dir` and generates `report.md` and `report_summary.json`
    in `report_dir`. Never blocks report generation when an adaptive policy fails to beat baselines.
    """
    rdir = Path(run_dir)
    out_dir = Path(report_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = json.loads((rdir / "manifest.json").read_text(encoding="utf-8"))
    episodes = json.loads((rdir / "episodes.json").read_text(encoding="utf-8"))
    counterfactuals = json.loads((rdir / "counterfactuals.json").read_text(encoding="utf-8"))
    invalid_runs = json.loads((rdir / "invalid_runs.json").read_text(encoding="utf-8"))
    checksums = json.loads((rdir / "checksums.json").read_text(encoding="utf-8"))
    extra_path = rdir / "extra_analysis.json"
    extra = json.loads(extra_path.read_text(encoding="utf-8")) if extra_path.exists() else {}

    cfg = manifest["resolved_config"]
    alpha = float(cfg["evaluation"]["cvar_alpha"])
    phenotypes: List[str] = cfg["phenotypes"]
    controllers = sorted({ep["controller_name"] for ep in episodes})

    # Preferred ordering for readability
    order_map = {
        "C0_Off": 0,
        "C1_Fixed_P02_MOD_BURST": 1,
        "C2_CalibratedFixed": 2,
        "C3_ConservativeRules": 3,
        "C4_HeuristicFilter": 4,
        "C5_SequentialBayesian": 5,
        "C5_Ablation_FrozenBeliefs": 6,
        "C5_Ablation_ShuffledReports": 7,
        "C5_Ablation_MatchedSchedule": 8,
        "C6_SparseRecurrentEI": 9,
        "C6_Ablation_DenseRecurrent": 10,
    }
    controllers.sort(key=lambda c: (order_map.get(c, 99), c))

    agg_rows: List[Dict[str, Any]] = []
    for pheno in phenotypes:
        for cname in controllers:
            sub = [e for e in episodes if e["phenotype"] == pheno and e["controller_name"] == cname]
            if not sub:
                continue
            n = len(sub)
            tot_losses = [float(e["cumulative_total_loss"]) for e in sub]
            clin_losses = [float(e["cumulative_clinical_loss"]) for e in sub]
            safe_losses = [float(e["cumulative_safety_loss"]) for e in sub]
            pain_ints = [float(e["pain_time_integral"]) for e in sub]
            eff_ints = [float(e["delivered_effort_integral"]) for e in sub]
            queries = [int(e["total_queries_requested"]) for e in sub]
            conf_steps = [int(e["confirmed_active_delivery_steps"]) for e in sub]
            viols = [int(e["proposal_violations"]) for e in sub]
            viol_rates = [float(e["decision_violation_rate"]) for e in sub]
            updates = [int(e["posterior_update_count"]) for e in sub]

            h_keys = sorted({k for e in sub for k in e["mean_restricted_excess_by_horizon"].keys()})
            h_primary = h_keys[-1] if h_keys else "8"
            reg_vals = [
                float(e["mean_restricted_excess_by_horizon"][h_primary])
                for e in sub
                if h_primary in e["mean_restricted_excess_by_horizon"]
            ]

            agg_rows.append({
                "phenotype": pheno,
                "controller": cname,
                "n": n,
                "mean_pain_integral": sum(pain_ints) / n,
                "mean_clinical_loss": sum(clin_losses) / n,
                "mean_safety_loss": sum(safe_losses) / n,
                "mean_total_loss": sum(tot_losses) / n,
                "cvar90_total_loss": compute_exact_cvar(tot_losses, alpha=alpha),
                "mean_effort_integral": sum(eff_ints) / n,
                "mean_queries": sum(queries) / n,
                "mean_confirmed_active_steps": sum(conf_steps) / n,
                "total_proposal_violations": sum(viols),
                "mean_decision_violation_rate_pct": (sum(viol_rates) / n) * 100.0,
                "mean_posterior_updates": sum(updates) / n,
                "mean_restricted_excess_h": sum(reg_vals) / len(reg_vals) if reg_vals else 0.0,
            })

    # Engineering Gates vs Research Outcomes evaluation
    eng_gate_status = "PASS" if len(invalid_runs) == 0 else "FAIL"

    # Evaluate C5_SequentialBayesian vs C2_CalibratedFixed
    def _find_agg(pheno: str, ctrl: str) -> Dict[str, Any] | None:
        for r in agg_rows:
            if r["phenotype"] == pheno and r["controller"] == ctrl:
                return r
        return None

    c5_resp = _find_agg("responder", "C5_SequentialBayesian")
    c2_resp = _find_agg("responder", "C2_CalibratedFixed")
    c5_wors = _find_agg("delayed_worsening", "C5_SequentialBayesian")
    c2_wors = _find_agg("delayed_worsening", "C2_CalibratedFixed")
    c5_non = _find_agg("nonresponder", "C5_SequentialBayesian")
    c2_non = _find_agg("nonresponder", "C2_CalibratedFixed")

    research_outcome = "INCONCLUSIVE"
    if eng_gate_status == "PASS" and c5_resp and c2_resp and c5_wors and c2_wors and c5_non and c2_non:
        beats_worsening = c5_wors["mean_total_loss"] < c2_wors["mean_total_loss"]
        beats_worsening_tail = (
            c5_wors["cvar90_total_loss"]
            <= c2_wors["cvar90_total_loss"] + float(cfg["evaluation"]["worsening_cvar_abs_margin"])
        )
        nonresp_ok = (
            c5_non["cvar90_total_loss"]
            <= c2_non["cvar90_total_loss"] + float(cfg["evaluation"]["nonresponder_cvar_abs_margin"])
        )
        if beats_worsening and beats_worsening_tail and nonresp_ok:
            research_outcome = "SUPPORTED_UNDER_MODEL"
        else:
            research_outcome = "NOT_SUPPORTED_UNDER_MODEL"

    md_lines = [
        f"# NeuroLoop v0.4.0 — Reproducible Experiment Report (`{cfg['protocol_id']}`)",
        "",
        "## 1. Gate & Claim Status Summary",
        "",
        "| Dimension | Status | Scope / Verification Evidence |",
        "| :--- | :--- | :--- |",
        f"| **Engineering Instrument Gate** | **`{eng_gate_status}`** | `{len(invalid_runs)}` instrument failures; config SHA-256 `{manifest['config_sha256'][:16]}...` |",
        f"| **Research Outcome (Within-Model)** | **`{research_outcome}`** | Evaluated on `{cfg['engine_mode']}` (`{cfg['actuator_mode']}` actuator, `{cfg['frequency_response_mode']}`) |",
        f"| **Translation Status** | **`{cfg['claim_tier']}`** | Software-only synthetic model; no human clinical efficacy or hardware safety claim |",
        "",
        "## 2. Multi-Ledger Tournament Results by Phenotype",
        "",
        "| Phenotype | Controller | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Exact $\\text{CVaR}_{0.90}$ | Excess $\\widehat{R}_H^{\\mathcal{B}}$ | Confirmed Active Steps | Posterior Updates | Violation Rate (%) |",
        "| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for r in agg_rows:
        md_lines.append(
            f"| `{r['phenotype']}` | `{r['controller']}` | {r['mean_clinical_loss']:.2f} | "
            f"{r['mean_safety_loss']:.2f} | **{r['mean_total_loss']:.2f}** | "
            f"{r['cvar90_total_loss']:.2f} | {r['mean_restricted_excess_h']:+.2f} | "
            f"{r['mean_confirmed_active_steps']:.1f} | {r['mean_posterior_updates']:.1f} | "
            f"{r['mean_decision_violation_rate_pct']:.2f}% |"
        )

    if "paired_comparisons" in extra:
        md_lines.extend([
            "",
            "## 3. Paired Scenario-Level Excess Loss (`C5_SequentialBayesian` vs `C2_CalibratedFixed`)",
            "",
            "| Phenotype | $N$ Paired | Mean Excess Loss ($\\Delta L$) | 95% CI | Exact $\\text{CVaR}_{0.90}(\\Delta L)$ | Relative Loss Reduction (%) |",
            "| :--- | ---: | ---: | :--- | ---: | ---: |",
        ])
        for p_row in extra["paired_comparisons"]:
            md_lines.append(
                f"| `{p_row['phenotype']}` | {int(p_row['n_paired'])} | {p_row['mean_excess_loss']:+.2f} | "
                f"[{p_row['ci95_low']:+.2f}, {p_row['ci95_high']:+.2f}] | "
                f"{p_row['cvar_excess_loss']:+.2f} | {p_row['relative_reduction_pct']:+.2f}% |"
            )

    if "exact_small_pomdp" in extra:
        pomdp = extra["exact_small_pomdp"]
        md_lines.extend([
            "",
            "## 4. Decision Sufficiency & Sensor Information Gap (`G2`)",
            "",
            "### 4.1 Exact Finite Calibration POMDP Analytical Benchmark",
            f"- **Full-State Oracle Expected Loss ($J^*_{{\\text{{full}}}}$):** `{pomdp['full_state_oracle_expected_loss']:.4f}`",
            f"- **Bayes-Optimal Partial Observer Expected Loss ($J^*_{{\\text{{partial}}}}$):** `{pomdp['bayes_optimal_partial_expected_loss']:.4f}`",
            f"- **Blind Policy Expected Loss ($J^*_{{\\text{{blind}}}}$):** `{pomdp['blind_policy_expected_loss']:.4f}`",
            f"- **Exact Information Gap ($\\Delta_{{\\text{{info}}}} = J^*_{{\\text{{partial}}}} - J^*_{{\\text{{full}}}}$):** `{pomdp['exact_information_gap_partial_vs_oracle']:.4f}`",
            f"- **Exact Value of Observation ($J^*_{{\\text{{blind}}}} - J^*_{{\\text{{partial}}}}$):** `{pomdp['value_of_observation_blind_vs_partial']:.4f}`",
        ])

    if "sensor_ablations" in extra:
        md_lines.extend([
            "",
            "### 4.2 Reference-Policy Sensor Ablation Estimates (`REFERENCE_POLICY_ESTIMATE`)",
            "",
            "| Sensor Regime | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Est. Info Gap vs. Full-State Oracle |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ])
        for s_row in extra["sensor_ablations"]:
            md_lines.append(
                f"| `{s_row['sensor_regime']}` | {s_row['mean_clinical_loss']:.2f} | "
                f"{s_row['mean_safety_loss']:.2f} | {s_row['mean_total_loss']:.2f} | "
                f"{s_row['estimated_info_gap_vs_oracle']:+.2f} |"
            )

    if "transfer_challenges" in extra:
        md_lines.extend([
            "",
            "## 5. Cross-Engine Transfer (Engine A Mechanistic GHK/KCC2) & Waveform Sensitivity Challenges",
            "",
            "| Challenge | Phenotype | Controller | Mean Total Loss | Exact $\\text{CVaR}_{0.90}$ | Posterior Updates |",
            "| :--- | :--- | :--- | ---: | ---: | ---: |",
        ])
        for t_row in extra["transfer_challenges"]:
            md_lines.append(
                f"| `{t_row['challenge_name']}` | `{t_row['phenotype']}` | `{t_row['controller_name']}` | "
                f"{t_row['mean_total_loss']:.2f} | {t_row['cvar90_total_loss']:.2f} | "
                f"{t_row['mean_posterior_updates']:.1f} |"
            )

    # Include a sample episode trace
    priv_path = rdir / "privileged_events.jsonl"
    if priv_path.exists():
        trace_md = render_episode_trace_markdown(
            priv_path,
            controller_name="C5_SequentialBayesian",
            phenotype="delayed_worsening",
            episode_index=0,
            max_steps=16,
        )
        md_lines.extend(["", "## 6. Sample Synchronized Diagnostic Trace", "", trace_md])

    md_lines.extend([
        "",
        "## 7. Provenance & Checksums",
        f"- **Config SHA-256:** `{manifest['config_sha256']}`",
        f"- **Equation Registry SHA-256:** `{manifest['equation_registry_sha256']}`",
        f"- **Public Events SHA-256:** `{checksums['public_events_sha256']}`",
        f"- **Privileged Events SHA-256:** `{checksums['privileged_events_sha256']}`",
        f"- **Episodes JSON SHA-256:** `{checksums['episodes_sha256']}`",
    ])

    report_md_path = out_dir / "report.md"
    report_md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    summary_payload = {
        "engineering_gate_status": eng_gate_status,
        "research_outcome": research_outcome,
        "translation_status": cfg["claim_tier"],
        "config_sha256": manifest["config_sha256"],
        "aggregates": agg_rows,
        "extra_analysis": extra,
        "checksums": checksums,
    }
    (out_dir / "report_summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return summary_payload
