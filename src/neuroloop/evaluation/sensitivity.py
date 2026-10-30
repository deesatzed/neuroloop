"""Extended 2x2x2 Engine x Actuator x Habituation and Report-Delay Sensitivity Suite."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from neuroloop.config import ProtocolConfig
from neuroloop.controllers import (
    AbstractController,
    CalibratedFixedController,
    ConservativeRulesController,
    OffController,
)
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.controllers.recurrent import RecurrentEIController
from neuroloop.evaluation import (
    compute_exact_cvar,
    precompute_patient_calibration,
    run_single_episode,
)
from neuroloop.evaluation.decision_sufficiency import (
    estimate_sensor_information_gap,
    solve_exact_small_pomdp,
)
from neuroloop.randomness import CanonicalScenarioKey


def run_sensitivity_suite(
    base_config: ProtocolConfig,
    output_dir: str | Path,
    n_episodes_per_phenotype: int = 10,
) -> dict[str, Any]:
    """Run the 2x2x2 (Engine x Actuator x Habituation) matrix and Report-Delay sweep (`[0, 1, 2, 3]`)."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    phenotypes = ["responder", "nonresponder", "delayed_worsening"]

    # 1. 2x2x2 Matrix: Engine (B vs A) x Actuator (normalized vs toy_resistive) x Habituation (burst_slows vs neutral)
    engines = ["engine_b_phenomenological", "engine_a_mechanistic"]
    actuators = ["normalized", "toy_resistive"]
    habituations = ["burst_slows_habituation", "frequency_neutral"]

    matrix_results: list[dict[str, Any]] = []
    for engine_name in engines:
        for actuator_name in actuators:
            for hab_mode in habituations:
                cell_id = f"{engine_name}__{actuator_name}__{hab_mode}"
                cfg_dict = base_config.to_dict()
                cfg_dict["engine_mode"] = engine_name
                cfg_dict["actuator_mode"] = actuator_name
                cfg_dict["frequency_response_mode"] = hab_mode
                cfg_dict["protocol_namespace"] = f"{base_config.protocol_namespace}_{cell_id}"
                cfg = ProtocolConfig.from_mapping(cfg_dict)

                controllers: list[AbstractController] = [
                    OffController(),
                    CalibratedFixedController(),
                    ConservativeRulesController(),
                    SequentialBayesianController(),
                    SequentialBayesianController(
                        freeze_beliefs=True,
                        name_override="C5_Ablation_FrozenBeliefs",
                    ),
                    RecurrentEIController(ablate_ei_structure=False),
                ]

                for phenotype in phenotypes:
                    scenarios = [
                        CanonicalScenarioKey.create(
                            cfg.protocol_namespace,
                            phenotype,
                            ep_idx,
                            cfg.seeds.scenario_offset,
                        )
                        for ep_idx in range(n_episodes_per_phenotype)
                    ]
                    cal_records = [precompute_patient_calibration(cfg, sk) for sk in scenarios]

                    for ctrl in controllers:
                        losses: list[float] = []
                        clinical_losses: list[float] = []
                        safety_losses: list[float] = []
                        active_steps: list[int] = []
                        updates: list[int] = []
                        for idx, (skey, cal_rec) in enumerate(zip(scenarios, cal_records)):
                            ep_sum, _, _ = run_single_episode(
                                config=cfg,
                                scenario_key=skey,
                                local_episode_sequence=idx,
                                controller=ctrl,
                                saved_calibration=cal_rec,
                                comparators=[],
                                enable_counterfactual_audits=False,
                            )
                            losses.append(float(ep_sum.cumulative_total_loss))
                            clinical_losses.append(float(ep_sum.cumulative_clinical_loss))
                            safety_losses.append(float(ep_sum.cumulative_safety_loss))
                            active_steps.append(int(ep_sum.confirmed_active_delivery_steps))
                            updates.append(int(ep_sum.posterior_update_count))
                        n = len(losses)
                        matrix_results.append(
                            {
                                "cell_id": cell_id,
                                "plant_engine": engine_name,
                                "actuator_mode": actuator_name,
                                "habituation_assumption": hab_mode,
                                "phenotype": phenotype,
                                "controller_id": ctrl.name,
                                "n_episodes": n,
                                "mean_clinical_loss": round(sum(clinical_losses) / n, 4),
                                "mean_safety_loss": round(sum(safety_losses) / n, 4),
                                "mean_total_loss": round(sum(losses) / n, 4),
                                "cvar_90_total_loss": round(compute_exact_cvar(losses, 0.90), 4),
                                "mean_active_steps": round(sum(active_steps) / n, 2),
                                "mean_posterior_updates": round(sum(updates) / n, 2),
                            }
                        )

    # 2. Multi-step Report Delay Sweep: report_delay_steps in [0, 1, 2, 3]
    delay_results: list[dict[str, Any]] = []
    for delay_steps in [0, 1, 2, 3]:
        cfg_dict = base_config.to_dict()
        cfg_dict["engine_mode"] = "engine_b_phenomenological"
        cfg_dict["actuator_mode"] = "normalized"
        cfg_dict["frequency_response_mode"] = "burst_slows_habituation"
        cfg_dict["timing"]["report_delay_steps"] = delay_steps
        cfg_dict["protocol_namespace"] = f"{base_config.protocol_namespace}_delay_{delay_steps}"
        cfg = ProtocolConfig.from_mapping(cfg_dict)

        delay_controllers: list[AbstractController] = [
            CalibratedFixedController(),
            SequentialBayesianController(),
            SequentialBayesianController(
                freeze_beliefs=True,
                name_override="C5_Ablation_FrozenBeliefs",
            ),
            RecurrentEIController(ablate_ei_structure=False),
        ]

        for phenotype in phenotypes:
            scenarios = [
                CanonicalScenarioKey.create(
                    cfg.protocol_namespace,
                    phenotype,
                    ep_idx,
                    cfg.seeds.scenario_offset,
                )
                for ep_idx in range(n_episodes_per_phenotype)
            ]
            cal_records = [precompute_patient_calibration(cfg, sk) for sk in scenarios]

            for ctrl in delay_controllers:
                losses = []
                safety_losses = []
                active_steps = []
                for idx, (skey, cal_rec) in enumerate(zip(scenarios, cal_records)):
                    ep_sum, _, _ = run_single_episode(
                        config=cfg,
                        scenario_key=skey,
                        local_episode_sequence=idx,
                        controller=ctrl,
                        saved_calibration=cal_rec,
                        comparators=[],
                        enable_counterfactual_audits=False,
                    )
                    losses.append(float(ep_sum.cumulative_total_loss))
                    safety_losses.append(float(ep_sum.cumulative_safety_loss))
                    active_steps.append(int(ep_sum.confirmed_active_delivery_steps))
                n = len(losses)
                delay_results.append(
                    {
                        "report_delay_steps": delay_steps,
                        "phenotype": phenotype,
                        "controller_id": ctrl.name,
                        "n_episodes": n,
                        "mean_total_loss": round(sum(losses) / n, 4),
                        "mean_safety_loss": round(sum(safety_losses) / n, 4),
                        "cvar_90_total_loss": round(compute_exact_cvar(losses, 0.90), 4),
                        "mean_active_steps": round(sum(active_steps) / n, 2),
                    }
                )

    pomdp_result = asdict(solve_exact_small_pomdp())
    sensor_gap = [asdict(r) for r in estimate_sensor_information_gap(base_config, n_episodes_per_phenotype=8)]

    payload = {
        "matrix_2x2x2": matrix_results,
        "report_delay_sweep": delay_results,
        "exact_pomdp": pomdp_result,
        "sensor_information_gap": sensor_gap,
    }

    json_path = out_path / "sensitivity_matrix.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    # Render Markdown report
    lines = [
        "# NeuroLoop v0.4.0 — Extended 2×2×2 Transfer Matrix & Report-Delay Sensitivity Report",
        "",
        "## 1. Exact Finite Calibration POMDP & Sensor Information-Gap Analysis (`G2`)",
        "",
        f"- **Full-State Oracle Expected Loss ($J^*_{{\\text{{full}}}}$):** `{pomdp_result['full_state_oracle_expected_loss']:.4f}`",
        f"- **Bayes-Optimal Partial Observer Expected Loss ($J^*_{{\\text{{partial}}}}$):** `{pomdp_result['bayes_optimal_partial_expected_loss']:.4f}`",
        f"- **Blind Policy Expected Loss ($J^*_{{\\text{{blind}}}}$):** `{pomdp_result['blind_policy_expected_loss']:.4f}`",
        f"- **Exact Information Gap ($\\Delta_{{\\text{{info}}}} = J^*_{{\\text{{partial}}}} - J^*_{{\\text{{full}}}}$):** `{pomdp_result['exact_information_gap_partial_vs_oracle']:.4f}`",
        f"- **Exact Value of Observation ($J^*_{{\\text{{blind}}}} - J^*_{{\\text{{partial}}}}$):** `{pomdp_result['value_of_observation_blind_vs_partial']:.4f}`",
        "",
        "| Sensor Regime | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Est. Info Gap vs. Full-State Oracle |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for row in sensor_gap:
        lines.append(
            f"| `{row['sensor_regime']}` | {row['mean_clinical_loss']:.2f} | {row['mean_safety_loss']:.2f} | "
            f"**{row['mean_total_loss']:.2f}** | {row['estimated_info_gap_vs_oracle']:+.2f} |"
        )

    lines.extend(
        [
            "",
            "## 2. 2×2×2 Factorial Sensitivity Matrix (`Engine` × `Actuator` × `Habituation`)",
            "",
            "| Engine | Actuator | Habituation | Phenotype | `C2_CalibratedFixed` Loss ($\\text{CVaR}_{0.90}$) | `C5_SequentialBayesian` Loss ($\\text{CVaR}_{0.90}$) | `C5_FrozenBeliefs` Loss | Paired Advantage ($\\Delta L = C5 - C2$) |",
            "| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: |",
        ]
    )

    grouped: dict[tuple[str, str, str, str], dict[str, dict[str, Any]]] = {}
    for r in matrix_results:
        key = (r["plant_engine"], r["actuator_mode"], r["habituation_assumption"], r["phenotype"])
        grouped.setdefault(key, {})[r["controller_id"]] = r

    for (eng, act, hab, phen), cmap in grouped.items():
        c2 = cmap["C2_CalibratedFixed"]
        c5 = cmap["C5_SequentialBayesian"]
        c5_frz = cmap["C5_Ablation_FrozenBeliefs"]
        diff = c5["mean_total_loss"] - c2["mean_total_loss"]
        lines.append(
            f"| `{eng}` | `{act}` | `{hab}` | `{phen}` | "
            f"{c2['mean_total_loss']:.2f} ({c2['cvar_90_total_loss']:.2f}) | "
            f"**{c5['mean_total_loss']:.2f}** ({c5['cvar_90_total_loss']:.2f}) | "
            f"{c5_frz['mean_total_loss']:.2f} | **{diff:+.2f}** |"
        )

    lines.extend(
        [
            "",
            "## 3. Multi-Step Report-Lag Sensitivity Sweep (`report_delay_steps` $\\in \\{0, 1, 2, 3\\}$)",
            "",
            "| Report Delay (steps) | Phenotype | `C2_CalibratedFixed` Loss | `C5_SequentialBayesian` Loss ($\\text{CVaR}_{0.90}$) | `C5` Active Steps | `C5_FrozenBeliefs` Loss | `C6_SparseRecurrentEI` Loss |",
            "| :---: | :--- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    delay_grouped: dict[tuple[int, str], dict[str, dict[str, Any]]] = {}
    for r in delay_results:
        delay_grouped.setdefault((r["report_delay_steps"], r["phenotype"]), {})[r["controller_id"]] = r

    for (dsteps, phen), cmap in sorted(delay_grouped.items()):
        c2 = cmap["C2_CalibratedFixed"]
        c5 = cmap["C5_SequentialBayesian"]
        c5f = cmap["C5_Ablation_FrozenBeliefs"]
        c6 = cmap["C6_SparseRecurrentEI"]
        lines.append(
            f"| `{dsteps}` ({dsteps * 30}s) | `{phen}` | {c2['mean_total_loss']:.2f} | "
            f"**{c5['mean_total_loss']:.2f}** ({c5['cvar_90_total_loss']:.2f}) | "
            f"{c5['mean_active_steps']:.1f} | {c5f['mean_total_loss']:.2f} | {c6['mean_total_loss']:.2f} |"
        )

    md_path = out_path / "sensitivity_matrix.md"
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return payload
