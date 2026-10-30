"""
Foundational helper repairs referenced in NeuroLoop_Executed_Audit.md Section 9:
- Stable canonical scenario IDs (invariant to PYTHONHASHSEED)
- Explicit zero-pain vs missing (`None`) handling
- Orthogonal action semantics (`HOLD | SET | OFF` x `NONE | REQUEST`)
- Exact empirical CVaR with fractional quantile-boundary mass
- Consistent non-clinical resistive fixture actuator (`I_del = min(I_cmd, V_max / R)`)
"""

from __future__ import annotations

from typing import Optional, Sequence

from neuroloop.actuator import ToyResistiveActuator
from neuroloop.contracts import (
    ContractViolationError,
    ControlAction,
    DeliveredExposure,
    DeliveryStatus,
    FeedbackCommand,
    ProgramSpec,
    StimulationCommand,
    WaveformSpec,
    render_pulse_events,
)
from neuroloop.evaluation import compute_exact_cvar
from neuroloop.randomness import CanonicalScenarioKey, SemanticRNG


def canonical_scenario_id(
    protocol_namespace: str,
    phenotype: str,
    episode_index: int,
    scenario_offset: int = 0,
) -> CanonicalScenarioKey:
    return CanonicalScenarioKey.create(
        protocol_namespace=protocol_namespace,
        phenotype=phenotype,
        episode_index=episode_index,
        scenario_offset=scenario_offset,
    )


def resolve_pain_report(reported_pain: Optional[int], default_if_missing: int = 6) -> int:
    """Preserves legitimate zero pain (`0`), substituting default ONLY when `reported_pain is None`."""
    if reported_pain is None:
        return int(default_if_missing)
    if isinstance(reported_pain, bool) or not isinstance(reported_pain, int):
        raise ContractViolationError(f"Pain report must be int or None, got {type(reported_pain).__name__}")
    if not (0 <= reported_pain <= 10):
        raise ContractViolationError(f"Pain report {reported_pain} out of range [0, 10]")
    return reported_pain


def compute_empirical_cvar(losses: Sequence[float], alpha: float = 0.90) -> float:
    """Exact empirical CVaR with fractional boundary mass."""
    return compute_exact_cvar(losses, alpha=alpha)


__all__ = [
    "CanonicalScenarioKey",
    "ContractViolationError",
    "ControlAction",
    "DeliveredExposure",
    "DeliveryStatus",
    "FeedbackCommand",
    "ProgramSpec",
    "SemanticRNG",
    "StimulationCommand",
    "ToyResistiveActuator",
    "WaveformSpec",
    "canonical_scenario_id",
    "compute_empirical_cvar",
    "compute_exact_cvar",
    "render_pulse_events",
    "resolve_pain_report",
]
