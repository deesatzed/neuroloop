"""
Stable canonical scenario identifiers and counter-based semantic random streams.
Never calls Python's process-salted built-in `hash()`.
"""

from __future__ import annotations

import hashlib
import math
import struct
from dataclasses import dataclass
from typing import Sequence, TypeVar

from neuroloop.contracts import ContractViolationError

T = TypeVar("T")

ALLOWED_NOISE_SOURCES = frozenset({
    "patient_params",
    "env_disturbance",
    "contact_dynamics",
    "sensor_noise",
    "patient_reporting",
    "controller_explore",
    "calibration_order",
    "mechanistic_synaptic",
})


@dataclass(frozen=True)
class CanonicalScenarioKey:
    """
    Process-invariant canonical scenario identifier.
    """
    protocol_namespace: str
    phenotype: str
    episode_index: int
    scenario_offset: int
    scenario_digest: str
    scenario_uint64: int

    @classmethod
    def create(
        cls,
        protocol_namespace: str,
        phenotype: str,
        episode_index: int,
        scenario_offset: int = 0,
    ) -> CanonicalScenarioKey:
        if not protocol_namespace or not phenotype:
            raise ContractViolationError("protocol_namespace and phenotype must be non-empty.")
        if episode_index < 0 or scenario_offset < 0:
            raise ContractViolationError("episode_index and scenario_offset must be >= 0.")
        canonical_str = f"neuroloop_v0_4|{protocol_namespace}|{phenotype}|ep:{episode_index}|off:{scenario_offset}"
        digest_bytes = hashlib.sha256(canonical_str.encode("utf-8")).digest()
        hex_digest = digest_bytes.hex()[:24]
        uint64_val = struct.unpack("<Q", digest_bytes[:8])[0]
        return cls(
            protocol_namespace=protocol_namespace,
            phenotype=phenotype,
            episode_index=episode_index,
            scenario_offset=scenario_offset,
            scenario_digest=hex_digest,
            scenario_uint64=uint64_val,
        )


class SemanticRNG:
    """
    Stateless counter-based pseudorandom stream indexed by:
      (master_seed, protocol_namespace, scenario_digest, source, time_index, entity_id, draw_index, audit_replicate)
    Guarantees:
      1. 100% invariance across PYTHONHASHSEED, execution order, and parallel workers.
      2. Action-independent background streams (where entity_id="env") remain bitwise identical
         across different controllers and counterfactual branches.
      3. Audit replicates (audit_replicate > 0) fork future stochastic draws cleanly after the audit step
         while preserving identical past trajectories.
    """

    def __init__(
        self,
        master_seed: int,
        scenario_key: CanonicalScenarioKey,
        audit_replicate: int = 0,
        fork_after_step: int = -1,
    ) -> None:
        self._master_seed = int(master_seed)
        self._scenario_key = scenario_key
        self._audit_replicate = int(audit_replicate)
        self._fork_after_step = int(fork_after_step)

    @property
    def scenario_key(self) -> CanonicalScenarioKey:
        return self._scenario_key

    @property
    def audit_replicate(self) -> int:
        return self._audit_replicate

    def fork_replicate(self, audit_replicate: int, fork_after_step: int) -> SemanticRNG:
        """Creates a counterfactual RNG that shares history <= fork_after_step and branches on replicate > 0 after."""
        return SemanticRNG(
            master_seed=self._master_seed,
            scenario_key=self._scenario_key,
            audit_replicate=audit_replicate,
            fork_after_step=fork_after_step,
        )

    def _effective_replicate(self, time_index: int) -> int:
        if self._fork_after_step >= 0 and time_index > self._fork_after_step:
            return self._audit_replicate
        return 0

    def uniform(
        self,
        source: str,
        time_index: int,
        entity_id: str = "env",
        draw_index: int = 0,
    ) -> float:
        if source not in ALLOWED_NOISE_SOURCES:
            raise ContractViolationError(f"Undeclared semantic noise source: {source!r}")
        rep = self._effective_replicate(time_index)
        payload = (
            f"{self._master_seed}|{self._scenario_key.protocol_namespace}|"
            f"{self._scenario_key.scenario_digest}|{source}|t:{int(time_index)}|"
            f"e:{entity_id}|d:{int(draw_index)}|r:{rep}"
        ).encode("utf-8")
        digest = hashlib.sha256(payload).digest()
        uint64_val = struct.unpack("<Q", digest[:8])[0]
        return (uint64_val + 0.5) / (2**64)

    def normal(
        self,
        source: str,
        time_index: int,
        mean: float = 0.0,
        std: float = 1.0,
        entity_id: str = "env",
        draw_index: int = 0,
    ) -> float:
        u1 = max(1e-12, min(1.0 - 1e-12, self.uniform(source, time_index, entity_id, draw_index * 2)))
        u2 = self.uniform(source, time_index, entity_id, draw_index * 2 + 1)
        z0 = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
        return mean + std * z0

    def permutation(
        self,
        items: Sequence[T],
        source: str,
        time_index: int,
        entity_id: str = "env",
    ) -> list[T]:
        """Deterministic Fisher-Yates shuffle driven by semantic counter draws."""
        arr = list(items)
        n = len(arr)
        for i in range(n - 1, 0, -1):
            u = self.uniform(source, time_index, entity_id=entity_id, draw_index=i)
            j = int(u * (i + 1))
            arr[i], arr[j] = arr[j], arr[i]
        return arr
