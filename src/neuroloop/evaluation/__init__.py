"""
Privileged Scientific Evaluator: Exact Fractional-Mass CVaR, Checkpointed Twin-World
Counterfactual Rollouts with Saved Calibration Provenance, Separate Outcome Ledgers,
and Paired Uncertainty Intervals for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import copy
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from neuroloop.config import ProtocolConfig
from neuroloop.contracts import (
    ContractViolationError,
    ControlAction,
    DEFAULT_PROGRAM_CATALOG,
    FeedbackCommand,
    ProgramSpec,
    StimulationCommand,
    require_finite,
    require_range,
)
from neuroloop.controllers import (
    AbstractController,
    CalibratedFixedController,
    CalibrationRecord,
    ConservativeRulesController,
    FixedProgramController,
    HeuristicThreeHypothesisController,
    HoldComparatorController,
    OffController,
)
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.controllers.recurrent import RecurrentEIController
from neuroloop.orchestrator import ClosedLoopEnvironment, StepExecutionRecord, SystemCheckpoint
from neuroloop.randomness import CanonicalScenarioKey, SemanticRNG


def compute_exact_cvar(losses: Sequence[float], alpha: float = 0.90) -> float:
    """
    Computes exact empirical Conditional Value at Risk (CVaR_alpha) in the upper tail
    including fractional quantile-boundary probability mass:
      CVaR_alpha(X) = (1 / (1 - alpha)) * integral_{alpha}^{1} F^{-1}(u) du
    Raises ContractViolationError on empty or non-finite inputs.
    """
    if not losses:
        raise ContractViolationError("Cannot compute CVaR on an empty outcome sequence.")
    a = require_range(alpha, "alpha", 0.01, 0.9999)
    cleaned = [require_finite(x, "loss_item") for x in losses]
    sorted_x = sorted(cleaned)
    n = len(sorted_x)
    if n == 1:
        return sorted_x[0]

    exact_cutoff = a * n
    k = int(math.floor(exact_cutoff))
    if k >= n:
        return sorted_x[-1]

    frac_weight = (k + 1) - exact_cutoff
    weighted_sum = frac_weight * sorted_x[k]
    for i in range(k + 1, n):
        weighted_sum += sorted_x[i]

    tail_mass = (1.0 - a) * n
    return weighted_sum / tail_mass


@dataclass(frozen=True)
class CounterfactualAuditRecord:
    """Record of a multi-replicate Twin-World counterfactual audit at checkpoint step_k."""
    scenario_digest: str
    phenotype: str
    episode_index: int
    candidate_controller: str
    checkpoint_step_k: int
    horizon_steps: int
    recovery_tail_steps: int
    num_replicates: int
    candidate_mean_loss: float
    comparator_mean_losses: Dict[str, float]
    pairwise_excess_losses: Dict[str, float]
    restricted_comparator_excess_loss: float
    selected_best_comparator: str
    calibrated_comparator_program: str


def evaluate_checkpoint_forks(
    env: ClosedLoopEnvironment,
    checkpoint: SystemCheckpoint,
    candidate_controller: AbstractController,
    comparators: Sequence[AbstractController],
    base_rng: SemanticRNG,
    horizon_steps: int,
    recovery_tail_steps: int,
    num_replicates: int,
    discount_gamma: float,
) -> CounterfactualAuditRecord:
    """
    Evaluates candidate_controller and each comparator from the EXACT same SystemCheckpoint
    across `num_replicates` shared future-noise paths (`audit_replicate = 1..R`), followed by
    `recovery_tail_steps` of OFF observation to capture delayed sensitization.
    Leaves `env` and `candidate_controller` completely unchanged after completion.
    """
    k0 = checkpoint.step_k

    def _rollout_single_policy(policy_proto: AbstractController, rep_idx: int) -> float:
        fork_rng = base_rng.fork_replicate(audit_replicate=rep_idx, fork_after_step=k0 - 1)
        fork_policy = policy_proto.clone()
        env.restore_checkpoint(checkpoint, controller=None, rng_override=fork_rng)

        # If this policy is the candidate itself, restore its exact checkpointed state
        if fork_policy.name == candidate_controller.name and type(fork_policy) is type(candidate_controller):
            fork_policy.restore(checkpoint.controller_snapshot)
        elif checkpoint.calibration_record is not None:
            # Supply the patient's actual saved calibration record to calibrated comparators
            fork_policy.set_calibration_record(checkpoint.calibration_record)

        discounted_loss = 0.0
        for j in range(horizon_steps):
            obs = env.current_observation
            action = fork_policy.act(obs)
            step_rec = env.step(action, controller_belief=fork_policy.get_belief_summary())
            discounted_loss += (discount_gamma ** j) * step_rec.loss.total_loss

        # Prespecified post-horizon recovery observation tail under OFF stimulation
        for t_idx in range(recovery_tail_steps):
            obs = env.current_observation
            off_action = ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=obs.timing_meta.observation_sequence,
            )
            step_rec = env.step(off_action, controller_belief=None)
            discounted_loss += (discount_gamma ** (horizon_steps + t_idx)) * step_rec.loss.total_loss

        return discounted_loss

    cand_rep_losses = [_rollout_single_policy(candidate_controller, r) for r in range(1, num_replicates + 1)]
    cand_mean = sum(cand_rep_losses) / len(cand_rep_losses)

    comp_means: Dict[str, float] = {}
    pairwise_excess: Dict[str, float] = {}
    for comp in comparators:
        rep_losses = [_rollout_single_policy(comp, r) for r in range(1, num_replicates + 1)]
        c_mean = sum(rep_losses) / len(rep_losses)
        comp_means[comp.name] = c_mean
        pairwise_excess[comp.name] = cand_mean - c_mean

    # Restore primary environment and controller state so auditing has zero side effect
    env.restore_checkpoint(checkpoint, controller=candidate_controller, rng_override=base_rng)

    best_comp_name = min(comp_means.keys(), key=lambda cname: comp_means[cname])
    best_comp_loss = comp_means[best_comp_name]
    restricted_excess = cand_mean - best_comp_loss
    cal_prog = (
        checkpoint.calibration_record.selected_program_id
        if checkpoint.calibration_record is not None
        else "uncalibrated"
    )

    return CounterfactualAuditRecord(
        scenario_digest=base_rng.scenario_key.scenario_digest,
        phenotype=base_rng.scenario_key.phenotype,
        episode_index=base_rng.scenario_key.episode_index,
        candidate_controller=candidate_controller.name,
        checkpoint_step_k=k0,
        horizon_steps=horizon_steps,
        recovery_tail_steps=recovery_tail_steps,
        num_replicates=num_replicates,
        candidate_mean_loss=cand_mean,
        comparator_mean_losses=comp_means,
        pairwise_excess_losses=pairwise_excess,
        restricted_comparator_excess_loss=restricted_excess,
        selected_best_comparator=best_comp_name,
        calibrated_comparator_program=cal_prog,
    )


@dataclass(frozen=True)
class EpisodeSummaryRecord:
    """
    Complete multi-ledger summary of one episode.
    Separates Clinical Burden, Treatment Burden, Safety Ledger, and Counterfactual Excess Loss.
    """
    scenario_digest: str
    phenotype: str
    episode_index: int
    local_episode_sequence: int
    controller_name: str
    total_steps: int
    # Ledger 1: Clinical Surrogate Burden
    pain_time_integral: float
    mean_latent_pain: float
    functional_time_integral: float
    cumulative_clinical_loss: float
    # Ledger 2: Treatment & Query Burden
    delivered_effort_integral: float
    total_queries_requested: int
    final_query_burden: float
    confirmed_active_delivery_steps: int
    partial_delivery_steps: int
    # Ledger 3: Safety & Supervisor Ledger
    proposal_violations: int
    decision_violation_rate: float
    fault_delivery_steps: int
    worsening_escalation_steps: int
    total_fault_stops: int
    total_rearms: int
    max_stop_latency_ms: int
    cumulative_safety_loss: float
    # Combined & Learning Diagnostics
    cumulative_total_loss: float
    posterior_update_count: int
    final_belief: Optional[List[float]]
    calibrated_program_id: Optional[str]
    # Counterfactual Summary
    mean_restricted_excess_by_horizon: Dict[int, float]
    mean_pairwise_excess_vs_calibrated: Dict[int, float]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["mean_restricted_excess_by_horizon"] = {
            str(k): v for k, v in self.mean_restricted_excess_by_horizon.items()
        }
        d["mean_pairwise_excess_vs_calibrated"] = {
            str(k): v for k, v in self.mean_pairwise_excess_vs_calibrated.items()
        }
        return d


def precompute_patient_calibration(
    config: ProtocolConfig,
    scenario_key: CanonicalScenarioKey,
    program_catalog: Optional[Mapping[str, ProgramSpec]] = None,
) -> CalibrationRecord:
    """
    Runs the shared calibration protocol on the scenario to obtain the patient's
    saved CalibrationRecord before evaluating continuation policies and comparators.
    """
    rng = SemanticRNG(config.seeds.master_seed, scenario_key)
    env = ClosedLoopEnvironment(
        config=config,
        scenario_key=scenario_key,
        local_episode_sequence=0,
        program_catalog=program_catalog,
        rng=rng,
    )
    cal_ctrl = CalibratedFixedController()
    cal_ctrl.reset(env.current_observation)
    cal_steps = max(7, config.timing.calibration_steps + config.timing.report_delay_steps + 1)
    for _ in range(min(cal_steps, config.timing.episode_steps)):
        obs = env.current_observation
        act = cal_ctrl.act(obs)
        env.step(act, controller_belief=None)
        rec = cal_ctrl.get_calibration_record()
        if rec is not None and rec.calibration_completed:
            return rec
    rec = cal_ctrl.get_calibration_record()
    assert rec is not None
    rec.calibration_completed = True
    return rec


def run_single_episode(
    config: ProtocolConfig,
    scenario_key: CanonicalScenarioKey,
    local_episode_sequence: int,
    controller: AbstractController,
    saved_calibration: CalibrationRecord,
    comparators: Sequence[AbstractController],
    enable_counterfactual_audits: bool = True,
    program_catalog: Optional[Mapping[str, ProgramSpec]] = None,
    ablate_impedance: bool = False,
    ablate_reports: bool = False,
) -> Tuple[EpisodeSummaryRecord, List[StepExecutionRecord], List[CounterfactualAuditRecord]]:
    rng = SemanticRNG(config.seeds.master_seed, scenario_key)
    env = ClosedLoopEnvironment(
        config=config,
        scenario_key=scenario_key,
        local_episode_sequence=local_episode_sequence,
        program_catalog=program_catalog,
        rng=rng,
        ablate_impedance=ablate_impedance,
        ablate_reports=ablate_reports,
    )
    env.set_saved_calibration(saved_calibration)

    ctrl = controller.clone()
    ctrl.reset(env.current_observation)

    step_records: List[StepExecutionRecord] = []
    audit_records: List[CounterfactualAuditRecord] = []

    audit_steps_set = set(config.counterfactual.audit_steps) if enable_counterfactual_audits else set()

    for step_k in range(config.timing.episode_steps):
        if step_k in audit_steps_set and comparators:
            ckpt = env.create_checkpoint(ctrl)
            if ckpt.calibration_record is None or not ckpt.calibration_record.calibration_completed:
                ckpt.calibration_record = copy.deepcopy(saved_calibration)
            for h in config.counterfactual.horizons_steps:
                audit_rec = evaluate_checkpoint_forks(
                    env=env,
                    checkpoint=ckpt,
                    candidate_controller=ctrl,
                    comparators=comparators,
                    base_rng=rng,
                    horizon_steps=h,
                    recovery_tail_steps=config.timing.recovery_tail_steps,
                    num_replicates=config.counterfactual.num_noise_replicates,
                    discount_gamma=config.counterfactual.discount_gamma,
                )
                audit_records.append(audit_rec)

        obs = env.current_observation
        action = ctrl.act(obs)
        belief_info = ctrl.get_belief_summary()
        step_rec = env.step(action, controller_belief=belief_info)
        step_records.append(step_rec)

    # Aggregate ledgers
    n_steps = len(step_records)
    pain_int = sum(r.plant_output.true_latent_pain * (r.exposure.dt_sec / 30.0) for r in step_records)
    func_int = sum(r.plant_output.true_functional_impairment * (r.exposure.dt_sec / 30.0) for r in step_records)
    cum_clin = sum(r.loss.clinical_loss for r in step_records)
    effort_int = sum(r.exposure.stimulation_effort for r in step_records)
    total_q = sum(1 for r in step_records if r.supervision.feedback_requested)
    final_qb = step_records[-1].plant_output.query_burden if step_records else 0.0
    conf_active = sum(
        1 for r in step_records if r.exposure.delivered_intensity > 0.05 and r.exposure.delivery_confirmed
    )
    part_steps = sum(1 for r in step_records if r.exposure.delivery_status.value == "PARTIAL")

    viol_count = sum(1 for r in step_records if r.loss.proposal_violated)
    fault_del_steps = sum(1 for r in step_records if r.exposure.compliance_limited and r.exposure.requested_intensity > 0)
    worsen_esc_steps = sum(
        1 for r in step_records if r.plant_output.delayed_sensitization > 1.10 and r.exposure.delivered_intensity > 0
    )
    sup_stops = sum(1 for r in step_records if not r.supervision.fault_latched_before and r.supervision.fault_latched_after)
    sup_rearms = sum(1 for r in step_records if r.supervision.rearmed_this_step)
    max_lat_ms = max((r.supervision.stop_latency_ms for r in step_records), default=0)
    cum_safe = sum(r.loss.safety_loss for r in step_records)
    cum_tot = sum(r.loss.total_loss for r in step_records)

    final_b_summary = ctrl.get_belief_summary()
    post_updates = int(final_b_summary.get("posterior_update_count", final_b_summary.get("update_count", 0))) if final_b_summary else 0
    final_b_vec = list(final_b_summary["belief"]) if (final_b_summary and "belief" in final_b_summary) else None
    cal_rec_final = ctrl.get_calibration_record() or saved_calibration
    cal_prog_id = cal_rec_final.selected_program_id if cal_rec_final else None

    mean_rest_by_h: Dict[int, float] = {}
    mean_pair_cal_by_h: Dict[int, float] = {}
    for h in config.counterfactual.horizons_steps:
        sub_a = [a for a in audit_records if a.horizon_steps == h]
        if sub_a:
            mean_rest_by_h[h] = sum(a.restricted_comparator_excess_loss for a in sub_a) / len(sub_a)
            cal_vals = [
                a.pairwise_excess_losses["C2_CalibratedFixed"]
                for a in sub_a
                if "C2_CalibratedFixed" in a.pairwise_excess_losses
            ]
            if cal_vals:
                mean_pair_cal_by_h[h] = sum(cal_vals) / len(cal_vals)

    summary = EpisodeSummaryRecord(
        scenario_digest=scenario_key.scenario_digest,
        phenotype=scenario_key.phenotype,
        episode_index=scenario_key.episode_index,
        local_episode_sequence=local_episode_sequence,
        controller_name=ctrl.name,
        total_steps=n_steps,
        pain_time_integral=pain_int,
        mean_latent_pain=pain_int / max(1, n_steps),
        functional_time_integral=func_int,
        cumulative_clinical_loss=cum_clin,
        delivered_effort_integral=effort_int,
        total_queries_requested=total_q,
        final_query_burden=final_qb,
        confirmed_active_delivery_steps=conf_active,
        partial_delivery_steps=part_steps,
        proposal_violations=viol_count,
        decision_violation_rate=viol_count / max(1, n_steps),
        fault_delivery_steps=fault_del_steps,
        worsening_escalation_steps=worsen_esc_steps,
        total_fault_stops=sup_stops,
        total_rearms=sup_rearms,
        max_stop_latency_ms=max_lat_ms,
        cumulative_safety_loss=cum_safe,
        cumulative_total_loss=cum_tot,
        posterior_update_count=post_updates,
        final_belief=final_b_vec,
        calibrated_program_id=cal_prog_id,
        mean_restricted_excess_by_horizon=mean_rest_by_h,
        mean_pairwise_excess_vs_calibrated=mean_pair_cal_by_h,
    )
    return summary, step_records, audit_records


def compute_paired_excess_summary(
    episodes: Sequence[EpisodeSummaryRecord],
    candidate_name: str,
    baseline_name: str,
    phenotype: str,
    alpha: float = 0.90,
) -> Dict[str, float]:
    """
    Computes paired scenario-level excess loss (L_candidate - L_baseline) on identical
    scenario digests, reporting mean excess, standard error, 95% confidence interval,
    and CVaR_alpha of paired excess loss.
    """
    cand_by_scen = {
        e.scenario_digest: e.cumulative_total_loss
        for e in episodes
        if e.controller_name == candidate_name and e.phenotype == phenotype
    }
    base_by_scen = {
        e.scenario_digest: e.cumulative_total_loss
        for e in episodes
        if e.controller_name == baseline_name and e.phenotype == phenotype
    }
    shared_keys = sorted(set(cand_by_scen.keys()) & set(base_by_scen.keys()))
    if not shared_keys:
        raise ContractViolationError(
            f"No paired scenarios found for {candidate_name} vs {baseline_name} on {phenotype}"
        )
    diffs = [cand_by_scen[k] - base_by_scen[k] for k in shared_keys]
    n = len(diffs)
    mean_diff = sum(diffs) / n
    if n > 1:
        var_diff = sum((d - mean_diff) ** 2 for d in diffs) / (n - 1)
        se_diff = math.sqrt(var_diff / n)
    else:
        se_diff = 0.0
    ci95_low = mean_diff - 1.96 * se_diff
    ci95_high = mean_diff + 1.96 * se_diff
    cvar_diff = compute_exact_cvar(diffs, alpha=alpha)
    base_mean = sum(base_by_scen[k] for k in shared_keys) / n
    rel_reduction_pct = ((base_mean - (base_mean + mean_diff)) / max(1e-9, base_mean)) * 100.0
    return {
        "n_paired": float(n),
        "mean_excess_loss": mean_diff,
        "se_excess_loss": se_diff,
        "ci95_low": ci95_low,
        "ci95_high": ci95_high,
        "cvar_excess_loss": cvar_diff,
        "relative_reduction_pct": rel_reduction_pct,
    }


def build_default_tournament_controllers(include_ablations: bool = True) -> List[AbstractController]:
    ctrls: List[AbstractController] = [
        OffController(),
        FixedProgramController("P02_MOD_BURST"),
        CalibratedFixedController(),
        ConservativeRulesController(),
        HeuristicThreeHypothesisController(),
        SequentialBayesianController(),
        RecurrentEIController(ablate_ei_structure=False),
    ]
    if include_ablations:
        ctrls.extend([
            SequentialBayesianController(freeze_beliefs=True),
            SequentialBayesianController(shuffle_reports=True),
            SequentialBayesianController(matched_schedule_heuristic=True),
            RecurrentEIController(ablate_ei_structure=True),
        ])
    return ctrls


def build_default_comparators() -> List[AbstractController]:
    return [
        HoldComparatorController(),
        OffController(),
        CalibratedFixedController(),
    ]
