"""
Biological and Phenomenological Plant Engines for NeuroLoop v0.4.0.
Plants advance state strictly as a function of `DeliveredExposure` and `SemanticRNG`.
"""

from __future__ import annotations

import copy
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

from neuroloop.contracts import ContractViolationError, DeliveredExposure, WaveformSpec, require_range
from neuroloop.randomness import SemanticRNG


@dataclass(frozen=True)
class PhysicalPlantOutput:
    """Privileged physical state summary emitted by a plant step."""
    step_k: int
    time_sec: float
    true_latent_pain: float
    true_functional_impairment: float
    analgesic_trace: float
    habituation: float
    delayed_sensitization: float
    query_burden: float
    contact_quality: float
    mechanistic_wdr_hz: Optional[float] = None
    intracellular_cl_mm: Optional[float] = None
    e_gaba_mv: Optional[float] = None


class AbstractPlantEngine(ABC):
    """
    Abstract base plant engine.
    Enforces that `step()` accepts ONLY `DeliveredExposure` (never `ControlAction` or `ProgramSpec`).
    """

    @property
    @abstractmethod
    def supports_checkpoint(self) -> bool:
        pass

    @abstractmethod
    def snapshot(self) -> Any:
        pass

    @abstractmethod
    def restore(self, state_snapshot: Any) -> None:
        pass

    @abstractmethod
    def current_output(self) -> PhysicalPlantOutput:
        pass

    @abstractmethod
    def sample_contact_quality(self, step_k: int, rng: SemanticRNG) -> float:
        pass

    @abstractmethod
    def step(
        self,
        exposure: DeliveredExposure,
        query_requested: bool,
        rng: SemanticRNG,
    ) -> PhysicalPlantOutput:
        pass


@dataclass
class PhenomenologicalState:
    phenotype: str
    frequency_response_mode: str
    step_k: int
    time_sec: float
    baseline_drive: float
    analgesic_trace: float
    habituation: float
    delayed_sensitization: float
    query_burden: float
    contact_quality: float
    patient_gain_scale: float
    patient_tau_analgesia_sec: float
    patient_tau_habituation_sec: float
    patient_tau_sensitization_sec: float
    fault_start_step: int
    fault_end_step: int


