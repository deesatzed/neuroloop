"""
Validated public and privileged value contracts, orthogonal action algebra,
waveform specifications, and pulse-event rendering for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple


class NeuroLoopError(Exception):
    """Base exception for all NeuroLoop errors."""


class ContractViolationError(NeuroLoopError):
    """Raised when an action, observation, or state violates schema/range invariants."""


class ConfigurationError(NeuroLoopError):
    """Raised when protocol configuration contains unknown keys, invalid types, or non-finite values."""


class BiophysicalNumericalError(NeuroLoopError):
    """Raised when ionic concentrations, voltages, or state variables diverge or exit physical bounds."""


class IsolationViolationError(NeuroLoopError):
    """Raised when a boundary check detects prohibited references or side-channel leakage."""


def require_finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractViolationError(f"Field '{name}' must be a real number, got {type(value).__name__}")
    fval = float(value)
    if not math.isfinite(fval):
        raise ContractViolationError(f"Field '{name}' must be finite, got {value!r}")
    return fval


def require_range(value: float, name: str, low: float, high: float) -> float:
    fval = require_finite(value, name)
    if fval < low or fval > high:
        raise ContractViolationError(
            f"Field '{name}'={fval} is outside allowed range [{low}, {high}]"
        )
    return fval


def require_int_non_negative(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolationError(f"Field '{name}' must be an integer, got {type(value).__name__}")
    if value < 0:
        raise ContractViolationError(f"Field '{name}' must be >= 0, got {value}")
    return value


class StimulationCommand(enum.Enum):
    """Orthogonal stimulation command component."""
    HOLD = "HOLD"
    SET = "SET"
    OFF = "OFF"


class FeedbackCommand(enum.Enum):
    """Orthogonal patient feedback query component."""
    NONE = "NONE"
    REQUEST = "REQUEST"


class DeliveryStatus(enum.Enum):
    """Explicit actuator delivery status."""
    OFF = "OFF"
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    FAULT = "FAULT"


class ReportStatus(enum.Enum):
    """Explicit patient pain report status distinguishing new, stale, ignored, and pending reports."""
    NONE_YET = "NONE_YET"
    NEW_PROMPT_RESPONSE = "NEW_PROMPT_RESPONSE"
    SPONTANEOUS = "SPONTANEOUS"
    STALE_CACHED = "STALE_CACHED"
    PROMPT_IGNORED = "PROMPT_IGNORED"
    PENDING_UNAVAILABLE = "PENDING_UNAVAILABLE"


@dataclass(frozen=True)
class WaveformSpec:
    """
    Explicit physical/synthetic waveform timing specification.
    Separates intraburst pulse repetition frequency from burst repetition frequency,
    pulses per burst, and pulse width.
    """
    pulse_freq_hz: float
    burst_freq_hz: float
    pulses_per_burst: int
    pulse_width_us: float
    biphasic_symmetric: bool = True

    def __post_init__(self) -> None:
        pf = require_range(self.pulse_freq_hz, "pulse_freq_hz", 0.0, 10_000.0)
        bf = require_range(self.burst_freq_hz, "burst_freq_hz", 0.0, 1_000.0)
        ppb = require_int_non_negative(self.pulses_per_burst, "pulses_per_burst")
        pw = require_range(self.pulse_width_us, "pulse_width_us", 0.0, 5_000.0)
        if pf == 0.0 and (bf > 0.0 or ppb > 0 or pw > 0.0):
            raise ContractViolationError("Inactive waveform (pulse_freq_hz=0) must have zero burst/width fields.")
        if bf > 0.0:
            if ppb < 2:
                raise ContractViolationError("Burst mode (burst_freq_hz > 0) requires pulses_per_burst >= 2.")
            if bf >= pf:
                raise ContractViolationError("burst_freq_hz must be strictly less than intraburst pulse_freq_hz.")
            burst_duration_s = (ppb - 1) / pf + (pw * 1e-6)
            if burst_duration_s > (1.0 / bf):
                raise ContractViolationError("Burst duration exceeds inter-burst period (1 / burst_freq_hz).")
        object.__setattr__(self, "pulse_freq_hz", pf)
        object.__setattr__(self, "burst_freq_hz", bf)
        object.__setattr__(self, "pulse_width_us", pw)

    @property
    def is_burst_modulated(self) -> bool:
        return self.burst_freq_hz > 0.0 and self.pulses_per_burst >= 2

    @property
    def effective_pulse_rate_hz(self) -> float:
        """Average number of pulses delivered per second."""
        if self.pulse_freq_hz <= 0.0:
            return 0.0
        if self.is_burst_modulated:
            return self.burst_freq_hz * float(self.pulses_per_burst)
        return self.pulse_freq_hz

    @property
    def duty_cycle_fraction(self) -> float:
        """Active pulse-width time fraction per second."""
        return self.effective_pulse_rate_hz * (self.pulse_width_us * 1e-6)


@dataclass(frozen=True)
class PulseTrainRenderResult:
    """Deterministic pulse-event rendering summary over a macro-step window."""
    duration_sec: float
    total_pulses: int
    total_bursts: int
    integrated_active_time_sec: float
    first_pulse_time_sec: Optional[float]
    last_pulse_time_sec: Optional[float]


def render_pulse_events(waveform: WaveformSpec, duration_sec: float) -> PulseTrainRenderResult:
    """
    Renders discrete pulse events over [0, duration_sec) to verify pulse counts,
    burst boundaries, and integrated exposure independently of neural models.
    """
    dur = require_range(duration_sec, "duration_sec", 0.0, 86_400.0)
    if dur == 0.0 or waveform.pulse_freq_hz <= 0.0:
        return PulseTrainRenderResult(
            duration_sec=dur,
            total_pulses=0,
            total_bursts=0,
            integrated_active_time_sec=0.0,
            first_pulse_time_sec=None,
            last_pulse_time_sec=None,
        )

    pulse_times: List[float] = []
    burst_count = 0
    if not waveform.is_burst_modulated:
        dt_p = 1.0 / waveform.pulse_freq_hz
        n_pulses = int(math.floor(dur * waveform.pulse_freq_hz + 1e-9))
        for idx in range(n_pulses):
            t_p = idx * dt_p
            if t_p < dur - 1e-12:
                pulse_times.append(t_p)
    else:
        dt_b = 1.0 / waveform.burst_freq_hz
        dt_p = 1.0 / waveform.pulse_freq_hz
        n_bursts = int(math.floor(dur * waveform.burst_freq_hz + 1e-9))
        for b_idx in range(n_bursts):
            t_b0 = b_idx * dt_b
            if t_b0 >= dur - 1e-12:
                break
            burst_has_pulse = False
            for p_idx in range(waveform.pulses_per_burst):
                t_p = t_b0 + p_idx * dt_p
                if t_p < dur - 1e-12:
                    pulse_times.append(t_p)
                    burst_has_pulse = True
            if burst_has_pulse:
                burst_count += 1

    total_p = len(pulse_times)
    phase_mult = 2.0 if waveform.biphasic_symmetric else 1.0
    active_time = total_p * (waveform.pulse_width_us * 1e-6) * phase_mult
    return PulseTrainRenderResult(
        duration_sec=dur,
        total_pulses=total_p,
        total_bursts=burst_count,
        integrated_active_time_sec=active_time,
        first_pulse_time_sec=pulse_times[0] if pulse_times else None,
        last_pulse_time_sec=pulse_times[-1] if pulse_times else None,
    )


@dataclass(frozen=True)
class ProgramSpec:
    """Immutable stimulation program specification."""
    program_id: str
    normalized_intensity: float
    waveform: WaveformSpec

    def __post_init__(self) -> None:
        if not isinstance(self.program_id, str) or not self.program_id.strip():
            raise ContractViolationError("program_id must be a non-empty string.")
        inten = require_range(self.normalized_intensity, "normalized_intensity", 0.0, 1.0)
        if not isinstance(self.waveform, WaveformSpec):
            raise ContractViolationError("waveform must be a WaveformSpec instance.")
        if inten == 0.0 and self.waveform.pulse_freq_hz > 0.0:
            raise ContractViolationError("Zero-intensity program must have zero waveform frequency.")
        if inten > 0.0 and self.waveform.pulse_freq_hz <= 0.0:
            raise ContractViolationError("Positive-intensity program must have positive pulse_freq_hz.")
        object.__setattr__(self, "normalized_intensity", inten)


def build_default_program_catalog() -> Dict[str, ProgramSpec]:
    """
    Canonical preset catalog with explicit intraburst vs. burst frequencies.
    P02_MOD_BURST explicitly specifies 100 Hz intraburst pulses modulated at 2 Hz bursts (5 pulses/burst).
    """
    return {
        "P00_OFF": ProgramSpec(
            program_id="P00_OFF",
            normalized_intensity=0.0,
            waveform=WaveformSpec(0.0, 0.0, 0, 0.0),
        ),
        "P01_LOW_CONV": ProgramSpec(
            program_id="P01_LOW_CONV",
            normalized_intensity=0.35,
            waveform=WaveformSpec(80.0, 0.0, 1, 150.0),
        ),
        "P02_MOD_BURST": ProgramSpec(
            program_id="P02_MOD_BURST",
            normalized_intensity=0.60,
            waveform=WaveformSpec(100.0, 2.0, 5, 200.0),
        ),
        "P03_HIGH_CONV": ProgramSpec(
            program_id="P03_HIGH_CONV",
            normalized_intensity=0.85,
            waveform=WaveformSpec(100.0, 0.0, 1, 250.0),
        ),
    }


DEFAULT_PROGRAM_CATALOG: Mapping[str, ProgramSpec] = build_default_program_catalog()


@dataclass(frozen=True)
class ControlAction:
    """
    Orthogonal controller action:
      - stimulation: HOLD | SET(target_program_id) | OFF
      - feedback: NONE | REQUEST(prompt_id)
      - observation_sequence: integer sequence number of the observation being acted upon
    """
    stimulation: StimulationCommand
    feedback: FeedbackCommand = FeedbackCommand.NONE
    target_program_id: Optional[str] = None
    prompt_id: Optional[str] = None
    observation_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stimulation, StimulationCommand):
            raise ContractViolationError(f"Invalid stimulation command: {self.stimulation!r}")
        if not isinstance(self.feedback, FeedbackCommand):
            raise ContractViolationError(f"Invalid feedback command: {self.feedback!r}")
        seq = require_int_non_negative(self.observation_sequence, "observation_sequence")
        object.__setattr__(self, "observation_sequence", seq)

        if self.stimulation == StimulationCommand.SET:
            if not isinstance(self.target_program_id, str) or not self.target_program_id.strip():
                raise ContractViolationError("StimulationCommand.SET requires a non-empty target_program_id.")
        elif self.stimulation == StimulationCommand.OFF:
            if self.target_program_id not in (None, "P00_OFF"):
                raise ContractViolationError(
                    f"Contradictory ControlAction: OFF command cannot specify target_program_id={self.target_program_id!r}"
                )
            object.__setattr__(self, "target_program_id", "P00_OFF")
        elif self.stimulation == StimulationCommand.HOLD:
            if self.target_program_id is not None:
                raise ContractViolationError(
                    f"Contradictory ControlAction: HOLD command must have target_program_id=None, got {self.target_program_id!r}"
                )

        if self.feedback == FeedbackCommand.REQUEST:
            if self.prompt_id is None:
                object.__setattr__(self, "prompt_id", f"prompt_seq_{seq}")
            elif not isinstance(self.prompt_id, str) or not self.prompt_id.strip():
                raise ContractViolationError("prompt_id must be a non-empty string when feedback=REQUEST.")
        else:
            if self.prompt_id is not None:
                raise ContractViolationError(
                    f"Contradictory ControlAction: FeedbackCommand.NONE cannot specify prompt_id={self.prompt_id!r}"
                )


@dataclass(frozen=True)
class DeliveredExposure:
    """
    The ONLY intervention object accepted by biological plant engines.
    Produced exclusively by the Virtual Actuator after Safety Supervision.
    Note: Contains physical/normalized waveform parameters, NOT privileged controller logic.
    """
    step_k: int
    dt_sec: float
    delivered_intensity: float          # Actual delivered normalized intensity [0.0, 1.0]
    requested_intensity: float          # Approved nominal intensity before load clamping [0.0, 1.0]
    effective_current_ma: Optional[float]  # None in normalized mode; finite mA in toy_resistive mode
    output_voltage_v: Optional[float]      # None in normalized mode; finite V in toy_resistive mode
    contact_factor: float               # Physical coupling factor [0.0, 1.0]
    delivery_status: DeliveryStatus
    delivery_confirmed: bool
    compliance_limited: bool
    waveform: WaveformSpec
    stimulation_effort: float           # Dimensionless effort integral over the step

    def __post_init__(self) -> None:
        require_int_non_negative(self.step_k, "step_k")
        require_range(self.dt_sec, "dt_sec", 0.0, 86_400.0)
        deliv = require_range(self.delivered_intensity, "delivered_intensity", 0.0, 1.0)
        req = require_range(self.requested_intensity, "requested_intensity", 0.0, 1.0)
        cf = require_range(self.contact_factor, "contact_factor", 0.0, 1.0)
        eff = require_range(self.stimulation_effort, "stimulation_effort", 0.0, 1e6)
        if self.effective_current_ma is not None:
            require_range(self.effective_current_ma, "effective_current_ma", 0.0, 500.0)
        if self.output_voltage_v is not None:
            require_range(self.output_voltage_v, "output_voltage_v", 0.0, 500.0)
        if not isinstance(self.delivery_status, DeliveryStatus):
            raise ContractViolationError(f"Invalid delivery_status: {self.delivery_status!r}")
        if not isinstance(self.waveform, WaveformSpec):
            raise ContractViolationError("waveform must be a WaveformSpec instance.")
        object.__setattr__(self, "delivered_intensity", deliv)
        object.__setattr__(self, "requested_intensity", req)
        object.__setattr__(self, "contact_factor", cf)
        object.__setattr__(self, "stimulation_effort", eff)


@dataclass(frozen=True)
class ElectrodeTelemetry:
    impedance_real_ohm: float
    impedance_imag_ohm: float
    measurement_frequency_hz: float
    output_voltage_v: Optional[float]
    compliance_limit_reached: bool
    fault_latched: bool

    def __post_init__(self) -> None:
        require_range(self.impedance_real_ohm, "impedance_real_ohm", 1.0, 1e7)
        require_range(self.impedance_imag_ohm, "impedance_imag_ohm", -1e7, 1e7)
        require_range(self.measurement_frequency_hz, "measurement_frequency_hz", 1.0, 1e6)
        if self.output_voltage_v is not None:
            require_range(self.output_voltage_v, "output_voltage_v", 0.0, 500.0)


@dataclass(frozen=True)
class EMGTelemetry:
    rms_uv: float
    spectral_features: Tuple[float, float, float]
    window_duration_ms: float
    missing: bool = False

    def __post_init__(self) -> None:
        require_range(self.rms_uv, "rms_uv", 0.0, 1e5)
        if len(self.spectral_features) != 3:
            raise ContractViolationError("spectral_features must be a 3-tuple of floats.")
        for idx, val in enumerate(self.spectral_features):
            require_finite(val, f"spectral_features[{idx}]")
        require_range(self.window_duration_ms, "window_duration_ms", 0.0, 6e5)


@dataclass(frozen=True)
class IMUTelemetry:
    acceleration_rms_g: float
    angular_velocity_rms_dps: float
    missing: bool = False

    def __post_init__(self) -> None:
        require_range(self.acceleration_rms_g, "acceleration_rms_g", 0.0, 100.0)
        require_range(self.angular_velocity_rms_dps, "angular_velocity_rms_dps", 0.0, 10_000.0)


@dataclass(frozen=True)
class PatientReportView:
    """
    Causal patient pain report view.
    Explicitly preserves `0` as a valid pain value (`0 is not None`).
    Distinguishes newly arrived reports from stale cached reports, ignored prompts, and pending queries.
    """
    last_pain_report: Optional[int]
    last_report_acquisition_time_sec: Optional[float]
    last_report_availability_time_sec: Optional[float]
    latest_prompt_response: Optional[int]
    latest_prompt_id: Optional[str]
    report_status: ReportStatus
    pending_prompts_count: int = 0

    def __post_init__(self) -> None:
        if self.last_pain_report is not None:
            if isinstance(self.last_pain_report, bool) or not isinstance(self.last_pain_report, int):
                raise ContractViolationError("last_pain_report must be int or None.")
            if not (0 <= self.last_pain_report <= 10):
                raise ContractViolationError(f"last_pain_report={self.last_pain_report} out of range [0, 10].")
        if self.latest_prompt_response is not None:
            if isinstance(self.latest_prompt_response, bool) or not isinstance(self.latest_prompt_response, int):
                raise ContractViolationError("latest_prompt_response must be int or None.")
            if not (0 <= self.latest_prompt_response <= 10):
                raise ContractViolationError(f"latest_prompt_response={self.latest_prompt_response} out of range [0, 10].")
        if self.last_report_acquisition_time_sec is not None:
            require_range(self.last_report_acquisition_time_sec, "last_report_acquisition_time_sec", 0.0, 1e7)
        if self.last_report_availability_time_sec is not None:
            require_range(self.last_report_availability_time_sec, "last_report_availability_time_sec", 0.0, 1e7)
        if not isinstance(self.report_status, ReportStatus):
            raise ContractViolationError(f"Invalid report_status: {self.report_status!r}")
        require_int_non_negative(self.pending_prompts_count, "pending_prompts_count")


@dataclass(frozen=True)
class DeliveredStimulationView:
    active_program_id: str
    requested_intensity: float
    delivered_intensity: float
    delivery_status: DeliveryStatus
    delivery_confirmed: bool
    stimulation_effort: float

    def __post_init__(self) -> None:
        if not isinstance(self.active_program_id, str) or not self.active_program_id.strip():
            raise ContractViolationError("active_program_id must be a non-empty string.")
        require_range(self.requested_intensity, "requested_intensity", 0.0, 1.0)
        require_range(self.delivered_intensity, "delivered_intensity", 0.0, 1.0)
        if not isinstance(self.delivery_status, DeliveryStatus):
            raise ContractViolationError(f"Invalid delivery_status: {self.delivery_status!r}")
        require_range(self.stimulation_effort, "stimulation_effort", 0.0, 1e6)


@dataclass(frozen=True)
class ObservationWindowMetadata:
    """Explicit integer millisecond timing metadata for every observation."""
    observation_sequence: int
    acquisition_time_ms: int
    availability_time_ms: int
    window_start_ms: int
    window_end_ms: int

    def __post_init__(self) -> None:
        require_int_non_negative(self.observation_sequence, "observation_sequence")
        require_int_non_negative(self.acquisition_time_ms, "acquisition_time_ms")
        require_int_non_negative(self.availability_time_ms, "availability_time_ms")
        require_int_non_negative(self.window_start_ms, "window_start_ms")
        require_int_non_negative(self.window_end_ms, "window_end_ms")
        if self.window_end_ms < self.window_start_ms:
            raise ContractViolationError("window_end_ms cannot precede window_start_ms.")
        if self.availability_time_ms < self.acquisition_time_ms:
            raise ContractViolationError("availability_time_ms cannot precede acquisition_time_ms.")


@dataclass(frozen=True)
class PublicObservation:
    """
    Strictly causal, immutable value payload passed to controllers.
    Contains ZERO callables, ZERO plant references, and ZERO phenotype/scenario tokens.
    """
    local_episode_sequence: int
    step_k: int
    time_sec: float
    timing_meta: ObservationWindowMetadata
    electrode: ElectrodeTelemetry
    emg: EMGTelemetry
    imu: IMUTelemetry
    patient: PatientReportView
    delivered: DeliveredStimulationView

    def __post_init__(self) -> None:
        require_int_non_negative(self.local_episode_sequence, "local_episode_sequence")
        require_int_non_negative(self.step_k, "step_k")
        require_range(self.time_sec, "time_sec", 0.0, 1e7)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes PublicObservation to a pure JSON-compatible dictionary."""
        return {
            "local_episode_sequence": self.local_episode_sequence,
            "step_k": self.step_k,
            "time_sec": self.time_sec,
            "timing_meta": {
                "observation_sequence": self.timing_meta.observation_sequence,
                "acquisition_time_ms": self.timing_meta.acquisition_time_ms,
                "availability_time_ms": self.timing_meta.availability_time_ms,
                "window_start_ms": self.timing_meta.window_start_ms,
                "window_end_ms": self.timing_meta.window_end_ms,
            },
            "electrode": {
                "impedance_real_ohm": self.electrode.impedance_real_ohm,
                "impedance_imag_ohm": self.electrode.impedance_imag_ohm,
                "measurement_frequency_hz": self.electrode.measurement_frequency_hz,
                "output_voltage_v": self.electrode.output_voltage_v,
                "compliance_limit_reached": self.electrode.compliance_limit_reached,
                "fault_latched": self.electrode.fault_latched,
            },
            "emg": {
                "rms_uv": self.emg.rms_uv,
                "spectral_features": list(self.emg.spectral_features),
                "window_duration_ms": self.emg.window_duration_ms,
                "missing": self.emg.missing,
            },
            "imu": {
                "acceleration_rms_g": self.imu.acceleration_rms_g,
                "angular_velocity_rms_dps": self.imu.angular_velocity_rms_dps,
                "missing": self.imu.missing,
            },
            "patient": {
                "last_pain_report": self.patient.last_pain_report,
                "last_report_acquisition_time_sec": self.patient.last_report_acquisition_time_sec,
                "last_report_availability_time_sec": self.patient.last_report_availability_time_sec,
                "latest_prompt_response": self.patient.latest_prompt_response,
                "latest_prompt_id": self.patient.latest_prompt_id,
                "report_status": self.patient.report_status.value,
                "pending_prompts_count": self.patient.pending_prompts_count,
            },
            "delivered": {
                "active_program_id": self.delivered.active_program_id,
                "requested_intensity": self.delivered.requested_intensity,
                "delivered_intensity": self.delivered.delivered_intensity,
                "delivery_status": self.delivered.delivery_status.value,
                "delivery_confirmed": self.delivered.delivery_confirmed,
                "stimulation_effort": self.delivered.stimulation_effort,
            },
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PublicObservation:
        tm = data["timing_meta"]
        el = data["electrode"]
        em = data["emg"]
        im = data["imu"]
        pt = data["patient"]
        dl = data["delivered"]
        return cls(
            local_episode_sequence=int(data["local_episode_sequence"]),
            step_k=int(data["step_k"]),
            time_sec=float(data["time_sec"]),
            timing_meta=ObservationWindowMetadata(
                observation_sequence=int(tm["observation_sequence"]),
                acquisition_time_ms=int(tm["acquisition_time_ms"]),
                availability_time_ms=int(tm["availability_time_ms"]),
                window_start_ms=int(tm["window_start_ms"]),
                window_end_ms=int(tm["window_end_ms"]),
            ),
            electrode=ElectrodeTelemetry(
                impedance_real_ohm=float(el["impedance_real_ohm"]),
                impedance_imag_ohm=float(el["impedance_imag_ohm"]),
                measurement_frequency_hz=float(el["measurement_frequency_hz"]),
                output_voltage_v=float(el["output_voltage_v"]) if el["output_voltage_v"] is not None else None,
                compliance_limit_reached=bool(el["compliance_limit_reached"]),
                fault_latched=bool(el["fault_latched"]),
            ),
            emg=EMGTelemetry(
                rms_uv=float(em["rms_uv"]),
                spectral_features=(
                    float(em["spectral_features"][0]),
                    float(em["spectral_features"][1]),
                    float(em["spectral_features"][2]),
                ),
                window_duration_ms=float(em["window_duration_ms"]),
                missing=bool(em["missing"]),
            ),
            imu=IMUMeasurement_from_dict(im),
            patient=PatientReportView(
                last_pain_report=int(pt["last_pain_report"]) if pt["last_pain_report"] is not None else None,
                last_report_acquisition_time_sec=(
                    float(pt["last_report_acquisition_time_sec"])
                    if pt["last_report_acquisition_time_sec"] is not None
                    else None
                ),
                last_report_availability_time_sec=(
                    float(pt["last_report_availability_time_sec"])
                    if pt["last_report_availability_time_sec"] is not None
                    else None
                ),
                latest_prompt_response=(
                    int(pt["latest_prompt_response"]) if pt["latest_prompt_response"] is not None else None
                ),
                latest_prompt_id=pt["latest_prompt_id"],
                report_status=ReportStatus(pt["report_status"]),
                pending_prompts_count=int(pt["pending_prompts_count"]),
            ),
            delivered=DeliveredStimulationView(
                active_program_id=str(dl["active_program_id"]),
                requested_intensity=float(dl["requested_intensity"]),
                delivered_intensity=float(dl["delivered_intensity"]),
                delivery_status=DeliveryStatus(dl["delivery_status"]),
                delivery_confirmed=bool(dl["delivery_confirmed"]),
                stimulation_effort=float(dl["stimulation_effort"]),
            ),
        )


def IMUMeasurement_from_dict(im: Mapping[str, Any]) -> IMUTelemetry:
    return IMUTelemetry(
        acceleration_rms_g=float(im["acceleration_rms_g"]),
        angular_velocity_rms_dps=float(im["angular_velocity_rms_dps"]),
        missing=bool(im["missing"]),
    )


@dataclass(frozen=True)
class StepLossBreakdown:
    """Privileged evaluator step-level loss decomposition."""
    pain_loss: float
    functional_loss: float
    effort_loss: float
    query_loss: float
    clinical_loss: float
    proposal_violation_loss: float
    fault_delivery_loss: float
    worsening_escalation_loss: float
    safety_loss: float
    total_loss: float
    proposal_violated: bool
    violation_reason: Optional[str]
    true_latent_pain: float
    true_functional_impairment: float
    mechanistic_wdr_hz: Optional[float] = None  # Populated ONLY by Engine A, never invented for Engine B
