"""
Stage 4 (PR 6): Sparse Excitatory/Inhibitory (E/I) Connectome-Inspired Recurrent Controller (C6)
with Dale's law sign constraints and an equal-capacity dense unstructured ablation.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from neuroloop.contracts import (
    ControlAction,
    FeedbackCommand,
    PublicObservation,
    ReportStatus,
    StimulationCommand,
)
from neuroloop.controllers import AbstractController, _is_hardware_fault_visible


class RecurrentEIController(AbstractController):
    """
    C6: Compact Recurrent E/I Controller with explicit Dale's law excitatory/inhibitory
    subpopulations (6 excitatory + 4 inhibitory leaky integrator units) vs. an equal-capacity
    unconstrained dense ablation (`ablate_ei_structure=True`).
    """

    def __init__(self, ablate_ei_structure: bool = False) -> None:
        self._ablate_ei = ablate_ei_structure
        self.name = "C6_Ablation_DenseRecurrent" if ablate_ei_structure else "C6_SparseRecurrentEI"
        self._baseline_pain: float = 6.0
        self._last_avail_sec: float = -1.0
        # 6 Excitatory units (relief / drive encoders) + 4 Inhibitory units (sensitization / fatigue gates)
        self._hidden: List[float] = [0.0] * 10

    def reset(self, initial_obs: PublicObservation) -> None:
        p = initial_obs.patient.last_pain_report
        self._baseline_pain = float(p) if p is not None else 6.0
        avail = initial_obs.patient.last_report_availability_time_sec
        self._last_avail_sec = avail if avail is not None else 0.0
        self._hidden = [0.0] * 10

    def get_belief_summary(self) -> Optional[Dict[str, Any]]:
        exc_mean = sum(self._hidden[:6]) / 6.0
        inh_mean = sum(self._hidden[6:]) / 4.0
        return {
            "exc_pool_activity": round(exc_mean, 4),
            "inh_pool_activity": round(inh_mean, 4),
        }

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        u_del = obs.delivered.delivered_intensity

        avail_sec = obs.patient.last_report_availability_time_sec
        is_new = obs.patient.report_status in (
            ReportStatus.NEW_PROMPT_RESPONSE,
            ReportStatus.SPONTANEOUS,
        )
        delta_pain = 0.0
        has_new = False
        if (
            is_new
            and avail_sec is not None
            and avail_sec > self._last_avail_sec
            and obs.patient.last_pain_report is not None
        ):
            self._last_avail_sec = avail_sec
            delta_pain = float(obs.patient.last_pain_report) - self._baseline_pain
            has_new = True

        # Advance recurrent E/I pools
        relief_signal = max(0.0, -delta_pain) if has_new else 0.0
        worsen_signal = max(0.0, delta_pain) if has_new else 0.0
        null_signal = (1.0 if abs(delta_pain) < 0.6 else 0.0) if (has_new and u_del > 0.1) else 0.0

        new_h = list(self._hidden)
        if not self._ablate_ei:
            # Structured Dale's Law E/I competitive dynamics
            for i in range(6):
                inh_feedback = 0.45 * sum(self._hidden[6:]) / 4.0
                drive = 0.35 * u_del + 0.55 * relief_signal - inh_feedback
                new_h[i] = max(0.0, min(3.0, 0.78 * self._hidden[i] + math.tanh(max(0.0, drive))))
            for j in range(6, 10):
                inh_drive = 0.65 * worsen_signal + 0.32 * null_signal
                if has_new and relief_signal > 0.8:
                    inh_drive -= 0.40 * relief_signal
                new_h[j] = max(0.0, min(3.0, 0.88 * self._hidden[j] + inh_drive))
        else:
            # Unstructured dense ablation without separated inhibitory sensitization latching
            for i in range(10):
                drive = 0.25 * u_del + 0.20 * (relief_signal - worsen_signal)
                new_h[i] = 0.75 * self._hidden[i] + math.tanh(drive)
        self._hidden = new_h

        if _is_hardware_fault_visible(obs, max_safe_z=30_000.0):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        exc_act = sum(self._hidden[:6]) / 6.0
        inh_act = sum(self._hidden[6:]) / 4.0

        if not self._ablate_ei and inh_act > 0.52:
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        if self._ablate_ei and (exc_act + inh_act) < -0.45:
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        last_t = obs.patient.last_report_availability_time_sec or 0.0
        age = obs.time_sec - last_t
        want_q = (age >= 150.0 and obs.step_k <= 18) and (obs.patient.pending_prompts_count == 0)
        fb = FeedbackCommand.REQUEST if want_q else FeedbackCommand.NONE
        pid = f"rec_q_{seq}" if want_q else None

        prog = "P02_MOD_BURST" if (obs.step_k // 6) % 2 == 0 else "P01_LOW_CONV"
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=fb,
            target_program_id=prog,
            prompt_id=pid,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "baseline_pain": self._baseline_pain,
            "last_avail_sec": self._last_avail_sec,
            "hidden": list(self._hidden),
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        self._baseline_pain = float(state["baseline_pain"])
        self._last_avail_sec = float(state["last_avail_sec"])
        self._hidden = [float(x) for x in state["hidden"]]
