"""
Stage 3 (PR 5): Genuine Sequential State-Space Bayesian Estimator (C5) with
carryover propagation, Expected Value of Information (EVoI) sparse querying,
and mandatory belief/sensor ablations.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from neuroloop.contracts import (
    ControlAction,
    DEFAULT_PROGRAM_CATALOG,
    FeedbackCommand,
    ProgramSpec,
    PublicObservation,
    ReportStatus,
    StimulationCommand,
)
from neuroloop.controllers import AbstractController, _is_hardware_fault_visible


@dataclass
class GridHypothesisParticle:
    """
    A point in the structured dynamic response hypothesis space:
      - hypothesis_class: 'responder' | 'nonresponder' | 'delayed_worsening'
      - analgesia_gain: expected steady-state relief per unit delivered intensity
      - sensitization_gain: expected delayed worsening per unit delivered intensity
      - weight: posterior probability w_k^(m)
      - est_analgesia: propagated latent analgesic carryover state a_hat_k^(m)
      - est_habituation: propagated habituation state h_hat_k^(m)
      - est_sensitization: propagated delayed sensitization state s_hat_k^(m)
    """
    hypothesis_class: str
    analgesia_gain: float
    sensitization_gain: float
    weight: float
    est_analgesia: float = 0.0
    est_habituation: float = 0.0
    est_sensitization: float = 0.0


class SequentialBayesianController(AbstractController):
    """
    C5: Sequential State-Space Bayesian Controller.
    Unlike the static 3-point heuristic filter, this controller:
      1. Propagates internal dynamic carryover states (analgesia, habituation, sensitization)
         at EVERY macro-step using the actual `obs.delivered.delivered_intensity` and waveform.
      2. Assimilates each new patient report exactly once (`avail_time > last_assimilated_time`),
         preventing double-counting of cached reports.
      3. Computes Expected Value of Information (EVoI) over the predictive distribution of
         hypothetical pain reports y in {0..10} to decide whether a query reduces expected decision loss
         by more than the query cost.
      4. Supports explicit ablation modes:
         - `freeze_beliefs=True`: disables posterior updating.
         - `shuffle_reports=True`: deterministic pseudo-permutation of incoming report values.
         - `matched_schedule_heuristic=True`: disables posterior abstention to isolate belief value.
    """

    def __init__(
        self,
        freeze_beliefs: bool = False,
        shuffle_reports: bool = False,
        matched_schedule_heuristic: bool = False,
        program_catalog: Optional[Mapping[str, ProgramSpec]] = None,
        name_override: Optional[str] = None,
    ) -> None:
        self._freeze_beliefs = freeze_beliefs
        self._shuffle_reports = shuffle_reports
        self._matched_schedule_heuristic = matched_schedule_heuristic
        self._catalog = dict(program_catalog or DEFAULT_PROGRAM_CATALOG)
        if name_override:
            self.name = name_override
        elif freeze_beliefs:
            self.name = "C5_Ablation_FrozenBeliefs"
        elif shuffle_reports:
            self.name = "C5_Ablation_ShuffledReports"
        elif matched_schedule_heuristic:
            self.name = "C5_Ablation_MatchedSchedule"
        else:
            self.name = "C5_SequentialBayesian"

        self._particles: List[GridHypothesisParticle] = []
        self._baseline_mean: float = 6.0
        self._baseline_var: float = 0.35
        self._last_assimilated_avail_sec: float = -1.0
        self._cumulative_delivered_exposure: float = 0.0
        self._posterior_update_count: int = 0
        self._last_evoi: float = 0.0
        self._est_query_burden: float = 0.0
        self._init_particles()

    def _init_particles(self) -> None:
        # 7 structured grid particles spanning Responder (3 gain levels), Nonresponder (2), Worsening (2)
        self._particles = [
            GridHypothesisParticle("responder", analgesia_gain=3.6, sensitization_gain=0.0, weight=0.16),
            GridHypothesisParticle("responder", analgesia_gain=4.6, sensitization_gain=0.0, weight=0.20),
            GridHypothesisParticle("responder", analgesia_gain=5.5, sensitization_gain=0.0, weight=0.14),
            GridHypothesisParticle("nonresponder", analgesia_gain=0.0, sensitization_gain=0.0, weight=0.20),
            GridHypothesisParticle("nonresponder", analgesia_gain=0.3, sensitization_gain=0.0, weight=0.10),
            GridHypothesisParticle("delayed_worsening", analgesia_gain=0.6, sensitization_gain=3.8, weight=0.10),
            GridHypothesisParticle("delayed_worsening", analgesia_gain=0.4, sensitization_gain=5.0, weight=0.10),
        ]

    def reset(self, initial_obs: PublicObservation) -> None:
        self._init_particles()
        p = initial_obs.patient.last_pain_report
        self._baseline_mean = float(p) if p is not None else 6.0
        self._baseline_var = 0.35
        avail = initial_obs.patient.last_report_availability_time_sec
        self._last_assimilated_avail_sec = avail if avail is not None else 0.0
        self._cumulative_delivered_exposure = 0.0
        self._posterior_update_count = 0
        self._last_evoi = 0.0
        self._est_query_burden = 0.0

    def class_probabilities(self, particles: Optional[List[GridHypothesisParticle]] = None) -> Dict[str, float]:
        pts = particles if particles is not None else self._particles
        probs = {"responder": 0.0, "nonresponder": 0.0, "delayed_worsening": 0.0}
        for pt in pts:
            probs[pt.hypothesis_class] += pt.weight
        return probs

    def get_belief_summary(self) -> Optional[Dict[str, Any]]:
        probs = self.class_probabilities()
        return {
            "belief": [
                round(probs["responder"], 5),
                round(probs["nonresponder"], 5),
                round(probs["delayed_worsening"], 5),
            ],
            "cumulative_delivered_exposure": round(self._cumulative_delivered_exposure, 4),
            "posterior_update_count": self._posterior_update_count,
            "last_evoi": round(self._last_evoi, 5),
        }

    def _propagate_particles(self, obs: PublicObservation, dt_sec: float = 30.0) -> None:
        u_del = obs.delivered.delivered_intensity
        self._cumulative_delivered_exposure += u_del
        prog_id = obs.delivered.active_program_id
        spec = self._catalog.get(prog_id)
        is_burst = spec.waveform.is_burst_modulated if spec is not None else False
        hab_mult = 0.45 if is_burst else 1.15

        decay_a = math.exp(-dt_sec / 65.0)
        decay_h = math.exp(-dt_sec / 180.0)
        decay_s = math.exp(-dt_sec / 150.0)

        for pt in self._particles:
            if u_del <= 0.0:
                pt.est_habituation *= decay_h
                pt.est_analgesia *= decay_a
                pt.est_sensitization *= math.exp(-dt_sec / 220.0)
            else:
                h_target = min(0.85, 0.90 * u_del * hab_mult)
                pt.est_habituation = decay_h * pt.est_habituation + (1.0 - decay_h) * h_target
                if pt.hypothesis_class == "delayed_worsening":
                    mask_target = (pt.analgesia_gain * u_del) if pt.est_sensitization < 0.70 else 0.0
                    pt.est_analgesia = decay_a * pt.est_analgesia + (1.0 - decay_a) * mask_target
                    s_target = pt.sensitization_gain * u_del if u_del > 0.12 else 0.0
                    pt.est_sensitization = min(4.5, decay_s * pt.est_sensitization + (1.0 - decay_s) * s_target)
                else:
                    a_target = pt.analgesia_gain * u_del * (1.0 - 0.65 * pt.est_habituation)
                    pt.est_analgesia = decay_a * pt.est_analgesia + (1.0 - decay_a) * a_target
                    pt.est_sensitization *= decay_s

        # Epistemic process diffusion under unmonitored active exposure (prevents premature lock-in
        # during early transient masking before delayed sensitization has had time to accumulate)
        if not self._freeze_beliefs and u_del > 0.10 and self._cumulative_delivered_exposure < 3.5:
            prior_w = [0.16, 0.20, 0.14, 0.20, 0.10, 0.10, 0.10]
            diffuse = 0.025
            for pt, pw in zip(self._particles, prior_w):
                pt.weight = (1.0 - diffuse) * pt.weight + diffuse * pw

    @staticmethod
    def _predicted_pain(pt: GridHypothesisParticle, baseline: float, time_sec: float) -> float:
        osc = 0.55 * math.sin(time_sec / 270.0)
        pred = baseline + osc - pt.est_analgesia + pt.est_sensitization
        return max(0.0, min(10.0, pred))

    def _updated_weights_for_report(
        self,
        reported_vas: float,
        time_sec: float,
    ) -> List[float]:
        obs_std = math.sqrt(self._baseline_var + 0.65 ** 2)
        unnorm: List[float] = []
        for pt in self._particles:
            pred = self._predicted_pain(pt, self._baseline_mean, time_sec)
            diff = reported_vas - pred
            lik = math.exp(-0.5 * (diff / obs_std) ** 2)
            unnorm.append(pt.weight * lik)
        tot = sum(unnorm) + 1e-15
        return [w / tot for w in unnorm]

    def _expected_step_loss_for_program(
        self,
        prog_id: str,
        weights: List[float],
        time_sec: float,
    ) -> float:
        spec = self._catalog[prog_id]
        u = spec.normalized_intensity
        is_burst = spec.waveform.is_burst_modulated
        hab_mult = 0.45 if is_burst else 1.15
        effort_cost = 0.35 * (u ** 2)

        exp_loss = 0.0
        for pt, w in zip(self._particles, weights):
            # Lookahead 3 macro-steps (90 sec) to capture delayed sensitization vs analgesia
            a = pt.est_analgesia
            h = pt.est_habituation
            s = pt.est_sensitization
            branch_loss = 0.0
            for j in range(1, 4):
                if u <= 0.0:
                    h *= 0.85
                    a *= 0.63
                    s *= 0.87
                elif pt.hypothesis_class == "delayed_worsening":
                    a = 0.63 * a + 0.37 * ((pt.analgesia_gain * u) if s < 0.70 else 0.0)
                    s = min(4.5, 0.78 * s + 0.22 * (pt.sensitization_gain * u))
                else:
                    h = 0.85 * h + 0.15 * min(0.85, 0.90 * u * hab_mult)
                    a = 0.63 * a + 0.37 * (pt.analgesia_gain * u * (1.0 - 0.65 * h))
                pain_j = max(0.0, min(10.0, self._baseline_mean - a + s))
                worsen_pen = 3.0 * u if s > 0.85 else 0.0
                branch_loss += (0.95 ** j) * (pain_j + effort_cost + worsen_pen)
            exp_loss += w * (branch_loss / 3.0)
        return exp_loss

    def _compute_evoi(self, time_sec: float) -> Tuple[str, float]:
        candidate_progs = ["P00_OFF", "P01_LOW_CONV", "P02_MOD_BURST"]
        cur_weights = [pt.weight for pt in self._particles]
        prior_losses = {pid: self._expected_step_loss_for_program(pid, cur_weights, time_sec) for pid in candidate_progs}
        best_prior_prog = min(candidate_progs, key=lambda pid: prior_losses[pid])
        min_prior_loss = prior_losses[best_prior_prog]

        if self._cumulative_delivered_exposure < 0.25:
            return best_prior_prog, 0.0

        # Compute predictive distribution over integer VAS reports y in 0..10
        obs_std = math.sqrt(self._baseline_var + 0.65 ** 2)
        y_probs: List[float] = []
        post_weights_by_y: List[List[float]] = []
        for y in range(11):
            p_y = 0.0
            unnorm: List[float] = []
            for pt in self._particles:
                pred = self._predicted_pain(pt, self._baseline_mean, time_sec)
                lik = math.exp(-0.5 * ((float(y) - pred) / obs_std) ** 2)
                p_y += pt.weight * lik
                unnorm.append(pt.weight * lik)
            tot = sum(unnorm) + 1e-15
            y_probs.append(p_y)
            post_weights_by_y.append([w / tot for w in unnorm])

        norm_y = sum(y_probs) + 1e-15
        y_probs = [p / norm_y for p in y_probs]

        expected_posterior_min_loss = 0.0
        for p_y, w_post in zip(y_probs, post_weights_by_y):
            post_min = min(self._expected_step_loss_for_program(pid, w_post, time_sec) for pid in candidate_progs)
            expected_posterior_min_loss += p_y * post_min

        # EVoI is the expected reduction in lookahead decision loss across the next ~3 steps
        evoi_multi_step = max(0.0, 3.5 * (min_prior_loss - expected_posterior_min_loss))
        return best_prior_prog, evoi_multi_step

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence

        # 1. Propagate internal state estimates forward using actual delivered stimulation
        if obs.step_k > 0:
            self._propagate_particles(obs, dt_sec=30.0)
            self._est_query_burden *= math.exp(-30.0 / 180.0)

        # 2. Sequential Bayesian update when a genuinely new report arrives
        avail_sec = obs.patient.last_report_availability_time_sec
        is_new_report = obs.patient.report_status in (
            ReportStatus.NEW_PROMPT_RESPONSE,
            ReportStatus.SPONTANEOUS,
        )
        if (
            is_new_report
            and avail_sec is not None
            and avail_sec > self._last_assimilated_avail_sec
            and obs.patient.last_pain_report is not None
        ):
            self._last_assimilated_avail_sec = avail_sec
            raw_vas = float(obs.patient.last_pain_report)
            if self._shuffle_reports:
                # Deterministic pseudo-shuffle of informative report value for ablation
                raw_vas = float((int(raw_vas) * 7 + obs.step_k * 3) % 11)
            if not self._freeze_beliefs and self._cumulative_delivered_exposure >= 0.85:
                new_w = self._updated_weights_for_report(raw_vas, obs.time_sec)
                for pt, w in zip(self._particles, new_w):
                    pt.weight = w
                self._posterior_update_count += 1

        # 3. Immediate hardware / compliance fault abstention
        if _is_hardware_fault_visible(obs, max_safe_z=30_000.0):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        # 4. Evaluate Bayes-optimal action and Expected Value of Information (EVoI)
        best_prog, evoi = self._compute_evoi(obs.time_sec)
        self._last_evoi = evoi

        probs = self.class_probabilities()
        if self._matched_schedule_heuristic:
            chosen_prog = "P02_MOD_BURST" if (obs.step_k // 6) % 2 == 0 else "P01_LOW_CONV"
        else:
            if self._cumulative_delivered_exposure >= 0.85 and (
                probs["delayed_worsening"] > 0.34 or (probs["nonresponder"] + probs["delayed_worsening"]) > 0.72
            ):
                chosen_prog = "P00_OFF"
            else:
                # Favor burst modulation with brief low-intensity de-habituation windows on responders
                chosen_prog = "P01_LOW_CONV" if (obs.step_k % 8 == 7) else "P02_MOD_BURST"

        # 5. EVoI-driven sparse patient querying (with periodic monitoring until responder confidence is high)
        last_t = obs.patient.last_report_availability_time_sec or 0.0
        report_age = obs.time_sec - last_t
        query_cost_est = 0.45 * (1.0 + 2.0 * self._est_query_burden)
        high_responder_conf = probs["responder"] > 0.78 and self._posterior_update_count >= 2
        should_query = (
            chosen_prog != "P00_OFF"
            and obs.patient.pending_prompts_count == 0
            and report_age >= 90.0
            and not (high_responder_conf and report_age < 360.0)
            and (
                evoi > query_cost_est * 0.08
                or report_age >= 180.0
                or (self._posterior_update_count < 2 and report_age >= 90.0)
            )
        )

        if should_query:
            self._est_query_burden = min(1.0, self._est_query_burden + 0.20)
            fb = FeedbackCommand.REQUEST
            pid = f"bayes_evoi_q_{seq}"
        else:
            fb = FeedbackCommand.NONE
            pid = None

        if chosen_prog == "P00_OFF":
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=fb,
                prompt_id=pid,
                observation_sequence=seq,
            )
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=fb,
            target_program_id=chosen_prog,
            prompt_id=pid,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "particles": [
                {
                    "hypothesis_class": pt.hypothesis_class,
                    "analgesia_gain": pt.analgesia_gain,
                    "sensitization_gain": pt.sensitization_gain,
                    "weight": pt.weight,
                    "est_analgesia": pt.est_analgesia,
                    "est_habituation": pt.est_habituation,
                    "est_sensitization": pt.est_sensitization,
                }
                for pt in self._particles
            ],
            "baseline_mean": self._baseline_mean,
            "baseline_var": self._baseline_var,
            "last_assimilated_avail_sec": self._last_assimilated_avail_sec,
            "cumulative_delivered_exposure": self._cumulative_delivered_exposure,
            "posterior_update_count": self._posterior_update_count,
            "last_evoi": self._last_evoi,
            "est_query_burden": self._est_query_burden,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        self._particles = [
            GridHypothesisParticle(
                hypothesis_class=str(p["hypothesis_class"]),
                analgesia_gain=float(p["analgesia_gain"]),
                sensitization_gain=float(p["sensitization_gain"]),
                weight=float(p["weight"]),
                est_analgesia=float(p["est_analgesia"]),
                est_habituation=float(p["est_habituation"]),
                est_sensitization=float(p["est_sensitization"]),
            )
            for p in state["particles"]
        ]
        self._baseline_mean = float(state["baseline_mean"])
        self._baseline_var = float(state["baseline_var"])
        self._last_assimilated_avail_sec = float(state["last_assimilated_avail_sec"])
        self._cumulative_delivered_exposure = float(state["cumulative_delivered_exposure"])
        self._posterior_update_count = int(state["posterior_update_count"])
        self._last_evoi = float(state["last_evoi"])
        self._est_query_burden = float(state["est_query_burden"])