class PhenomenologicalPlant(AbstractPlantEngine):
    """
    Engine B: Fast state-space phenomenological challenge engine.
    Properties:
      1. Consumes ONLY `DeliveredExposure` (delivered_intensity and waveform timing),
         never program_id strings—guaranteeing 100% program-ID permutation invariance.
      2. Zero delivered exposure (`delivered_intensity == 0.0`) adds ZERO new treatment-induced
         analgesia or sensitization increment; existing carryover decays exponentially.
      3. All slow state variables evolve via explicit continuous-time exponential integration:
           x(t + dt) = exp(-dt / tau) * x(t) + (1 - exp(-dt / tau)) * x_target
    """

    def __init__(
        self,
        phenotype: str,
        frequency_response_mode: str,
        rng: SemanticRNG,
        fixed_fault_window: Optional[tuple[int, int]] = (18, 24),
    ) -> None:
        # Sample patient-level physiological heterogeneity from 'patient_params' stream at t=0
        gain_scale = max(0.75, min(1.25, 1.0 + rng.normal("patient_params", 0, 0.0, 0.08, draw_index=0)))
        tau_a = max(35.0, min(120.0, 65.0 + rng.normal("patient_params", 0, 0.0, 6.0, draw_index=1)))
        tau_h = max(90.0, min(360.0, 180.0 + rng.normal("patient_params", 0, 0.0, 15.0, draw_index=2)))
        tau_s = max(90.0, min(360.0, 150.0 + rng.normal("patient_params", 0, 0.0, 12.0, draw_index=3)))
        init_base = max(4.5, min(7.8, 6.2 + rng.normal("patient_params", 0, 0.0, 0.25, draw_index=4)))

        if phenotype == "random_fault_window":
            f_start = 8 + int(rng.uniform("patient_params", 0, draw_index=5) * 20)
            f_dur = 3 + int(rng.uniform("patient_params", 0, draw_index=6) * 5)
            f_end = f_start + f_dur
        elif fixed_fault_window is not None:
            f_start, f_end = fixed_fault_window
        else:
            f_start, f_end = -1, -1

        self._state = PhenomenologicalState(
            phenotype=phenotype,
            frequency_response_mode=frequency_response_mode,
            step_k=0,
            time_sec=0.0,
            baseline_drive=init_base,
            analgesic_trace=0.0,
            habituation=0.0,
            delayed_sensitization=0.0,
            query_burden=0.0,
            contact_quality=1.0,
            patient_gain_scale=gain_scale,
            patient_tau_analgesia_sec=tau_a,
            patient_tau_habituation_sec=tau_h,
            patient_tau_sensitization_sec=tau_s,
            fault_start_step=f_start,
            fault_end_step=f_end,
        )

    @property
    def supports_checkpoint(self) -> bool:
        return True

    def snapshot(self) -> PhenomenologicalState:
        return copy.deepcopy(self._state)

    def restore(self, state_snapshot: PhenomenologicalState) -> None:
        self._state = copy.deepcopy(state_snapshot)

    def _compute_latent_pain(self, st: PhenomenologicalState) -> float:
        raw = st.baseline_drive - st.analgesic_trace + st.delayed_sensitization
        return max(0.0, min(10.0, raw))

    def _compute_functional_impairment(self, st: PhenomenologicalState, pain: float) -> float:
        return max(0.0, min(10.0, 0.65 * pain + 0.35 * st.delayed_sensitization))

    def current_output(self) -> PhysicalPlantOutput:
        st = self._state
        pain = self._compute_latent_pain(st)
        func = self._compute_functional_impairment(st, pain)
        return PhysicalPlantOutput(
            step_k=st.step_k,
            time_sec=st.time_sec,
            true_latent_pain=pain,
            true_functional_impairment=func,
            analgesic_trace=st.analgesic_trace,
            habituation=st.habituation,
            delayed_sensitization=st.delayed_sensitization,
            query_burden=st.query_burden,
            contact_quality=st.contact_quality,
            mechanistic_wdr_hz=None,
            intracellular_cl_mm=None,
            e_gaba_mv=None,
        )

    def sample_contact_quality(self, step_k: int, rng: SemanticRNG) -> float:
        st = self._state
        if st.fault_start_step <= step_k <= st.fault_end_step:
            cq = max(0.18, min(0.30, 0.24 + rng.normal("contact_dynamics", step_k, 0.0, 0.02, draw_index=0)))
        else:
            cq = max(0.78, min(1.0, 0.95 + rng.normal("contact_dynamics", step_k, 0.0, 0.015, draw_index=1)))
        st.contact_quality = cq
        return cq

    def _habituation_multiplier(self, wf: WaveformSpec) -> float:
        mode = self._state.frequency_response_mode
        if mode == "frequency_neutral":
            return 1.0
        if mode == "burst_slows_habituation":
            return 0.45 if wf.is_burst_modulated else 1.15
        if mode == "burst_accelerates_habituation":
            return 1.25 if wf.is_burst_modulated else 0.55
        return 1.0

    @staticmethod
    def _exp_step(current: float, target: float, dt_sec: float, tau_sec: float) -> float:
        if dt_sec <= 0.0:
            return current
        decay = math.exp(-dt_sec / max(1e-6, tau_sec))
        return decay * current + (1.0 - decay) * target

    def step(
        self,
        exposure: DeliveredExposure,
        query_requested: bool,
        rng: SemanticRNG,
    ) -> PhysicalPlantOutput:
        if not isinstance(exposure, DeliveredExposure):
            raise ContractViolationError(
                f"Plant.step requires DeliveredExposure from an Actuator, got {type(exposure).__name__}"
            )
        st = self._state
        dt = require_range(exposure.dt_sec, "dt_sec", 0.0, 3600.0)
        k = st.step_k
        u_del = exposure.delivered_intensity

        # 1. Action-independent background nociceptive drive with sqrt(dt / 30) diffusion scaling
        dt_scale = math.sqrt(dt / 30.0) if dt > 0.0 else 0.0
        drift = rng.normal("env_disturbance", k, 0.0, 0.16 * dt_scale, draw_index=0)
        flare_offset = 1.4 if (st.phenotype == "baseline_flare" and 12 <= k <= 22) else 0.0
        target_drive = 6.2 + flare_offset + 0.65 * math.sin((st.time_sec + dt) / 270.0) + drift
        st.baseline_drive = max(3.0, min(9.2, target_drive))

        # 2. Treatment-induced state updates driven strictly by actual delivered_intensity (u_del)
        eff_pheno = "responder" if st.phenotype == "random_fault_window" else st.phenotype

        if u_del <= 0.0 or eff_pheno == "null_effect":
            # Strictly ZERO new treatment increment when delivered exposure is zero or in null_effect fixture!
            # Existing carryover and sensitization relax exponentially toward 0.0.
            st.habituation = self._exp_step(st.habituation, 0.0, dt, st.patient_tau_habituation_sec)
            st.analgesic_trace = self._exp_step(st.analgesic_trace, 0.0, dt, st.patient_tau_analgesia_sec)
            st.delayed_sensitization = self._exp_step(
                st.delayed_sensitization, 0.0, dt, st.patient_tau_sensitization_sec * 1.5
            )
        elif eff_pheno == "responder":
            hab_mult = self._habituation_multiplier(exposure.waveform)
            hab_target = min(0.85, 0.90 * u_del * hab_mult)
            st.habituation = self._exp_step(st.habituation, hab_target, dt, st.patient_tau_habituation_sec)

            relief_target = 4.6 * st.patient_gain_scale * u_del * (1.0 - 0.65 * st.habituation)
            st.analgesic_trace = self._exp_step(
                st.analgesic_trace, relief_target, dt, st.patient_tau_analgesia_sec
            )
            st.delayed_sensitization = self._exp_step(
                st.delayed_sensitization, 0.0, dt, st.patient_tau_sensitization_sec
            )
        elif eff_pheno == "nonresponder" or eff_pheno == "baseline_flare":
            st.habituation = self._exp_step(st.habituation, min(0.85, u_del), dt, st.patient_tau_habituation_sec)
            st.analgesic_trace = self._exp_step(st.analgesic_trace, 0.0, dt, st.patient_tau_analgesia_sec)
            st.delayed_sensitization = self._exp_step(
                st.delayed_sensitization, 0.0, dt, st.patient_tau_sensitization_sec
            )
        elif eff_pheno == "delayed_worsening":
            # Brief transient masking when sensitization is low, followed by cumulative sensitization
            transient_target = (0.75 * u_del) if st.delayed_sensitization < 0.70 else 0.0
            st.analgesic_trace = self._exp_step(
                st.analgesic_trace, transient_target, dt, st.patient_tau_analgesia_sec * 0.75
            )
            sens_target = 4.8 * st.patient_gain_scale * u_del if u_del > 0.12 else 0.0
            st.delayed_sensitization = min(
                4.5,
                self._exp_step(st.delayed_sensitization, sens_target, dt, st.patient_tau_sensitization_sec * 0.75),
            )
        else:
            raise ContractViolationError(f"Unsupported phenotype in PhenomenologicalPlant: {st.phenotype!r}")

        # 3. Query burden dynamics
        if query_requested:
            st.query_burden = min(1.0, st.query_burden + 0.20 * (dt / 30.0))
        else:
            st.query_burden = self._exp_step(st.query_burden, 0.0, dt, 180.0)

        st.step_k += 1
        st.time_sec += dt
        return self.current_output()
