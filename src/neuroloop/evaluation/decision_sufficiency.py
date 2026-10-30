"""
Stage 3 (PR 5): Decision Sufficiency & Sensor Information Gap Evaluator.
Includes:
  1. An exact finite-state Bayes-optimal POMDP solver (`solve_exact_small_pomdp`) to
     mathematically validate the Information Gap calculator against an analytic solution.
  2. Reference-policy sensor ablation estimator (`estimate_sensor_information_gap`) comparing
     Full Sensors, Impedance-Only, Report-Only, and Blind policies against a full-state
     privileged oracle, explicitly labeled as a reference-policy approximation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from neuroloop.config import ProtocolConfig
from neuroloop.contracts import (
    ControlAction,
    FeedbackCommand,
    PublicObservation,
    StimulationCommand,
)
from neuroloop.controllers import AbstractController, _is_hardware_fault_visible
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.evaluation import precompute_patient_calibration, run_single_episode
from neuroloop.randomness import CanonicalScenarioKey


@dataclass(frozen=True)
class ExactSmallPOMDPResult:
    """Exact analytical Information Gap on a 2-step 3-phenotype calibration POMDP."""
    full_state_oracle_expected_loss: float
    bayes_optimal_partial_expected_loss: float
    blind_policy_expected_loss: float
    exact_information_gap_partial_vs_oracle: float
    value_of_observation_blind_vs_partial: float


def solve_exact_small_pomdp() -> ExactSmallPOMDPResult:
    """
    Solves a finite 2-stage 3-phenotype POMDP exactly by enumerating the binary observation
    tree (pain reduced: Y=1 vs pain increased/unchanged: Y=0 after a probe step) and computing
    exact Bayes-optimal actions in Stage 2:
      Hidden phenotypes theta in {responder (0.5), nonresponder (0.3), worsening (0.2)}
      Actions u in {OFF, STIM}
      Stage losses:
        - responder: L(OFF)=6.0, L(STIM)=3.2
        - nonresponder: L(OFF)=6.0, L(STIM)=6.4 (effort penalty with zero relief)
        - worsening: L(OFF)=6.0, L(STIM)=9.5 (sensitization + escalation penalty)
      Observation likelihood P(Y=1 | theta, u_0=STIM):
        - responder: 0.85
        - nonresponder: 0.15
        - worsening: 0.05
    """
    prior = {"responder": 0.50, "nonresponder": 0.30, "worsening": 0.20}
    loss_off = {"responder": 6.0, "nonresponder": 6.0, "worsening": 6.0}
    loss_stim = {"responder": 3.2, "nonresponder": 6.4, "worsening": 9.5}
    p_y1_given_stim = {"responder": 0.85, "nonresponder": 0.15, "worsening": 0.05}

    # 1. Full-state oracle knows theta at both stages (2 stages total)
    j_oracle = 0.0
    for th, p_th in prior.items():
        best_step_l = min(loss_off[th], loss_stim[th])
        j_oracle += p_th * (2.0 * best_step_l)

    # 2. Blind policy has no observations at either stage
    exp_step_off = sum(prior[th] * loss_off[th] for th in prior)
    exp_step_stim = sum(prior[th] * loss_stim[th] for th in prior)
    j_blind = 2.0 * min(exp_step_off, exp_step_stim)

    # 3. Bayes-optimal partial observer:
    # Option A: Stage 1 = OFF (uninformative), Stage 2 = best prior action
    j_opt_a = exp_step_off + min(exp_step_off, exp_step_stim)

    # Option B: Stage 1 = STIM + observe Y in {0, 1}, Stage 2 = Bayes-optimal action given Y
    p_y1 = sum(prior[th] * p_y1_given_stim[th] for th in prior)
    p_y0 = 1.0 - p_y1

    post_y1 = {th: (prior[th] * p_y1_given_stim[th]) / p_y1 for th in prior}
    post_y0 = {th: (prior[th] * (1.0 - p_y1_given_stim[th])) / p_y0 for th in prior}

    stage2_given_y1 = min(
        sum(post_y1[th] * loss_off[th] for th in prior),
        sum(post_y1[th] * loss_stim[th] for th in prior),
    )
    stage2_given_y0 = min(
        sum(post_y0[th] * loss_off[th] for th in prior),
        sum(post_y0[th] * loss_stim[th] for th in prior),
    )
    j_opt_b = exp_step_stim + (p_y1 * stage2_given_y1 + p_y0 * stage2_given_y0)

    j_partial_star = min(j_opt_a, j_opt_b)
    info_gap = j_partial_star - j_oracle
    voi = j_blind - j_partial_star

    return ExactSmallPOMDPResult(
        full_state_oracle_expected_loss=j_oracle,
        bayes_optimal_partial_expected_loss=j_partial_star,
        blind_policy_expected_loss=j_blind,
        exact_information_gap_partial_vs_oracle=info_gap,
        value_of_observation_blind_vs_partial=voi,
    )


class PrivilegedFullStateOracleController(AbstractController):
    """
    Evaluator-only full-state reference policy (never used as a deployable competitor).
    Selects the best preset for the known phenotype and exact fault window.
    """
    name = "Oracle_FullStateReference"

    def __init__(self, true_phenotype: str) -> None:
        self._true_phenotype = true_phenotype

    def reset(self, initial_obs: PublicObservation) -> None:
        pass

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        if _is_hardware_fault_visible(obs, max_safe_z=30_000.0) or (18 <= obs.step_k <= 24):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        if self._true_phenotype in ("nonresponder", "delayed_worsening", "null_effect", "baseline_flare"):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        prog = "P02_MOD_BURST" if (obs.step_k // 6) % 2 == 0 else "P01_LOW_CONV"
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=FeedbackCommand.NONE,
            target_program_id=prog,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, str]:
        return {"true_phenotype": self._true_phenotype}

    def restore(self, state: Dict[str, str]) -> None:
        self._true_phenotype = str(state["true_phenotype"])


@dataclass(frozen=True)
class SensorAblationEstimate:
    """
    Reference-policy Information Gap estimate across sensor modalities.
    Explicitly labeled as `approximation_status = 'REFERENCE_POLICY_ESTIMATE'`.
    """
    approximation_status: str
    sensor_regime: str
    mean_total_loss: float
    mean_clinical_loss: float
    mean_safety_loss: float
    estimated_info_gap_vs_oracle: float


def estimate_sensor_information_gap(
    config: ProtocolConfig,
    n_episodes_per_phenotype: int = 8,
) -> List[SensorAblationEstimate]:
    regimes = [
        ("Full_Sensors", False, False),
        ("Report_Only_NoImpedance", True, False),
        ("Impedance_Only_NoReports", False, True),
        ("Blind_NoImpedance_NoReports", True, True),
    ]

    oracle_losses: List[float] = []
    scenarios: List[CanonicalScenarioKey] = []
    for pheno in config.phenotypes:
        for ep_idx in range(n_episodes_per_phenotype):
            skey = CanonicalScenarioKey.create(
                config.protocol_namespace, pheno, ep_idx, config.seeds.scenario_offset
            )
            scenarios.append(skey)
            cal_rec = precompute_patient_calibration(config, skey)
            oracle_ctrl = PrivilegedFullStateOracleController(pheno)
            ep_sum, _, _ = run_single_episode(
                config=config,
                scenario_key=skey,
                local_episode_sequence=ep_idx,
                controller=oracle_ctrl,
                saved_calibration=cal_rec,
                comparators=[],
                enable_counterfactual_audits=False,
            )
            oracle_losses.append(ep_sum.cumulative_total_loss)

    mean_oracle = sum(oracle_losses) / max(1, len(oracle_losses))
    results: List[SensorAblationEstimate] = []

    for label, ablate_z, ablate_rep in regimes:
        tot_l: List[float] = []
        clin_l: List[float] = []
        safe_l: List[float] = []
        for idx, skey in enumerate(scenarios):
            cal_rec = precompute_patient_calibration(config, skey)
            ctrl = SequentialBayesianController(name_override=f"C5_{label}")
            ep_sum, _, _ = run_single_episode(
                config=config,
                scenario_key=skey,
                local_episode_sequence=idx,
                controller=ctrl,
                saved_calibration=cal_rec,
                comparators=[],
                enable_counterfactual_audits=False,
                ablate_impedance=ablate_z,
                ablate_reports=ablate_rep,
            )
            tot_l.append(ep_sum.cumulative_total_loss)
            clin_l.append(ep_sum.cumulative_clinical_loss)
            safe_l.append(ep_sum.cumulative_safety_loss)

        m_tot = sum(tot_l) / len(tot_l)
        m_clin = sum(clin_l) / len(clin_l)
        m_safe = sum(safe_l) / len(safe_l)
        results.append(
            SensorAblationEstimate(
                approximation_status="REFERENCE_POLICY_ESTIMATE",
                sensor_regime=label,
                mean_total_loss=m_tot,
                mean_clinical_loss=m_clin,
                mean_safety_loss=m_safe,
                estimated_info_gap_vs_oracle=m_tot - mean_oracle,
            )
        )

    return results
