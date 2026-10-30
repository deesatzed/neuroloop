"""
Independent Safety Supervisor with explicit fault latching, anti-chattering rearm hysteresis,
and fast-tick stop latency tracking for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Dict, Mapping, Optional

from neuroloop.config import SupervisorConfig, TimingConfig
from neuroloop.contracts import (
    ContractViolationError,
    ControlAction,
    FeedbackCommand,
    ProgramSpec,
    PublicObservation,
    StimulationCommand,
)


@dataclass
class SupervisorState:
    active_program_id: str = "P00_OFF"
    fault_latched: bool = False
    consecutive_clean_steps: int = 0
    total_fault_stops: int = 0
    total_rearms: int = 0
    last_stop_latency_ms: int = 0


@dataclass(frozen=True)
class SupervisionDecision:
    proposed_action: ControlAction
    approved_program: ProgramSpec
    feedback_requested: bool
    prompt_id: Optional[str]
    proposal_violated: bool
    violation_reason: Optional[str]
    fault_latched_before: bool
    fault_latched_after: bool
    rearmed_this_step: bool
    stop_latency_ms: int


class SafetySupervisor:
    """
    Intercepts controller proposals, enforces permissible action envelopes using ONLY
    declared accessible telemetry (never hidden phenotype or latent pain truth),
    and manages the fault latch / rearm state machine to prevent ON/OFF chattering.
    """

    def __init__(
        self,
        supervisor_cfg: SupervisorConfig,
        timing_cfg: TimingConfig,
        program_catalog: Mapping[str, ProgramSpec],
    ) -> None:
        if "P00_OFF" not in program_catalog:
            raise ContractViolationError("program_catalog must contain 'P00_OFF'.")
        self._cfg = supervisor_cfg
        self._timing = timing_cfg
        self._catalog: Dict[str, ProgramSpec] = dict(program_catalog)
        self._state = SupervisorState()

    @property
    def state(self) -> SupervisorState:
        return copy.deepcopy(self._state)

    def snapshot(self) -> SupervisorState:
        return copy.deepcopy(self._state)

    def restore(self, state: SupervisorState) -> None:
        self._state = copy.deepcopy(state)

    def evaluate_proposal(
        self,
        proposed: ControlAction,
        latest_obs: Optional[PublicObservation],
    ) -> SupervisionDecision:
        if not isinstance(proposed, ControlAction):
            raise ContractViolationError(f"Expected ControlAction, got {type(proposed).__name__}")

        latched_before = self._state.fault_latched
        rearmed = False
        stop_latency_ms = 0

        # 1. Inspect accessible telemetry for hardware / impedance fault conditions
        fault_present_now = False
        if latest_obs is not None:
            high_z = latest_obs.electrode.impedance_real_ohm > self._cfg.max_safe_impedance_ohm
            saturated = latest_obs.electrode.compliance_limit_reached
            fault_present_now = high_z or saturated

        if fault_present_now:
            self._state.consecutive_clean_steps = 0
            if self._cfg.latch_on_fault and not self._state.fault_latched:
                self._state.fault_latched = True
                self._state.total_fault_stops += 1
                stop_latency_ms = self._timing.fast_tick_ms
                self._state.last_stop_latency_ms = stop_latency_ms
        else:
            if self._state.fault_latched:
                self._state.consecutive_clean_steps += 1
                if self._state.consecutive_clean_steps >= self._timing.rearm_required_clean_steps:
                    self._state.fault_latched = False
                    self._state.consecutive_clean_steps = 0
                    self._state.total_rearms += 1
                    rearmed = True

        # 2. Resolve requested target program from orthogonal stimulation command
        violated = False
        violation_reason: Optional[str] = None

        if proposed.stimulation == StimulationCommand.OFF:
            requested_id = "P00_OFF"
        elif proposed.stimulation == StimulationCommand.HOLD:
            requested_id = self._state.active_program_id
        elif proposed.stimulation == StimulationCommand.SET:
            assert proposed.target_program_id is not None
            if proposed.target_program_id not in self._catalog:
                violated = True
                violation_reason = f"unknown_program:{proposed.target_program_id}"
                requested_id = "P00_OFF"
            else:
                requested_id = proposed.target_program_id
        else:
            raise ContractViolationError(f"Unsupported stimulation command: {proposed.stimulation!r}")

        if latest_obs is not None and proposed.observation_sequence != latest_obs.timing_meta.observation_sequence:
            violated = True
            violation_reason = (
                f"stale_observation_sequence:{proposed.observation_sequence}!=latest:{latest_obs.timing_meta.observation_sequence}"
            )
            requested_id = "P00_OFF"

        requested_spec = self._catalog[requested_id]

        # 3. Enforce fault latch and fault envelope
        active_fault_lock = fault_present_now or self._state.fault_latched
        if active_fault_lock:
            if requested_spec.normalized_intensity > self._cfg.max_intensity_under_fault:
                # Proposing active stimulation while a visible fault or active latch is present in latest_obs
                if latest_obs is not None and (
                    latest_obs.electrode.impedance_real_ohm > self._cfg.max_safe_impedance_ohm
                    or latest_obs.electrode.compliance_limit_reached
                    or latest_obs.electrode.fault_latched
                ):
                    violated = True
                    violation_reason = violation_reason or "active_stimulation_proposed_during_fault_or_latch"
                approved_spec = self._catalog["P00_OFF"]
            else:
                approved_spec = requested_spec
        else:
            approved_spec = requested_spec

        self._state.active_program_id = approved_spec.program_id
        feedback_req = proposed.feedback == FeedbackCommand.REQUEST

        return SupervisionDecision(
            proposed_action=proposed,
            approved_program=approved_spec,
            feedback_requested=feedback_req,
            prompt_id=proposed.prompt_id if feedback_req else None,
            proposal_violated=violated,
            violation_reason=violation_reason,
            fault_latched_before=latched_before,
            fault_latched_after=self._state.fault_latched,
            rearmed_this_step=rearmed,
            stop_latency_ms=stop_latency_ms,
        )
