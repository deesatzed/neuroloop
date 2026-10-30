"""
Virtual Actuator stage mapping supervisor-approved ProgramSpec and physical/normalized
contact state into actual DeliveredExposure.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from neuroloop.config import ActuatorConfig
from neuroloop.contracts import (
    ContractViolationError,
    DeliveredExposure,
    DeliveryStatus,
    ProgramSpec,
    require_range,
)


@dataclass
class ActuatorState:
    cumulative_effort: float = 0.0
    partial_delivery_steps: int = 0
    fault_delivery_steps: int = 0


class AbstractActuator(ABC):
    """Base interface for virtual actuators."""

    def __init__(self, cfg: ActuatorConfig) -> None:
        self._cfg = cfg
        self._state = ActuatorState()

    def snapshot(self) -> ActuatorState:
        return ActuatorState(
            cumulative_effort=self._state.cumulative_effort,
            partial_delivery_steps=self._state.partial_delivery_steps,
            fault_delivery_steps=self._state.fault_delivery_steps,
        )

    def restore(self, state: ActuatorState) -> None:
        self._state = ActuatorState(
            cumulative_effort=state.cumulative_effort,
            partial_delivery_steps=state.partial_delivery_steps,
            fault_delivery_steps=state.fault_delivery_steps,
        )

    @abstractmethod
    def deliver(
        self,
        step_k: int,
        dt_sec: float,
        approved_program: ProgramSpec,
        contact_quality: float,
        load_impedance_real_ohm: float,
    ) -> DeliveredExposure:
        pass


class NormalizedActuator(AbstractActuator):
    """
    MVP Normalized Actuator:
    Uses dimensionless exposure and explicitly synthetic contact constraints.
    Does not invent clinical mA or voltage numbers (`effective_current_ma=None`, `output_voltage_v=None`).
    """

    FAULT_CONTACT_THRESHOLD = 0.32
    PARTIAL_CONTACT_THRESHOLD = 0.70

    def deliver(
        self,
        step_k: int,
        dt_sec: float,
        approved_program: ProgramSpec,
        contact_quality: float,
        load_impedance_real_ohm: float,
    ) -> DeliveredExposure:
        if not isinstance(approved_program, ProgramSpec):
            raise ContractViolationError("approved_program must be a ProgramSpec.")
        cq = require_range(contact_quality, "contact_quality", 0.0, 1.0)
        req_inten = approved_program.normalized_intensity

        if req_inten <= 0.0:
            return DeliveredExposure(
                step_k=step_k,
                dt_sec=dt_sec,
                delivered_intensity=0.0,
                requested_intensity=0.0,
                effective_current_ma=None,
                output_voltage_v=None,
                contact_factor=cq,
                delivery_status=DeliveryStatus.OFF,
                delivery_confirmed=True,
                compliance_limited=False,
                waveform=approved_program.waveform,
                stimulation_effort=0.0,
            )

        if cq < self.FAULT_CONTACT_THRESHOLD or load_impedance_real_ohm > 35_000.0:
            # Severe pad lift-off / contact fault: compliance limit prevents full delivery
            delivered_inten = req_inten * (cq * 0.5)
            status = DeliveryStatus.FAULT
            confirmed = False
            compliance_lim = True
            self._state.fault_delivery_steps += 1
        elif cq < self.PARTIAL_CONTACT_THRESHOLD:
            delivered_inten = req_inten * cq
            status = DeliveryStatus.PARTIAL
            confirmed = True
            compliance_lim = False
            self._state.partial_delivery_steps += 1
        else:
            delivered_inten = req_inten * cq
            status = DeliveryStatus.FULL
            confirmed = True
            compliance_lim = False

        # Dimensionless stimulation effort scales with delivered intensity squared
        effort = (delivered_inten ** 2) * (dt_sec / 30.0)
        self._state.cumulative_effort += effort

        return DeliveredExposure(
            step_k=step_k,
            dt_sec=dt_sec,
            delivered_intensity=delivered_inten,
            requested_intensity=req_inten,
            effective_current_ma=None,
            output_voltage_v=None,
            contact_factor=cq,
            delivery_status=status,
            delivery_confirmed=confirmed,
            compliance_limited=compliance_lim,
            waveform=approved_program.waveform,
            stimulation_effort=effort,
        )


class ToyResistiveActuator(AbstractActuator):
    """
    Explicitly labeled NON-CLINICAL resistive load fixture:
      I_cmd = I_max * requested_intensity
      I_del = min(I_cmd, V_max / R_load)
      V_del = I_del * R_load
      delivered_intensity = (I_del / I_max) * contact_quality
    Guarantees 100% mathematical consistency between voltage compliance clamping,
    delivered current, and biological exposure.
    """

    def deliver(
        self,
        step_k: int,
        dt_sec: float,
        approved_program: ProgramSpec,
        contact_quality: float,
        load_impedance_real_ohm: float,
    ) -> DeliveredExposure:
        if not isinstance(approved_program, ProgramSpec):
            raise ContractViolationError("approved_program must be a ProgramSpec.")
        cq = require_range(contact_quality, "contact_quality", 0.0, 1.0)
        r_ohm = require_range(load_impedance_real_ohm, "load_impedance_real_ohm", 1.0, 1e7)
        req_inten = approved_program.normalized_intensity

        if req_inten <= 0.0:
            return DeliveredExposure(
                step_k=step_k,
                dt_sec=dt_sec,
                delivered_intensity=0.0,
                requested_intensity=0.0,
                effective_current_ma=0.0,
                output_voltage_v=0.0,
                contact_factor=cq,
                delivery_status=DeliveryStatus.OFF,
                delivery_confirmed=True,
                compliance_limited=False,
                waveform=approved_program.waveform,
                stimulation_effort=0.0,
            )

        i_max_ma = self._cfg.max_current_ma
        v_max_v = self._cfg.compliance_voltage_v
        i_cmd_ma = i_max_ma * req_inten
        max_deliverable_ma = (v_max_v / r_ohm) * 1000.0
        i_del_ma = min(i_cmd_ma, max_deliverable_ma)
        v_del_v = (i_del_ma * 1e-3) * r_ohm

        compliance_lim = i_del_ma < (i_cmd_ma - 1e-6)
        delivered_fraction = (i_del_ma / i_max_ma) * cq

        if compliance_lim:
            if i_del_ma < 0.35 * i_cmd_ma or cq < 0.32:
                status = DeliveryStatus.FAULT
                confirmed = False
                self._state.fault_delivery_steps += 1
            else:
                status = DeliveryStatus.PARTIAL
                confirmed = True
                self._state.partial_delivery_steps += 1
        else:
            status = DeliveryStatus.FULL if cq >= 0.70 else DeliveryStatus.PARTIAL
            confirmed = True

        effort = (delivered_fraction ** 2) * (dt_sec / 30.0)
        self._state.cumulative_effort += effort

        return DeliveredExposure(
            step_k=step_k,
            dt_sec=dt_sec,
            delivered_intensity=delivered_fraction,
            requested_intensity=req_inten,
            effective_current_ma=round(i_del_ma, 6),
            output_voltage_v=round(v_del_v, 4),
            contact_factor=cq,
            delivery_status=status,
            delivery_confirmed=confirmed,
            compliance_limited=compliance_lim,
            waveform=approved_program.waveform,
            stimulation_effort=effort,
        )
