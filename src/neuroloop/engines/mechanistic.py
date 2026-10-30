"""
Engine A: Biophysical Dorsal Horn Conductance & Chloride Homeostasis Reference Engine.
Implements Goldman-Hodgkin-Katz (GHK) Cl-/HCO3- GABA reversal potential and
thermodynamically consistent electroneutral KCC2 cotransport grounded in the
chemical potential product ([K+]_i * [Cl-]_i - [K+]_o * [Cl-]_o).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Optional

from neuroloop.contracts import (
    BiophysicalNumericalError,
    ContractViolationError,
    DeliveredExposure,
    require_range,
)
from neuroloop.engines import AbstractPlantEngine, PhysicalPlantOutput
from neuroloop.randomness import SemanticRNG


@dataclass
class MechanisticState:
    phenotype: str
    frequency_response_mode: str
    step_k: int
    time_sec: float
    cl_in_mm: float              # Intracellular [Cl-]_i (mM), valid [1.0, 80.0]
    cl_out_mm: float             # Extracellular [Cl-]_o (mM), fixed 120.0
    hco3_in_mm: float            # Intracellular [HCO3-]_i (mM), fixed 15.0
    hco3_out_mm: float           # Extracellular [HCO3-]_o (mM), fixed 25.0
    k_in_mm: float               # Intracellular [K+]_i (mM), valid [80.0, 180.0]
    k_out_mm: float              # Extracellular [K+]_o (mM), valid [2.5, 12.0]
    kcc2_rate_per_sec: float     # Extrusion rate constant k_KCC2 (s^-1)
    abeta_coupling_gain: float   # Recruitment efficiency of A-beta inhibitory pathway
    synaptic_depression: float   # Vesicle depletion / habituation variable [0.0, 0.9]
    wdr_voltage_mv: float        # Effective WDR somatic membrane potential (mV)
    wdr_firing_hz: float         # WDR projection firing rate (Hz)
    c_fiber_drive_hz: float      # Nociceptive C-fiber input rate (Hz)
    query_burden: float
    contact_quality: float
    fault_start_step: int
    fault_end_step: int


class MechanisticDorsalHornPlant(AbstractPlantEngine):
    """
    Engine A: Conductance-based dorsal horn gate reference engine with explicit
    Cl-/HCO3- GHK reversal potential and electroneutral KCC2 cotransport.
    """

    # Physical constants at T = 310.15 K (37 C)
    RT_OVER_F_MV = 26.7128  # (R * T / F) in mV at 37 C
    P_HCO3_TO_CL_RATIO = 0.25
    E_LEAK_MV = -65.0
    E_EXC_MV = 0.0
    G_LEAK_MS_CM2 = 0.10
    SUBSTEP_DT_SEC = 0.50

    def __init__(
        self,
        phenotype: str,
        frequency_response_mode: str,
        rng: SemanticRNG,
        fixed_fault_window: Optional[tuple[int, int]] = (18, 24),
    ) -> None:
        cl_out = 120.0
        k_out = 4.0
        k_in = 135.0
        # At thermodynamic KCC2 equilibrium with basal Cl influx offset:
        # [K]_o * [Cl]_o / [K]_i = 4.0 * 120.0 / 135.0 = 3.5556 mM (pure KCC2 equilibrium)
        # With small basal tonic Cl leak in intact neurons, resting [Cl-]_i ~ 6.2 mM.
        eff_pheno = "responder" if phenotype == "random_fault_window" else phenotype

        gain_jitter = 1.0 + rng.normal("patient_params", 0, 0.0, 0.06, draw_index=0)
        if eff_pheno == "responder":
            kcc2_rate = 0.085 * gain_jitter
            abeta_gain = 1.05 * gain_jitter
            cl_init = 6.2
        elif eff_pheno in ("nonresponder", "null_effect", "baseline_flare"):
            # Loss of A-beta synaptic coupling onto dorsal horn inhibitory interneurons
            kcc2_rate = 0.075
            abeta_gain = 0.0 if eff_pheno == "null_effect" else 0.04
            cl_init = 6.5
        elif eff_pheno == "delayed_worsening":
            # KCC2 downregulation phenotype: impaired chloride extrusion leads to activity-dependent
            # intracellular Cl- accumulation and depolarizing shift in E_GABA
            kcc2_rate = 0.012 * gain_jitter
            abeta_gain = 0.95 * gain_jitter
            cl_init = 11.5
        else:
            raise ContractViolationError(f"Unsupported phenotype in MechanisticDorsalHornPlant: {phenotype!r}")

        if phenotype == "random_fault_window":
            f_start = 8 + int(rng.uniform("patient_params", 0, draw_index=5) * 20)
            f_dur = 3 + int(rng.uniform("patient_params", 0, draw_index=6) * 5)
            f_end = f_start + f_dur
        elif fixed_fault_window is not None:
            f_start, f_end = fixed_fault_window
        else:
            f_start, f_end = -1, -1

        self._state = MechanisticState(
            phenotype=phenotype,
            frequency_response_mode=frequency_response_mode,
            step_k=0,
            time_sec=0.0,
            cl_in_mm=cl_init,
            cl_out_mm=cl_out,
            hco3_in_mm=15.0,
            hco3_out_mm=25.0,
            k_in_mm=k_in,
            k_out_mm=k_out,
            kcc2_rate_per_sec=kcc2_rate,
            abeta_coupling_gain=abeta_gain,
            synaptic_depression=0.0,
            wdr_voltage_mv=-54.0,
            wdr_firing_hz=32.0,
            c_fiber_drive_hz=28.0,
            query_burden=0.0,
            contact_quality=1.0,
            fault_start_step=f_start,
            fault_end_step=f_end,
        )
        self._update_steady_voltage_and_firing()
        self._validate_bounds(self._state)

    @property
    def supports_checkpoint(self) -> bool:
        return True

    def snapshot(self) -> MechanisticState:
        return copy.deepcopy(self._state)

    def restore(self, state_snapshot: MechanisticState) -> None:
        self._validate_bounds(state_snapshot)
        self._state = copy.deepcopy(state_snapshot)

    @classmethod
    def compute_e_cl_mv(cls, cl_in_mm: float, cl_out_mm: float) -> float:
        """Nernst reversal potential for Cl- (valence z = -1)."""
        if cl_in_mm <= 0.0 or cl_out_mm <= 0.0:
            raise BiophysicalNumericalError(f"Non-positive chloride concentration: in={cl_in_mm}, out={cl_out_mm}")
        return -cls.RT_OVER_F_MV * math.log(cl_out_mm / cl_in_mm)

    @classmethod
    def compute_e_gaba_ghk_mv(
        cls,
        cl_in_mm: float,
        cl_out_mm: float,
        hco3_in_mm: float,
        hco3_out_mm: float,
    ) -> float:
        """
        Goldman-Hodgkin-Katz (GHK) reversal potential for GABA_A receptor channel
        permeable to both Cl- and HCO3- (valence z = -1):
          E_GABA = (RT/F) * ln((P_Cl*[Cl]_i + P_HCO3*[HCO3]_i) / (P_Cl*[Cl]_o + P_HCO3*[HCO3]_o))
        """
        num = cl_in_mm + cls.P_HCO3_TO_CL_RATIO * hco3_in_mm
        den = cl_out_mm + cls.P_HCO3_TO_CL_RATIO * hco3_out_mm
        if num <= 0.0 or den <= 0.0:
            raise BiophysicalNumericalError(f"Invalid GHK concentrations: num={num}, den={den}")
        return cls.RT_OVER_F_MV * math.log(num / den)

    @classmethod
    def compute_kcc2_extrusion_mm_per_s(
        cls,
        kcc2_rate_per_sec: float,
        k_in_mm: float,
        cl_in_mm: float,
        k_out_mm: float,
        cl_out_mm: float,
    ) -> float:
        """
        Thermodynamically grounded electroneutral K+-Cl- cotransport flux.
        Driven by the net chemical potential product ([K+]_i * [Cl-]_i - [K+]_o * [Cl-]_o).
        Vanishes identically at thermodynamic equilibrium: [Cl-]_i,eq = ([K+]_o * [Cl-]_o) / [K+]_i.
        """
        denom = k_out_mm * cl_out_mm
        if denom <= 0.0:
            raise BiophysicalNumericalError("Extracellular K+ or Cl- concentration is non-positive.")
        driving_force = (k_in_mm * cl_in_mm - denom) / denom
        return kcc2_rate_per_sec * driving_force

    @staticmethod
    def _validate_bounds(st: MechanisticState) -> None:
        for fname in (
            "cl_in_mm",
            "cl_out_mm",
            "hco3_in_mm",
            "hco3_out_mm",
            "k_in_mm",
            "k_out_mm",
            "wdr_voltage_mv",
            "wdr_firing_hz",
        ):
            val = getattr(st, fname)
            if not isinstance(val, (int, float)) or not math.isfinite(val):
                raise BiophysicalNumericalError(f"Non-finite biophysical state {fname}={val!r}")
        if not (1.0 <= st.cl_in_mm <= 80.0):
            raise BiophysicalNumericalError(f"[Cl-]_i={st.cl_in_mm} mM exited physical bounds [1.0, 80.0] mM.")
        if not (80.0 <= st.k_in_mm <= 180.0):
            raise BiophysicalNumericalError(f"[K+]_i={st.k_in_mm} mM exited physical bounds [80.0, 180.0] mM.")
        if not (2.0 <= st.k_out_mm <= 15.0):
            raise BiophysicalNumericalError(f"[K+]_o={st.k_out_mm} mM exited physical bounds [2.0, 15.0] mM.")
        if not (-100.0 <= st.wdr_voltage_mv <= 40.0):
            raise BiophysicalNumericalError(f"V_m={st.wdr_voltage_mv} mV exited physical bounds [-100.0, 40.0] mV.")

    def _update_steady_voltage_and_firing(self, g_gaba_active: float = 0.0) -> None:
        st = self._state
        e_gaba = self.compute_e_gaba_ghk_mv(st.cl_in_mm, st.cl_out_mm, st.hco3_in_mm, st.hco3_out_mm)
        g_exc = 0.0014 * st.c_fiber_drive_hz
        g_gaba = 0.015 + g_gaba_active
        g_tot = self.G_LEAK_MS_CM2 + g_exc + g_gaba
        v_ss = (
            self.G_LEAK_MS_CM2 * self.E_LEAK_MV + g_exc * self.E_EXC_MV + g_gaba * e_gaba
        ) / g_tot
        st.wdr_voltage_mv = v_ss
        # Threshold-linear firing rate above spike threshold V_th = -59.5 mV
        v_th = -59.5
        st.wdr_firing_hz = max(0.0, min(90.0, 5.2 * max(0.0, v_ss - v_th)))

    def _wdr_to_pain(self, wdr_hz: float) -> float:
        return max(0.0, min(10.0, wdr_hz / 5.0))

    def current_output(self) -> PhysicalPlantOutput:
        st = self._state
        e_gaba = self.compute_e_gaba_ghk_mv(st.cl_in_mm, st.cl_out_mm, st.hco3_in_mm, st.hco3_out_mm)
        pain = self._wdr_to_pain(st.wdr_firing_hz)
        eq_cl = (st.k_out_mm * st.cl_out_mm) / st.k_in_mm
        cl_shift = max(0.0, (st.cl_in_mm - 6.5) * 0.28)
        func = max(0.0, min(10.0, 0.65 * pain + 0.35 * cl_shift))
        # Derive equivalent phenomenological traces for diagnostic inspection
        basal_pain = self._wdr_to_pain(max(0.0, 5.2 * ((-65.0 * 0.1 + 0.0014 * st.c_fiber_drive_hz * 0.0 + 0.015 * (-70.0)) / (0.115 + 0.0014 * st.c_fiber_drive_hz) - (-59.5))))
        analgesia_equiv = max(0.0, basal_pain - pain)
        return PhysicalPlantOutput(
            step_k=st.step_k,
            time_sec=st.time_sec,
            true_latent_pain=pain,
            true_functional_impairment=func,
            analgesic_trace=analgesia_equiv,
            habituation=st.synaptic_depression,
            delayed_sensitization=cl_shift,
            query_burden=st.query_burden,
            contact_quality=st.contact_quality,
            mechanistic_wdr_hz=st.wdr_firing_hz,
            intracellular_cl_mm=st.cl_in_mm,
            e_gaba_mv=e_gaba,
        )

    def sample_contact_quality(self, step_k: int, rng: SemanticRNG) -> float:
        st = self._state
        if st.fault_start_step <= step_k <= st.fault_end_step:
            cq = max(0.18, min(0.30, 0.24 + rng.normal("contact_dynamics", step_k, 0.0, 0.02, draw_index=0)))
        else:
            cq = max(0.78, min(1.0, 0.95 + rng.normal("contact_dynamics", step_k, 0.0, 0.015, draw_index=1)))
        st.contact_quality = cq
        return cq

    def relax_to_equilibrium(self, duration_sec: float) -> MechanisticState:
        """
        Pure passive relaxation utility (zero synaptic input, zero stimulation)
        used by verification tests to confirm convergence to KCC2 thermodynamic equilibrium.
        """
        st = self._state
        n_steps = max(1, int(round(duration_sec / self.SUBSTEP_DT_SEC)))
        dt = duration_sec / n_steps
        for _ in range(n_steps):
            j_kcc2 = self.compute_kcc2_extrusion_mm_per_s(
                st.kcc2_rate_per_sec, st.k_in_mm, st.cl_in_mm, st.k_out_mm, st.cl_out_mm
            )
            st.cl_in_mm -= dt * j_kcc2
            self._validate_bounds(st)
        self._update_steady_voltage_and_firing(0.0)
        return copy.deepcopy(st)

    def step(
        self,
        exposure: DeliveredExposure,
        query_requested: bool,
        rng: SemanticRNG,
    ) -> PhysicalPlantOutput:
        if not isinstance(exposure, DeliveredExposure):
            raise ContractViolationError(
                f"MechanisticDorsalHornPlant.step requires DeliveredExposure, got {type(exposure).__name__}"
            )
        st = self._state
        dt_total = require_range(exposure.dt_sec, "dt_sec", 0.0, 3600.0)
        k = st.step_k
        u_del = exposure.delivered_intensity

        # Background C-fiber nociceptive drive
        dt_scale = math.sqrt(dt_total / 30.0) if dt_total > 0.0 else 0.0
        c_drift = rng.normal("env_disturbance", k, 0.0, 0.85 * dt_scale, draw_index=0)
        flare_hz = 6.5 if (st.phenotype == "baseline_flare" and 12 <= k <= 22) else 0.0
        st.c_fiber_drive_hz = max(14.0, min(42.0, 28.0 + flare_hz + 3.0 * math.sin((st.time_sec + dt_total) / 270.0) + c_drift))

        # Frequency-dependent vesicle depletion multiplier
        wf = exposure.waveform
        if st.frequency_response_mode == "frequency_neutral":
            dep_mult = 1.0
        elif st.frequency_response_mode == "burst_slows_habituation":
            dep_mult = 0.45 if wf.is_burst_modulated else 1.15
        else:
            dep_mult = 1.25 if wf.is_burst_modulated else 0.55

        n_sub = max(1, int(round(dt_total / self.SUBSTEP_DT_SEC)))
        dt_sub = dt_total / n_sub if dt_total > 0.0 else 0.0

        for _ in range(n_sub):
            if dt_sub <= 0.0:
                break
            # 1. Synaptic depression dynamics
            dep_target = min(0.82, 0.85 * u_del * dep_mult) if u_del > 0.0 else 0.0
            tau_dep = 160.0
            decay_d = math.exp(-dt_sub / tau_dep)
            st.synaptic_depression = decay_d * st.synaptic_depression + (1.0 - decay_d) * dep_target

            # 2. A-beta evoked GABA_A conductance
            g_gaba_evoked = 0.135 * st.abeta_coupling_gain * u_del * (1.0 - 0.65 * st.synaptic_depression)
            self._update_steady_voltage_and_firing(g_gaba_evoked)

            # 3. Chloride influx through GABA_A channels + electroneutral KCC2 extrusion
            e_cl = self.compute_e_cl_mv(st.cl_in_mm, st.cl_out_mm)
            # Inward Cl- movement occurs when V_m > E_Cl (outward negative current = Cl- entry)
            cl_driving_mv = max(0.0, st.wdr_voltage_mv - e_cl)
            # Evoked GABA conductance loads intracellular Cl- proportional to driving force
            # Plus small basal tonic Cl- load balanced at rest (~6.2 mM in intact, ~11.5 mM in impaired)
            eq_cl = (st.k_out_mm * st.cl_out_mm) / st.k_in_mm
            basal_target_cl = 6.2 if st.kcc2_rate_per_sec > 0.04 else 11.5
            basal_cl_influx = st.kcc2_rate_per_sec * (st.k_in_mm * (basal_target_cl - eq_cl)) / (st.k_out_mm * st.cl_out_mm)
            evoked_cl_influx = 0.022 * g_gaba_evoked * cl_driving_mv

            j_kcc2 = self.compute_kcc2_extrusion_mm_per_s(
                st.kcc2_rate_per_sec, st.k_in_mm, st.cl_in_mm, st.k_out_mm, st.cl_out_mm
            )
            d_cl = (basal_cl_influx + evoked_cl_influx) - j_kcc2
            st.cl_in_mm = max(2.0, min(55.0, st.cl_in_mm + dt_sub * d_cl))
            self._validate_bounds(st)

        # Final firing rate update at end of macro-step
        g_gaba_final = (
            0.135 * st.abeta_coupling_gain * u_del * (1.0 - 0.65 * st.synaptic_depression)
            if u_del > 0.0
            else 0.0
        )
        self._update_steady_voltage_and_firing(g_gaba_final)

        if query_requested:
            st.query_burden = min(1.0, st.query_burden + 0.20 * (dt_total / 30.0))
        else:
            decay_q = math.exp(-dt_total / 180.0) if dt_total > 0.0 else 1.0
            st.query_burden *= decay_q

        st.step_k += 1
        st.time_sec += dt_total
        self._validate_bounds(st)
        return self.current_output()
