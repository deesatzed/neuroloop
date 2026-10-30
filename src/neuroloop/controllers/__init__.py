"""
Controller interfaces, calibration record protocol, and baseline controllers (C0-C4)
for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from neuroloop.contracts import (
    ControlAction,
    DEFAULT_PROGRAM_CATALOG,
    FeedbackCommand,
    ProgramSpec,
    PublicObservation,
    ReportStatus,
    StimulationCommand,
)


@dataclass
class CalibrationRecord:
    """
    Explicit, checkpointable record of a patient's calibration phase.
    Shared with counterfactual comparators so forked rollouts inherit the patient's
    actual calibrated program rather than reverting to an uncalibrated default.
    """
    baseline_pain: float = 6.0
    p01_confirmed_steps: int = 0
    p01_fresh_pain: Optional[int] = None
    p02_confirmed_steps: int = 0
    p02_fresh_pain: Optional[int] = None
    selected_program_id: str = "P01_LOW_CONV"
    calibration_completed: bool = False
    fallback_used: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CalibrationRecord:
        return cls(
            baseline_pain=float(data["baseline_pain"]),
            p01_confirmed_steps=int(data["p01_confirmed_steps"]),
            p01_fresh_pain=int(data["p01_fresh_pain"]) if data["p01_fresh_pain"] is not None else None,
            p02_confirmed_steps=int(data["p02_confirmed_steps"]),
            p02_fresh_pain=int(data["p02_fresh_pain"]) if data["p02_fresh_pain"] is not None else None,
            selected_program_id=str(data["selected_program_id"]),
            calibration_completed=bool(data["calibration_completed"]),
            fallback_used=bool(data["fallback_used"]),
        )


class AbstractController(ABC):
    """
    Public controller interface.
    Receives ONLY immutable `PublicObservation` value objects and returns `ControlAction`.
    """
    name: str

    @abstractmethod
    def reset(self, initial_obs: PublicObservation) -> None:
        pass

    @abstractmethod
    def act(self, obs: PublicObservation) -> ControlAction:
        pass

    @abstractmethod
    def snapshot(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def restore(self, state: Mapping[str, Any]) -> None:
        pass

    def clone(self) -> AbstractController:
        cloned = copy.deepcopy(self)
        return cloned

    def get_belief_summary(self) -> Optional[Dict[str, Any]]:
        return None

    def get_calibration_record(self) -> Optional[CalibrationRecord]:
        return None

    def set_calibration_record(self, record: CalibrationRecord) -> None:
        pass


def _is_hardware_fault_visible(obs: PublicObservation, max_safe_z: float = 35_000.0) -> bool:
    return (
        obs.electrode.fault_latched
        or obs.electrode.compliance_limit_reached
        or obs.electrode.impedance_real_ohm > max_safe_z
    )


class HoldComparatorController(AbstractController):
    """Counterfactual comparator: holds current stimulation without querying, except during visible faults."""
    name = "Comparator_Hold"

    def reset(self, initial_obs: PublicObservation) -> None:
        pass

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        if _is_hardware_fault_visible(obs):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        return ControlAction(
            stimulation=StimulationCommand.HOLD,
            feedback=FeedbackCommand.NONE,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {"name": self.name}

    def restore(self, state: Mapping[str, Any]) -> None:
        pass


class OffController(AbstractController):
    """C0: Always OFF and never queries."""
    name = "C0_Off"

    def reset(self, initial_obs: PublicObservation) -> None:
        pass

    def act(self, obs: PublicObservation) -> ControlAction:
        return ControlAction(
            stimulation=StimulationCommand.OFF,
            feedback=FeedbackCommand.NONE,
            observation_sequence=obs.timing_meta.observation_sequence,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {"name": self.name}

    def restore(self, state: Mapping[str, Any]) -> None:
        pass


class FixedProgramController(AbstractController):
    """C1: Fixed preset stimulation with independent fault abstention."""

    def __init__(self, target_program_id: str = "P02_MOD_BURST") -> None:
        if target_program_id not in DEFAULT_PROGRAM_CATALOG:
            raise ValueError(f"Unknown target_program_id: {target_program_id}")
        self._target_program_id = target_program_id
        self.name = f"C1_Fixed_{target_program_id}"

    def reset(self, initial_obs: PublicObservation) -> None:
        pass

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        if _is_hardware_fault_visible(obs):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=FeedbackCommand.NONE,
            target_program_id=self._target_program_id,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {"target_program_id": self._target_program_id}

    def restore(self, state: Mapping[str, Any]) -> None:
        self._target_program_id = str(state["target_program_id"])


class CalibratedFixedController(AbstractController):
    """
    C2: Personalized Fixed Controller with explicit CalibrationRecord provenance.
    - Evaluates P01_LOW_CONV (steps 0..2) and P02_MOD_BURST (steps 3..5).
    - Requires confirmed exposure (`delivered_intensity > 0.1`) and fresh report timestamps
      before locking a personalized setting.
    - Preserves zero pain (`last_pain_report is not None`).
    - Locks treatment selection after calibration, while still respecting independent
      fault abstention (`OFF` during visible electrode/compliance faults).
    """
    name = "C2_CalibratedFixed"

    def __init__(self) -> None:
        self._cal = CalibrationRecord()
        self._p01_window_start_sec: float = 0.0
        self._p02_window_start_sec: float = 90.0

    def reset(self, initial_obs: PublicObservation) -> None:
        init_pain = initial_obs.patient.last_pain_report
        base_val = float(init_pain) if init_pain is not None else 6.0
        self._cal = CalibrationRecord(baseline_pain=base_val)
        self._p01_window_start_sec = initial_obs.time_sec
        self._p02_window_start_sec = initial_obs.time_sec + 90.0

    def get_calibration_record(self) -> Optional[CalibrationRecord]:
        return copy.deepcopy(self._cal)

    def set_calibration_record(self, record: CalibrationRecord) -> None:
        self._cal = copy.deepcopy(record)

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        k = obs.step_k

        # Track confirmed exposure during calibration windows
        if not self._cal.calibration_completed:
            if 1 <= k <= 3 and obs.delivered.delivered_intensity > 0.10:
                self._cal.p01_confirmed_steps += 1
            elif 4 <= k <= 6 and obs.delivered.delivered_intensity > 0.10:
                self._cal.p02_confirmed_steps += 1

        # Independent safety fault protection applies at all steps
        if _is_hardware_fault_visible(obs):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        if self._cal.calibration_completed:
            if self._cal.selected_program_id == "P00_OFF":
                return ControlAction(
                    stimulation=StimulationCommand.OFF,
                    feedback=FeedbackCommand.NONE,
                    observation_sequence=seq,
                )
            return ControlAction(
                stimulation=StimulationCommand.SET,
                feedback=FeedbackCommand.NONE,
                target_program_id=self._cal.selected_program_id,
                observation_sequence=seq,
            )

        # Calibration window 1: steps 0, 1, 2 -> P01_LOW_CONV, query on step 2
        if k < 3:
            req_fb = FeedbackCommand.REQUEST if k == 2 else FeedbackCommand.NONE
            return ControlAction(
                stimulation=StimulationCommand.SET,
                feedback=req_fb,
                target_program_id="P01_LOW_CONV",
                prompt_id=f"cal_p01_step_{k}" if req_fb == FeedbackCommand.REQUEST else None,
                observation_sequence=seq,
            )

        # Record P01 fresh report at step 3 (or step 4 if 1-step report delay)
        if k in (3, 4) and self._cal.p01_fresh_pain is None:
            acq_t = obs.patient.last_report_acquisition_time_sec
            if (
                obs.patient.last_pain_report is not None
                and acq_t is not None
                and acq_t > self._p01_window_start_sec
                and self._cal.p01_confirmed_steps >= 1
            ):
                self._cal.p01_fresh_pain = obs.patient.last_pain_report
            if k == 3:
                self._p02_window_start_sec = obs.time_sec

        # Calibration window 2: steps 3, 4, 5 -> P02_MOD_BURST, query on step 5
        if k < 6:
            req_fb = FeedbackCommand.REQUEST if k == 5 else FeedbackCommand.NONE
            return ControlAction(
                stimulation=StimulationCommand.SET,
                feedback=req_fb,
                target_program_id="P02_MOD_BURST",
                prompt_id=f"cal_p02_step_{k}" if req_fb == FeedbackCommand.REQUEST else None,
                observation_sequence=seq,
            )

        # Finalize calibration at step 6 (or step 7 if delayed report is still in flight)
        if k == 6 and obs.patient.pending_prompts_count > 0 and self._cal.p02_fresh_pain is None:
            return ControlAction(
                stimulation=StimulationCommand.HOLD,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        acq_t = obs.patient.last_report_acquisition_time_sec
        if (
            obs.patient.last_pain_report is not None
            and acq_t is not None
            and acq_t > self._p02_window_start_sec
            and self._cal.p02_confirmed_steps >= 1
        ):
            self._cal.p02_fresh_pain = obs.patient.last_pain_report

        v1 = self._cal.p01_fresh_pain
        v2 = self._cal.p02_fresh_pain
        if v1 is None and v2 is None:
            self._cal.selected_program_id = "P01_LOW_CONV"
            self._cal.fallback_used = True
        else:
            eff_v1 = float(v1) if v1 is not None else 10.0
            eff_v2 = float(v2) if v2 is not None else 10.0
            best_v = min(eff_v1, eff_v2)
            if best_v > self._cal.baseline_pain:
                self._cal.selected_program_id = "P00_OFF"
            elif eff_v2 <= eff_v1:
                self._cal.selected_program_id = "P02_MOD_BURST"
            else:
                self._cal.selected_program_id = "P01_LOW_CONV"

        self._cal.calibration_completed = True
        if self._cal.selected_program_id == "P00_OFF":
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=FeedbackCommand.NONE,
            target_program_id=self._cal.selected_program_id,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "cal": self._cal.to_dict(),
            "p01_window_start_sec": self._p01_window_start_sec,
            "p02_window_start_sec": self._p02_window_start_sec,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        self._cal = CalibrationRecord.from_dict(state["cal"])
        self._p01_window_start_sec = float(state["p01_window_start_sec"])
        self._p02_window_start_sec = float(state["p02_window_start_sec"])


class ConservativeRulesController(AbstractController):
    """
    C3: Conservative patient-adjusted rules controller.
    - Explicitly checks `last_pain_report is not None` so `0` pain turns stimulation OFF
      rather than defaulting to `5` (`P02_MOD_BURST`).
    - Backs off to `OFF` if pain worsens by >= 2 points above baseline after active exposure.
    """
    name = "C3_ConservativeRules"

    def __init__(self) -> None:
        self._baseline_pain: float = 6.0
        self._active_exposure_steps: int = 0
        self._worsening_abstained: bool = False

    def reset(self, initial_obs: PublicObservation) -> None:
        p = initial_obs.patient.last_pain_report
        self._baseline_pain = float(p) if p is not None else 6.0
        self._active_exposure_steps = 0
        self._worsening_abstained = False

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        if obs.delivered.delivered_intensity > 0.10:
            self._active_exposure_steps += 1

        if _is_hardware_fault_visible(obs, max_safe_z=30_000.0):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        vas = obs.patient.last_pain_report if obs.patient.last_pain_report is not None else 5

        if self._active_exposure_steps >= 4 and vas >= self._baseline_pain + 2.0:
            self._worsening_abstained = True

        if self._worsening_abstained or vas <= 1:
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        last_t = obs.patient.last_report_availability_time_sec
        age_sec = obs.time_sec - (last_t if last_t is not None else 0.0)
        need_query = (age_sec >= 240.0) and (obs.patient.pending_prompts_count == 0)
        fb = FeedbackCommand.REQUEST if need_query else FeedbackCommand.NONE
        pid = f"rules_q_{seq}" if need_query else None

        if vas >= 7:
            target = "P03_HIGH_CONV"
        elif vas >= 5:
            target = "P02_MOD_BURST"
        else:
            target = "P01_LOW_CONV"

        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=fb,
            target_program_id=target,
            prompt_id=pid,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "baseline_pain": self._baseline_pain,
            "active_exposure_steps": self._active_exposure_steps,
            "worsening_abstained": self._worsening_abstained,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        self._baseline_pain = float(state["baseline_pain"])
        self._active_exposure_steps = int(state["active_exposure_steps"])
        self._worsening_abstained = bool(state["worsening_abstained"])


class HeuristicThreeHypothesisController(AbstractController):
    """
    C4: Repaired Three-Hypothesis Heuristic Filter (honest renaming of the legacy v0.3.2 policy).
    Repaired to track actual delivered_intensity and assimilate each new report once.
    """
    name = "C4_HeuristicFilter"

    def __init__(self) -> None:
        self._belief: List[float] = [0.50, 0.30, 0.20]
        self._baseline_vas: float = 6.0
        self._last_assimilated_avail_sec: float = -1.0
        self._cumulative_exposure: float = 0.0
        self._update_count: int = 0

    def reset(self, initial_obs: PublicObservation) -> None:
        self._belief = [0.50, 0.30, 0.20]
        p = initial_obs.patient.last_pain_report
        self._baseline_vas = float(p) if p is not None else 6.0
        avail = initial_obs.patient.last_report_availability_time_sec
        self._last_assimilated_avail_sec = avail if avail is not None else 0.0
        self._cumulative_exposure = 0.0
        self._update_count = 0

    def get_belief_summary(self) -> Optional[Dict[str, Any]]:
        return {
            "belief": list(self._belief),
            "cumulative_exposure": round(self._cumulative_exposure, 4),
            "update_count": self._update_count,
        }

    def act(self, obs: PublicObservation) -> ControlAction:
        seq = obs.timing_meta.observation_sequence
        self._cumulative_exposure += obs.delivered.delivered_intensity

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
            if self._cumulative_exposure >= 0.50:
                import math

                vas = float(obs.patient.last_pain_report)
                delta = vas - self._baseline_vas
                l_resp = math.exp(-0.5 * ((delta - (-1.6)) / 1.1) ** 2)
                l_null = math.exp(-0.5 * ((delta - 0.0) / 1.1) ** 2)
                l_worsen = math.exp(-0.5 * ((delta - (+1.4)) / 1.1) ** 2)
                unnorm = [
                    self._belief[0] * l_resp,
                    self._belief[1] * l_null,
                    self._belief[2] * l_worsen,
                ]
                tot = sum(unnorm) + 1e-12
                self._belief = [x / tot for x in unnorm]
                self._update_count += 1

        if _is_hardware_fault_visible(obs, max_safe_z=30_000.0):
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        p_resp, p_null, p_worsen = self._belief
        if p_worsen > 0.36 or (p_null + p_worsen) > 0.74:
            return ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.NONE,
                observation_sequence=seq,
            )

        import math

        entropy = -sum(p * math.log(max(1e-9, p)) for p in self._belief)
        last_t = obs.patient.last_report_availability_time_sec or 0.0
        report_age = obs.time_sec - last_t
        want_q = (
            ((entropy > 0.80 and report_age >= 120.0) or report_age >= 300.0)
            and obs.patient.pending_prompts_count == 0
        )
        fb = FeedbackCommand.REQUEST if want_q else FeedbackCommand.NONE
        pid = f"heur_q_{seq}" if want_q else None

        chosen_prog = "P02_MOD_BURST" if (obs.step_k // 6) % 2 == 0 else "P01_LOW_CONV"
        return ControlAction(
            stimulation=StimulationCommand.SET,
            feedback=fb,
            target_program_id=chosen_prog,
            prompt_id=pid,
            observation_sequence=seq,
        )

    def snapshot(self) -> Dict[str, Any]:
        return {
            "belief": list(self._belief),
            "baseline_vas": self._baseline_vas,
            "last_assimilated_avail_sec": self._last_assimilated_avail_sec,
            "cumulative_exposure": self._cumulative_exposure,
            "update_count": self._update_count,
        }

    def restore(self, state: Mapping[str, Any]) -> None:
        self._belief = [float(x) for x in state["belief"]]
        self._baseline_vas = float(state["baseline_vas"])
        self._last_assimilated_avail_sec = float(state["last_assimilated_avail_sec"])
        self._cumulative_exposure = float(state["cumulative_exposure"])
        self._update_count = int(state["update_count"])
