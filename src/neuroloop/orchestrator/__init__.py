"""
Experiment Orchestrator, Closed-Loop Environment, Full-State SystemCheckpoint,
and Subprocess Isolation Runner for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from neuroloop.actuator import AbstractActuator, NormalizedActuator, ToyResistiveActuator
from neuroloop.config import ProtocolConfig
from neuroloop.contracts import (
    ContractViolationError,
    ControlAction,
    DEFAULT_PROGRAM_CATALOG,
    DeliveredExposure,
    FeedbackCommand,
    IsolationViolationError,
    ProgramSpec,
    PublicObservation,
    StepLossBreakdown,
    StimulationCommand,
)
from neuroloop.controllers import AbstractController, CalibrationRecord
from neuroloop.engines import AbstractPlantEngine, PhenomenologicalPlant, PhysicalPlantOutput
from neuroloop.engines.mechanistic import MechanisticDorsalHornPlant
from neuroloop.randomness import CanonicalScenarioKey, SemanticRNG
from neuroloop.sensors import SensorPipeline
from neuroloop.supervisor import SafetySupervisor, SupervisionDecision

FORBIDDEN_PUBLIC_TOKENS = (
    "responder",
    "nonresponder",
    "delayed_worsening",
    "chloride",
    "e_gaba",
    "secret",
    "null_effect",
    "baseline_flare",
)


def verify_public_observation_isolation(obs: PublicObservation) -> None:
    """
    Verifies that a PublicObservation instance is a pure value tree containing:
      - Zero callables or bound methods (`__self__`).
      - Zero references to Plant, Supervisor, or Evaluator objects.
      - Zero forbidden phenotype/mechanism tokens in any string representation.
    """
    if not isinstance(obs, PublicObservation):
        raise IsolationViolationError(f"Expected PublicObservation, got {type(obs).__name__}")

    def _walk(obj: Any, path: str) -> None:
        if callable(obj) or hasattr(obj, "__self__") or hasattr(obj, "__code__"):
            raise IsolationViolationError(f"Callable or bound method leaked at {path}: {obj!r}")
        if isinstance(obj, (AbstractPlantEngine, SafetySupervisor, SensorPipeline, AbstractActuator)):
            raise IsolationViolationError(f"Privileged engine/component reference leaked at {path}")
        if isinstance(obj, str):
            low = obj.lower()
            for tok in FORBIDDEN_PUBLIC_TOKENS:
                if tok in low:
                    raise IsolationViolationError(f"Forbidden privileged token '{tok}' leaked at {path}: {obj!r}")
        elif isinstance(obj, (list, tuple)):
            for idx, item in enumerate(obj):
                _walk(item, f"{path}[{idx}]")
        elif isinstance(obj, dict):
            for k, v in obj.items():
                _walk(k, f"{path}.key({k})")
                _walk(v, f"{path}[{k!r}]")
        elif hasattr(obj, "__dataclass_fields__"):
            for fname in obj.__dataclass_fields__:
                _walk(getattr(obj, fname), f"{path}.{fname}")

    _walk(obs, "PublicObservation")


@dataclass
class SystemCheckpoint:
    """
    Complete snapshot of all environment, actuator, supervisor, sensor queue,
    calibration, and controller states at a specific macro-step.
    Guarantees that counterfactual rollouts branch cleanly without mutating the primary run.
    """
    step_k: int
    active_program_id: str
    plant_snapshot: Any
    actuator_snapshot: Any
    supervisor_snapshot: Any
    sensor_snapshot: Any
    current_observation: PublicObservation
    controller_snapshot: Dict[str, Any]
    calibration_record: Optional[CalibrationRecord]


@dataclass(frozen=True)
class StepExecutionRecord:
    """Complete record of one executed closed-loop macro-step."""
    step_k: int
    time_sec: float
    observation_before: PublicObservation
    proposed_action: ControlAction
    supervision: SupervisionDecision
    exposure: DeliveredExposure
    plant_output: PhysicalPlantOutput
    observation_after: PublicObservation
    loss: StepLossBreakdown
    controller_belief: Optional[Dict[str, Any]]


def build_plant(
    config: ProtocolConfig,
    phenotype: str,
    rng: SemanticRNG,
) -> AbstractPlantEngine:
    if config.engine_mode == "engine_b_phenomenological":
        return PhenomenologicalPlant(
            phenotype=phenotype,
            frequency_response_mode=config.frequency_response_mode,
            rng=rng,
        )
    if config.engine_mode in ("engine_a_mechanistic", "engine_a_fast_surrogate"):
        return MechanisticDorsalHornPlant(
            phenotype=phenotype,
            frequency_response_mode=config.frequency_response_mode,
            rng=rng,
        )
    raise ContractViolationError(f"Unsupported engine_mode: {config.engine_mode!r}")


def build_actuator(config: ProtocolConfig) -> AbstractActuator:
    if config.actuator_mode == "normalized":
        return NormalizedActuator(config.actuator)
    if config.actuator_mode == "toy_resistive":
        return ToyResistiveActuator(config.actuator)
    raise ContractViolationError(f"Unsupported actuator_mode: {config.actuator_mode!r}")


class ClosedLoopEnvironment:
    """
    Privileged simulation orchestrator owning the Plant, Actuator, SafetySupervisor,
    and SensorPipeline.
    Controllers NEVER receive a reference to this class; the orchestrator passes
    a deep-copied `PublicObservation` to the controller and feeds the returned
    `ControlAction` into `ClosedLoopEnvironment.step()`.
    """

    def __init__(
        self,
        config: ProtocolConfig,
        scenario_key: CanonicalScenarioKey,
        local_episode_sequence: int,
        program_catalog: Optional[Mapping[str, ProgramSpec]] = None,
        rng: Optional[SemanticRNG] = None,
        ablate_impedance: bool = False,
        ablate_reports: bool = False,
    ) -> None:
        self._config = config
        self._scenario_key = scenario_key
        self._local_ep_seq = local_episode_sequence
        self._catalog: Dict[str, ProgramSpec] = dict(program_catalog or DEFAULT_PROGRAM_CATALOG)
        self._rng = rng or SemanticRNG(config.seeds.master_seed, scenario_key)
        self._ablate_impedance = ablate_impedance
        self._ablate_reports = ablate_reports

        self._plant = build_plant(config, scenario_key.phenotype, self._rng)
        self._actuator = build_actuator(config)
        self._supervisor = SafetySupervisor(config.supervisor, config.timing, self._catalog)
        self._sensors = SensorPipeline(config.timing, config.actuator, config.actuator_mode)

        self._step_k = 0
        self._active_program_id = "P00_OFF"
        self._saved_calibration: Optional[CalibrationRecord] = None

        # Emit initial step_k=0 observation under P00_OFF
        cq0 = self._plant.sample_contact_quality(0, self._rng)
        z_r0, z_i0 = self._sensors.measure_load_impedance(0, cq0, self._rng)
        exp0 = self._actuator.deliver(0, 0.0, self._catalog["P00_OFF"], cq0, z_r0)
        p_out0 = self._plant.current_output()
        self._current_obs = self._sensors.emit_observation(
            local_episode_sequence=self._local_ep_seq,
            step_k=0,
            true_latent_pain=p_out0.true_latent_pain,
            true_functional_impairment=p_out0.true_functional_impairment,
            query_burden=p_out0.query_burden,
            contact_quality=cq0,
            z_real_ohm=z_r0,
            z_imag_ohm=z_i0,
            active_program_id="P00_OFF",
            exposure=exp0,
            fault_latched=False,
            prompt_requested=False,
            prompt_id=None,
            rng=self._rng,
            ablate_impedance=self._ablate_impedance,
            ablate_reports=self._ablate_reports,
        )
        verify_public_observation_isolation(self._current_obs)

    @property
    def current_observation(self) -> PublicObservation:
        return copy.deepcopy(self._current_obs)

    @property
    def plant_output(self) -> PhysicalPlantOutput:
        return self._plant.current_output()

    @property
    def saved_calibration(self) -> Optional[CalibrationRecord]:
        return copy.deepcopy(self._saved_calibration)

    def set_saved_calibration(self, record: CalibrationRecord) -> None:
        self._saved_calibration = copy.deepcopy(record)

    def create_checkpoint(self, controller: AbstractController) -> SystemCheckpoint:
        if not self._plant.supports_checkpoint:
            raise ContractViolationError("Underlying plant engine does not support state checkpointing.")
        cal_rec = controller.get_calibration_record() or self._saved_calibration
        return SystemCheckpoint(
            step_k=self._step_k,
            active_program_id=self._active_program_id,
            plant_snapshot=self._plant.snapshot(),
            actuator_snapshot=self._actuator.snapshot(),
            supervisor_snapshot=self._supervisor.snapshot(),
            sensor_snapshot=self._sensors.snapshot(),
            current_observation=copy.deepcopy(self._current_obs),
            controller_snapshot=controller.snapshot(),
            calibration_record=copy.deepcopy(cal_rec) if cal_rec is not None else None,
        )

    def restore_checkpoint(
        self,
        checkpoint: SystemCheckpoint,
        controller: Optional[AbstractController] = None,
        rng_override: Optional[SemanticRNG] = None,
    ) -> None:
        self._step_k = checkpoint.step_k
        self._active_program_id = checkpoint.active_program_id
        self._plant.restore(checkpoint.plant_snapshot)
        self._actuator.restore(checkpoint.actuator_snapshot)
        self._supervisor.restore(checkpoint.supervisor_snapshot)
        self._sensors.restore(checkpoint.sensor_snapshot)
        self._current_obs = copy.deepcopy(checkpoint.current_observation)
        self._saved_calibration = copy.deepcopy(checkpoint.calibration_record)
        if rng_override is not None:
            self._rng = rng_override
        if controller is not None:
            controller.restore(checkpoint.controller_snapshot)

    def _compute_loss(
        self,
        supervision: SupervisionDecision,
        exposure: DeliveredExposure,
        plant_out: PhysicalPlantOutput,
    ) -> StepLossBreakdown:
        lw = self._config.loss_weights
        dt_norm = exposure.dt_sec / 30.0

        pain_l = lw.w_latent_pain * plant_out.true_latent_pain * dt_norm
        func_l = lw.w_functional_impairment * plant_out.true_functional_impairment * dt_norm
        effort_l = lw.w_stimulation_effort * exposure.stimulation_effort
        query_l = (
            lw.w_query_burden_base * (1.0 + 2.0 * plant_out.query_burden)
            if supervision.feedback_requested
            else 0.0
        )
        clinical_loss = pain_l + func_l + effort_l + query_l

        viol_l = lw.w_proposal_violation if supervision.proposal_violated else 0.0
        fault_del_l = (
            lw.w_fault_stimulation * exposure.requested_intensity
            if exposure.compliance_limited
            else 0.0
        )
        worsen_l = (
            lw.w_worsening_escalation * exposure.delivered_intensity
            if plant_out.delayed_sensitization > 1.10
            else 0.0
        )
        safety_loss = viol_l + fault_del_l + worsen_l

        return StepLossBreakdown(
            pain_loss=pain_l,
            functional_loss=func_l,
            effort_loss=effort_l,
            query_loss=query_l,
            clinical_loss=clinical_loss,
            proposal_violation_loss=viol_l,
            fault_delivery_loss=fault_del_l,
            worsening_escalation_loss=worsen_l,
            safety_loss=safety_loss,
            total_loss=clinical_loss + safety_loss,
            proposal_violated=supervision.proposal_violated,
            violation_reason=supervision.violation_reason,
            true_latent_pain=plant_out.true_latent_pain,
            true_functional_impairment=plant_out.true_functional_impairment,
            mechanistic_wdr_hz=plant_out.mechanistic_wdr_hz,
        )

    def step(
        self,
        proposed_action: ControlAction,
        controller_belief: Optional[Dict[str, Any]] = None,
    ) -> StepExecutionRecord:
        obs_before = copy.deepcopy(self._current_obs)
        k = self._step_k
        dt_sec = self._config.timing.macro_step_dt_sec

        # 1. Safety Supervisor evaluates proposed action against accessible telemetry
        supervision = self._supervisor.evaluate_proposal(proposed_action, obs_before)
        approved_spec = supervision.approved_program
        self._active_program_id = approved_spec.program_id

        # 2. Sample physical pad contact and load impedance at step k
        cq = self._plant.sample_contact_quality(k, self._rng)
        z_real, z_imag = self._sensors.measure_load_impedance(k, cq, self._rng)

        # 3. Virtual Actuator computes actual delivered exposure
        exposure = self._actuator.deliver(
            step_k=k,
            dt_sec=dt_sec,
            approved_program=approved_spec,
            contact_quality=cq,
            load_impedance_real_ohm=z_real,
        )

        # 4. Plant advances state strictly using DeliveredExposure
        plant_out = self._plant.step(
            exposure=exposure,
            query_requested=supervision.feedback_requested,
            rng=self._rng,
        )
        self._step_k += 1

        # 5. Sensor Pipeline emits causal PublicObservation at step k + 1
        obs_after = self._sensors.emit_observation(
            local_episode_sequence=self._local_ep_seq,
            step_k=self._step_k,
            true_latent_pain=plant_out.true_latent_pain,
            true_functional_impairment=plant_out.true_functional_impairment,
            query_burden=plant_out.query_burden,
            contact_quality=cq,
            z_real_ohm=z_real,
            z_imag_ohm=z_imag,
            active_program_id=self._active_program_id,
            exposure=exposure,
            fault_latched=supervision.fault_latched_after,
            prompt_requested=supervision.feedback_requested,
            prompt_id=supervision.prompt_id,
            rng=self._rng,
            ablate_impedance=self._ablate_impedance,
            ablate_reports=self._ablate_reports,
        )
        verify_public_observation_isolation(obs_after)
        self._current_obs = obs_after

        # 6. Privileged Evaluator computes step loss breakdown
        loss = self._compute_loss(supervision, exposure, plant_out)

        return StepExecutionRecord(
            step_k=k,
            time_sec=obs_before.time_sec,
            observation_before=obs_before,
            proposed_action=proposed_action,
            supervision=supervision,
            exposure=exposure,
            plant_output=plant_out,
            observation_after=obs_after,
            loss=loss,
            controller_belief=copy.deepcopy(controller_belief),
        )


class SubprocessControllerWrapper(AbstractController):
    """
    Release-mode process boundary wrapper (`isolation_mode = 'release_subprocess'`).
    Spawns a fresh Python worker process with zero inherited plant/evaluator memory and
    communicates strictly via serialized JSON lines over stdin/stdout.
    """

    def __init__(self, inner_controller_factory_spec: str, name: str) -> None:
        self._factory_spec = inner_controller_factory_spec
        self.name = name
        self._proc: Optional[subprocess.Popen[str]] = None
        self._last_snapshot: Dict[str, Any] = {}

    def _ensure_proc(self) -> subprocess.Popen[str]:
        if self._proc is None or self._proc.poll() is not None:
            import os
            from pathlib import Path

            src_dir = str(Path(__file__).resolve().parents[2])
            env = dict(os.environ)
            env["PYTHONPATH"] = src_dir + (os.pathsep + env["PYTHONPATH"] if "PYTHONPATH" in env else "")
            self._proc = subprocess.Popen(
                [sys.executable, "-m", "neuroloop.orchestrator.worker_main", self._factory_spec],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        return self._proc

    def _rpc(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        proc = self._ensure_proc()
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps(payload, allow_nan=False) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        if not line:
            err = proc.stderr.read() if proc.stderr else ""
            raise IsolationViolationError(f"Subprocess controller worker terminated unexpectedly: {err}")
        return json.loads(line)

    def reset(self, initial_obs: PublicObservation) -> None:
        resp = self._rpc({"cmd": "reset", "obs": initial_obs.to_dict()})
        self._last_snapshot = resp["snapshot"]

    def act(self, obs: PublicObservation) -> ControlAction:
        resp = self._rpc({"cmd": "act", "obs": obs.to_dict()})
        self._last_snapshot = resp["snapshot"]
        act_d = resp["action"]
        return ControlAction(
            stimulation=StimulationCommand(act_d["stimulation"]),
            feedback=FeedbackCommand(act_d["feedback"]),
            target_program_id=act_d["target_program_id"],
            prompt_id=act_d["prompt_id"],
            observation_sequence=int(act_d["observation_sequence"]),
        )

    def snapshot(self) -> Dict[str, Any]:
        resp = self._rpc({"cmd": "snapshot"})
        self._last_snapshot = resp["snapshot"]
        return copy.deepcopy(self._last_snapshot)

    def restore(self, state: Mapping[str, Any]) -> None:
        self._last_snapshot = dict(state)
        self._rpc({"cmd": "restore", "state": self._last_snapshot})

    def close(self) -> None:
        if self._proc is not None:
            if self._proc.poll() is None:
                try:
                    if self._proc.stdin is not None:
                        self._proc.stdin.write(json.dumps({"cmd": "exit"}) + "\n")
                        self._proc.stdin.flush()
                    self._proc.wait(timeout=2.0)
                except Exception:
                    self._proc.kill()
            for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        self._proc = None

    def __del__(self) -> None:
        self.close()
