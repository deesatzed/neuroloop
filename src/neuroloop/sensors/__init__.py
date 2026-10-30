"""
Causal Sensor Pipeline and Pending-Report Queue with explicit integer millisecond timestamps.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import List, Optional

from neuroloop.config import ActuatorConfig, TimingConfig
from neuroloop.contracts import (
    DeliveredExposure,
    DeliveredStimulationView,
    ElectrodeTelemetry,
    EMGTelemetry,
    IMUTelemetry,
    ObservationWindowMetadata,
    PatientReportView,
    PublicObservation,
    ReportStatus,
)
from neuroloop.randomness import SemanticRNG


@dataclass
class PendingPromptItem:
    prompt_id: str
    acquisition_step_k: int
    acquisition_time_ms: int
    availability_step_k: int
    availability_time_ms: int
    answered: bool
    sampled_pain_value: Optional[int]


@dataclass
class SensorPipelineState:
    observation_sequence: int = 0
    last_visible_pain_report: Optional[int] = None
    last_visible_acquisition_sec: Optional[float] = None
    last_visible_availability_sec: Optional[float] = None
    pending_queue: List[PendingPromptItem] = field(default_factory=list)


class SensorPipeline:
    """
    Transforms physical plant outputs and actuator delivery records into strictly causal
    PublicObservation instances.
    Manages the PendingReportQueue so future delayed reports are never leaked early,
    ignored prompts are never misclassified as zero pain, and zero pain (0) is preserved.
    """

    def __init__(
        self,
        timing_cfg: TimingConfig,
        actuator_cfg: ActuatorConfig,
        actuator_mode: str,
    ) -> None:
        self._timing = timing_cfg
        self._actuator_cfg = actuator_cfg
        self._actuator_mode = actuator_mode
        self._state = SensorPipelineState()

    def snapshot(self) -> SensorPipelineState:
        return copy.deepcopy(self._state)

    def restore(self, state: SensorPipelineState) -> None:
        self._state = copy.deepcopy(state)

    def measure_load_impedance(
        self,
        step_k: int,
        contact_quality: float,
        rng: SemanticRNG,
    ) -> tuple[float, float]:
        """Samples complex bioimpedance from physical contact quality."""
        base_r = (
            self._actuator_cfg.toy_resistive_ohm
            if self._actuator_mode == "toy_resistive"
            else self._actuator_cfg.nominal_impedance_ohm
        )
        z_real = (base_r / max(0.08, contact_quality)) + rng.normal(
            "sensor_noise", step_k, mean=0.0, std=base_r * 0.035, draw_index=0
        )
        z_imag = (-0.20 * base_r / max(0.08, contact_quality)) + rng.normal(
            "sensor_noise", step_k, mean=0.0, std=base_r * 0.01, draw_index=1
        )
        return max(100.0, round(z_real, 2)), round(z_imag, 2)

    def emit_observation(
        self,
        local_episode_sequence: int,
        step_k: int,
        true_latent_pain: float,
        true_functional_impairment: float,
        query_burden: float,
        contact_quality: float,
        z_real_ohm: float,
        z_imag_ohm: float,
        active_program_id: str,
        exposure: DeliveredExposure,
        fault_latched: bool,
        prompt_requested: bool,
        prompt_id: Optional[str],
        rng: SemanticRNG,
        ablate_impedance: bool = False,
        ablate_reports: bool = False,
    ) -> PublicObservation:
        dt_ms = int(round(self._timing.macro_step_dt_sec * 1000))
        now_ms = step_k * dt_ms
        win_start_ms = max(0, now_ms - dt_ms)
        time_sec = now_ms / 1000.0

        # 1. Enqueue newly requested patient prompt (if any)
        if prompt_requested and not ablate_reports:
            eff_prompt_id = prompt_id or f"prompt_step_{step_k}"
            # Within the 2-query calibration budget (query_burden <= 0.45), patient completes calibration prompts;
            # excessive querying beyond calibration induces fatigue and missed responses.
            reply_prob = 1.0 if query_burden <= 0.45 else max(0.15, 0.95 - 0.80 * query_burden)
            u_reply = rng.uniform("patient_reporting", step_k, draw_index=0)
            answered = u_reply < reply_prob
            sampled_vas: Optional[int] = None
            if answered:
                obs_noise = rng.normal(
                    "patient_reporting", step_k, mean=0.35 * query_burden, std=0.45, draw_index=1
                )
                sampled_vas = int(round(max(0.0, min(10.0, true_latent_pain + obs_noise))))
            delay_steps = self._timing.report_delay_steps
            avail_step = step_k + delay_steps
            avail_ms = avail_step * dt_ms
            self._state.pending_queue.append(
                PendingPromptItem(
                    prompt_id=eff_prompt_id,
                    acquisition_step_k=step_k,
                    acquisition_time_ms=now_ms,
                    availability_step_k=avail_step,
                    availability_time_ms=avail_ms,
                    answered=answered,
                    sampled_pain_value=sampled_vas,
                )
            )

        # 2. Release any pending prompt responses whose availability_step_k <= step_k
        due_items: List[PendingPromptItem] = []
        still_pending: List[PendingPromptItem] = []
        for item in self._state.pending_queue:
            if item.availability_step_k <= step_k:
                due_items.append(item)
            else:
                still_pending.append(item)
        self._state.pending_queue = still_pending

        latest_prompt_val: Optional[int] = None
        latest_prompt_id: Optional[str] = None
        status = ReportStatus.NONE_YET

        if due_items:
            last_due = due_items[-1]
            latest_prompt_id = last_due.prompt_id
            if last_due.answered and last_due.sampled_pain_value is not None:
                latest_prompt_val = last_due.sampled_pain_value
                self._state.last_visible_pain_report = last_due.sampled_pain_value
                self._state.last_visible_acquisition_sec = last_due.acquisition_time_ms / 1000.0
                self._state.last_visible_availability_sec = last_due.availability_time_ms / 1000.0
                status = ReportStatus.NEW_PROMPT_RESPONSE
            else:
                status = ReportStatus.PROMPT_IGNORED

        # 3. Spontaneous report or initial baseline report at step_k == 0
        spont_u = rng.uniform("patient_reporting", step_k, draw_index=2)
        spont_trigger = (step_k == 0) or (not ablate_reports and spont_u < 0.10)
        if spont_trigger and status not in (ReportStatus.NEW_PROMPT_RESPONSE, ReportStatus.PROMPT_IGNORED):
            spont_noise = rng.normal("patient_reporting", step_k, mean=0.0, std=0.40, draw_index=3)
            spont_vas = int(round(max(0.0, min(10.0, true_latent_pain + spont_noise))))
            self._state.last_visible_pain_report = spont_vas
            self._state.last_visible_acquisition_sec = time_sec
            self._state.last_visible_availability_sec = time_sec
            status = ReportStatus.SPONTANEOUS

        if status == ReportStatus.NONE_YET:
            if self._state.pending_queue:
                status = ReportStatus.PENDING_UNAVAILABLE
            elif self._state.last_visible_pain_report is not None:
                status = ReportStatus.STALE_CACHED

        # 4. EMG and IMU causal feature windows
        emg_rms = max(
            1.0,
            15.0 + 4.5 * true_functional_impairment + rng.normal("sensor_noise", step_k, 0.0, 1.5, draw_index=4),
        )
        imu_acc = max(
            0.01,
            0.12 + 0.04 * true_functional_impairment + rng.normal("sensor_noise", step_k, 0.0, 0.015, draw_index=5),
        )
        imu_gyro = max(
            0.1,
            3.5 + 1.2 * true_functional_impairment + rng.normal("sensor_noise", step_k, 0.0, 0.3, draw_index=6),
        )

        obs_seq = self._state.observation_sequence
        self._state.observation_sequence += 1

        reported_z_real = 12_500.0 if ablate_impedance else z_real_ohm
        reported_z_imag = -2_500.0 if ablate_impedance else z_imag_ohm
        reported_compliance = False if ablate_impedance else exposure.compliance_limited
        reported_latched = False if ablate_impedance else fault_latched

        return PublicObservation(
            local_episode_sequence=local_episode_sequence,
            step_k=step_k,
            time_sec=time_sec,
            timing_meta=ObservationWindowMetadata(
                observation_sequence=obs_seq,
                acquisition_time_ms=now_ms,
                availability_time_ms=now_ms,
                window_start_ms=win_start_ms,
                window_end_ms=now_ms,
            ),
            electrode=ElectrodeTelemetry(
                impedance_real_ohm=reported_z_real,
                impedance_imag_ohm=reported_z_imag,
                measurement_frequency_hz=1000.0,
                output_voltage_v=exposure.output_voltage_v,
                compliance_limit_reached=reported_compliance,
                fault_latched=reported_latched,
            ),
            emg=EMGTelemetry(
                rms_uv=round(emg_rms, 2),
                spectral_features=(
                    round(0.25 + 0.03 * exposure.delivered_intensity, 3),
                    round(0.45 + 0.02 * true_functional_impairment, 3),
                    round(0.30, 3),
                ),
                window_duration_ms=float(dt_ms),
                missing=False,
            ),
            imu=IMUTelemetry(
                acceleration_rms_g=round(imu_acc, 4),
                angular_velocity_rms_dps=round(imu_gyro, 3),
                missing=False,
            ),
            patient=PatientReportView(
                last_pain_report=self._state.last_visible_pain_report,
                last_report_acquisition_time_sec=self._state.last_visible_acquisition_sec,
                last_report_availability_time_sec=self._state.last_visible_availability_sec,
                latest_prompt_response=latest_prompt_val,
                latest_prompt_id=latest_prompt_id,
                report_status=status,
                pending_prompts_count=len(self._state.pending_queue),
            ),
            delivered=DeliveredStimulationView(
                active_program_id=active_program_id,
                requested_intensity=exposure.requested_intensity,
                delivered_intensity=exposure.delivered_intensity,
                delivery_status=exposure.delivery_status,
                delivery_confirmed=exposure.delivery_confirmed,
                stimulation_effort=exposure.stimulation_effort,
            ),
        )
