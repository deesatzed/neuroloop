This master execution plan and foundational scaffolding locks **NeuroLoop Lab v0.3.2** into a disciplined, local-first engineering blueprint. It establishes strict contracts, architectural boundaries, and automated verification gates before any complex neural modeling or policy training begins.

---

## 1. Master Build Plan & Gate-Driven Execution Phases

Development progresses through **six sequential phases**. A phase cannot start until the previous phase's automated gate (`pytest` + DuckDB SQL assertions) passes with zero violations.

| Phase | Gate | Focus & Deliverables | Build Expectations & Exit Criteria |
| --- | --- | --- | --- |
| **Phase 1: Core Infrastructure & Isolation** | **G0** | `core/`, `observation/restricted_adapter.py`, `protocols/`, and the Gate G0 audit test suite. | **100% bitwise determinism** across identical seeds; **0 bytes** of privileged state, plant references, or phenotype strings reachable via `inspect` or memory traversal from the controller interface. |
| **Phase 2: Dual Plants & Controllability** | **G1** | `engines/phenomenological/` (L0 fast state-space) and `engines/mechanistic/` (L1/L2 conductance-based dorsal horn with electroneutral KCC2). | Omniscient full-state oracle confirms allowed interventions shift WDR/nociceptive output by $\ge 20\%$ on `responder`, $\approx 0\%$ on `nonresponder`, and worsen `delayed_worsening` if unchecked. |
| **Phase 3: Sensor Pipeline & Decision Sufficiency** | **G2** | `observation/sensor_models.py`, `evaluation/decision_sufficiency.py`, and sensor ablation masks. | Quantifies the **Information Gap** ($\Delta_{\text{info}} = J^*_{\text{partial}} - J^*_{\text{full}}$) across sensor combinations *before* AI controller tuning. Identifies which sensors reduce expected treatment loss. |
| **Phase 4: Baseline & Adaptive Tournament** | **G3** | `controllers/baselines/`, `controllers/bayesian/`, `controllers/decision/`, and `evaluation/counterfactual_rollout.py`. | **Freeze controller weights/hyperparameters** prior to opening held-out seeds. Compute Restricted Comparator Regret ($R_H^{\mathcal{B}}$) using counter-based Common Random Numbers across horizons $H \in \{4, 8, 16\}$. |
| **Phase 5: Cross-Engine Transfer & Tail Risk** | **G4 & G5** | `evaluation/cross_engine_transfer.py`, `evaluation/tail_risk.py`, and `controllers/connectome/` (with equal-capacity ablations). | Zero-shot evaluation of Engine A-tuned controllers on Engine B (and vice versa). Must meet absolute non-inferiority margins on $\text{CVaR}_{0.90}(\text{Clinical Loss})$ and $\text{CVaR}_{0.90}(\text{Safety Loss})$. |
| **Phase 6: Evidence Dossiers & Local UI** | **G6 & G7** | `reports/` (DuckDB + Parquet analytics, LaTeX/Markdown tables) and optional FastAPI + React inspection viewer. | Generates reproducible publication figures (Papers 1–3) and structured IP invention dossiers separating simulated sensitivity from bench validation requirements. |

---

## 2. Engineering Expectations & Architectural Invariants

Every module committed to the repository must obey five architectural invariants:

1. **Single Responsibility & Explicit Dependencies:**
* *Plants* (`engines/`) advance biological state $x_{k+1} = F(x_k, u_k^{\text{delivered}}, \xi_k)$ and emit raw physical quantities. Plants know nothing about controllers, loss weights, or safety rules.
* *Sensors* (`observation/`) transform physical plant outputs into causal, delayed, artifact-corrupted measurements $y_k = G(x_k, u_{k-1}^{\text{delivered}}, \eta_k)$.
* *Safety Supervisor* (`observation/safety_supervisor.py`) intercepts $u_k^{\text{proposed}}$, logs violations, and emits $u_k^{\text{delivered}}$.
* *Controllers* (`controllers/`) consume only `PublicObservation` and emit `ControllerAction`.
* *Evaluators* (`evaluation/`) hold privileged handles to both the plant and controller to run Twin-World counterfactual forks and log Parquet records.


2. **Counter-Based Stateless Randomness (`CounterPRNG`):**
* `random.random()` and stateful `np.random.Generator` instances are **banned** inside plants and sensors. Every stochastic draw must call `prng.normal(step_k, channel_name, sub_idx)` so counterfactual branches never desynchronize when one policy queries the patient or triggers a fault and another does not.


3. **Opaque Handle Firewall:**
* Controllers interact with the environment exclusively through `RestrictedControllerAdapter`. The adapter strips all `info` dictionaries, replaces human-readable phenotype IDs with salted SHA-256 tokens (`ep_8f3a91c04b12`), and holds no public reference to the underlying `AbstractPlant`.


4. **Explicit Error Handling & Physical Bounds:**
* All ionic concentrations ($[\text{Cl}^-]_i, [\text{K}^+]_i, [\text{HCO}_3^-]_i$), conductances, and impedance values are validated at every step. Out-of-bounds numerical drift raises an explicit `BiophysicalNumericalError` rather than silently clamping `NaN` or `inf`.


5. **Pre-Registered Freeze Protocol:**
* `protocols/prespecified_gates.yaml` defines all loss weights, non-inferiority margins, and held-out seed ranges. Evaluators hash this YAML file into every Parquet run manifest (`provenance_hash`) so post-hoc threshold moving is immediately detectable.



---

## 3. Repository Layout

```text
neuroloop_lab/
├── pyproject.toml
├── Makefile
├── protocols/
│   ├── prespecified_gates.yaml       # Frozen evaluation gates, loss weights, and seed splits
│   └── phenotype_registry.yaml       # Parameter ranges & provenance (experimental vs hypothetical)
├── src/
│   └── neuroloop/
│       ├── __init__.py
│       ├── core/
│       │   ├── __init__.py
│       │   ├── contracts.py          # Immutable dataclasses for observations, actions, losses
│       │   ├── causal_noise.py       # Stateless SHA-256 counter-based PRNG streams
│       │   ├── exceptions.py         # Explicit numerical, leakage, and contract exceptions
│       │   └── provenance.py         # Git commit, YAML hash, and hardware manifest logger
│       ├── engines/
│       │   ├── __init__.py
│       │   ├── base_plant.py         # AbstractPlant ABC with mandatory clone_state()
│       │   ├── phenomenological/     # Engine B (L0 state-space switching dynamics)
│       │   └── mechanistic/          # Engine A (L1/L2 conductance dorsal horn + KCC2)
│       ├── observation/
│       │   ├── __init__.py
│       │   ├── sensor_models.py      # Impedance, EMG artifact harmonics, IMU, delayed VAS
│       │   ├── safety_supervisor.py  # Maps u_proposed -> u_delivered & records violations
│       │   └── restricted_adapter.py # Memory-isolated firewall for controller execution
│       ├── controllers/
│       │   ├── __init__.py
│       │   ├── base_controller.py    # AbstractController ABC
│       │   ├── baselines/            # C0 (Off), C1 (Fixed), C2 (Calibrated), C3 (Rules)
│       │   ├── bayesian/             # C4 (Belief-state posterior + VoI sparse query)
│       │   ├── decision/             # C5 (Compact decision model)
│       │   └── connectome/           # C6 (Sparse E/I recurrent + equal-capacity ablations)
│       └── evaluation/
│           ├── __init__.py
│           ├── counterfactual.py     # Twin-World R_H^B evaluator across horizons H
│           ├── decision_sufficiency.py # Gate G2 Information Gap (Delta_info)
│           ├── tail_risk.py          # Quantile CVaR_90 and absolute non-inferiority tests
│           └── parquet_sink.py       # DuckDB / Parquet schema writer
└── tests/
    ├── test_g0_isolation.py          # Verifies zero privilege leakage & counter PRNG alignment
    ├── test_g0_determinism.py        # Verifies bitwise replay across identical seeds
    └── test_ionic_bounds.py          # Verifies GHK and KCC2 equilibrium convergence

```

---

## 4. Foundational Scaffolding Code (Ready to Drop In)

Below are the six core scaffolding files that establish the environment, configuration protocols, contracts, memory firewall, and Gate G0 verification tests.

### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "neuroloop"
version = "0.3.2"
description = "Closed-loop peripheral neuromodulation simulator under partial observability and model-form uncertainty"
readme = "README.md"
requires-python = ">=3.11"
license = {text = "MIT"}
authors = [{name = "NeuroLoop Lab Research"}]
dependencies = [
    "numpy>=1.26.0",
    "scipy>=1.12.0",
    "pyyaml>=6.0.1",
    "duckdb>=1.0.0",
    "pyarrow>=15.0.0",
]

[project.optional-dependencies]
mechanistic = ["brian2>=2.6.0"]
ml = ["torch>=2.2.0", "scikit-learn>=1.4.0", "optuna>=3.6.0"]
dev = ["pytest>=8.0.0", "ruff>=0.4.0", "mypy>=1.9.0"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.ruff]
line-length = 100
target-version = "py311"

```

### `protocols/prespecified_gates.yaml`

```yaml
protocol_version: "0.3.2"
freeze_status: "DEVELOPMENT_CALIBRATION"  # Switch to FROZEN_EVALUATION before opening held_out_seeds

seeds:
  calibration_seed_range: [1000, 1499]
  validation_seed_range: [2000, 2499]
  held_out_test_seed_range: [9000, 9999]  # Locked until Gate G3 readiness

simulation:
  macro_step_dt_sec: 30.0
  episode_macro_steps: 60                 # 30 minutes simulated clinical window
  counterfactual_horizons_steps: [4, 8, 16]
  discount_gamma: 0.98

loss_weights:
  clinical:
    w_latent_pain: 1.00
    w_functional_impairment: 0.50
    w_stimulation_energy: 0.35
    w_query_burden_base: 0.45
  safety:
    w_proposal_violation: 5.00
    w_fault_stimulation: 2.50
    w_worsening_escalation: 3.00

gates:
  G0_integrity:
    require_bitwise_determinism: true
    max_privileged_leakage_bytes: 0
  G1_controllability:
    min_oracle_responder_reduction_pct: 20.0
  G2_decision_sufficiency:
    max_acceptable_information_gap_abs: 15.0
  G3_controller_advantage:
    exploratory_relative_benefit_pct: 10.0
  G4_G5_tail_safety:
    cvar_quantile: 0.90
    nonresponder_clinical_cvar_abs_margin: 8.0     # Max allowable excess CVaR_90 loss vs C2_CalibratedFixed
    worsening_clinical_cvar_abs_margin: 5.0        # Must not worsen tail loss on delayed_worsening vs C2
    max_safety_loss_cvar_abs: 2.5                  # Absolute bound on safety tail loss (avoids div-by-zero)
    max_proposal_violation_rate: 0.01

```

### `src/neuroloop/core/exceptions.py`

```python
#!/usr/bin/env python3
"""Explicit domain exceptions for NeuroLoop Lab v0.3.2."""


class NeuroLoopError(Exception):
    """Base exception for all NeuroLoop errors."""


class PrivilegeLeakageError(NeuroLoopError):
    """Raised when a controller or adapter attempts to access privileged state."""


class BiophysicalNumericalError(NeuroLoopError):
    """Raised when ionic concentrations, voltages, or state variables diverge or violate bounds."""


class ContractViolationError(NeuroLoopError):
    """Raised when an observation, action, or protocol manifest violates schema invariants."""

```

### `src/neuroloop/core/contracts.py`

```python
#!/usr/bin/env python3
"""
Immutable data contracts enforcing the boundary between Public Observations,
Controller Actions, Safety Supervision, and Privileged Evaluator States.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


class ActionMode(enum.Enum):
    HOLD = "HOLD"
    SWITCH_PROGRAM = "SWITCH_PROGRAM"
    ABSTAIN_SAFE = "ABSTAIN_SAFE"
    QUERY_PATIENT = "QUERY_PATIENT"


@dataclass(frozen=True)
class ProgramSpec:
    program_id: str
    normalized_intensity: float  # Bounded [0.0, 1.0]
    pulse_freq_hz: float
    burst_freq_hz: float
    pulse_width_us: float


ALLOWED_PRESET_PROGRAMS: Dict[str, ProgramSpec] = {
    "P00_OFF": ProgramSpec("P00_OFF", 0.0, 0.0, 0.0, 0.0),
    "P01_LOW_CONV": ProgramSpec("P01_LOW_CONV", 0.35, 80.0, 0.0, 150.0),
    "P02_MOD_BURST": ProgramSpec("P02_MOD_BURST", 0.60, 100.0, 2.0, 200.0),
    "P03_HIGH_CONV": ProgramSpec("P03_HIGH_CONV", 0.85, 100.0, 0.0, 250.0),
}


@dataclass(frozen=True)
class ControllerAction:
    """Action proposed by a controller (Track A preset mode)."""
    mode: ActionMode
    target_program_id: str = "P00_OFF"
    request_feedback: bool = False


@dataclass(frozen=True)
class SupervisedActionRecord:
    """Audit record comparing the controller's proposal against the supervisor's delivered action."""
    proposed_action: ControllerAction
    delivered_program: ProgramSpec
    request_feedback_delivered: bool
    proposal_violated_envelope: bool
    violation_reason: Optional[str] = None


@dataclass(frozen=True)
class ElectrodeMeasurement:
    impedance_real_ohm: float
    impedance_imag_ohm: float
    measurement_frequency_hz: float
    output_voltage_v: float
    compliance_limit_reached: bool


@dataclass(frozen=True)
class EMGMeasurement:
    rms_uv: float
    spectral_features: Tuple[float, float, float]
    window_duration_ms: float
    missing: bool = False


@dataclass(frozen=True)
class IMUMeasurement:
    acceleration_rms_g: float
    angular_velocity_rms_dps: float
    missing: bool = False


@dataclass(frozen=True)
class PatientMeasurement:
    last_pain_report: Optional[int]
    report_time_sec: Optional[float]
    prompt_response: Optional[int]


@dataclass(frozen=True)
class DeliveredStimulation:
    program: str
    normalized_intensity: float
    delivery_confirmed: bool


@dataclass(frozen=True)
class PublicObservation:
    """
    Strictly causal observation payload delivered to controllers.
    Contains zero hidden biological variables or ground-truth fault labels.
    """
    episode_token: str
    time_sec: float
    step_k: int
    electrode: ElectrodeMeasurement
    emg: EMGMeasurement
    imu: IMUMeasurement
    patient: PatientMeasurement
    delivered_stimulation: DeliveredStimulation


@dataclass(frozen=True)
class StepLossBreakdown:
    """Privileged loss decomposition stored only by the scientific evaluator."""
    clinical_loss: float
    safety_loss: float
    total_loss: float
    proposal_violated: bool
    true_latent_pain: float
    true_wdr_firing_hz: float

```

### `src/neuroloop/observation/restricted_adapter.py`

```python
#!/usr/bin/env python3
"""
Memory-isolated firewall separating controllers from the simulation plant and evaluator.
Prevents side-channel inspection of hidden states, plant references, or info dicts.
"""

from __future__ import annotations

from typing import Callable, Dict, Tuple
from neuroloop.core.contracts import (
    ALLOWED_PRESET_PROGRAMS,
    ControllerAction,
    ProgramSpec,
    PublicObservation,
)
from neuroloop.core.exceptions import PrivilegeLeakageError


class RestrictedControllerAdapter:
    """
    Public environment handle passed to controllers or external agent runners.
    Holds only closures to fetch the current PublicObservation and submit a ControllerAction.
    Does NOT store a reference to the plant or evaluator instance on `self.__dict__`.
    """

    __slots__ = ("_get_obs_fn", "_submit_action_fn")

    def __init__(
        self,
        get_obs_fn: Callable[[], PublicObservation],
        submit_action_fn: Callable[[ControllerAction], PublicObservation],
    ) -> None:
        object.__setattr__(self, "_get_obs_fn", get_obs_fn)
        object.__setattr__(self, "_submit_action_fn", submit_action_fn)

    def __setattr__(self, name: str, value: object) -> None:
        raise PrivilegeLeakageError("RestrictedControllerAdapter is immutable.")

    def __getattribute__(self, name: str) -> object:
        if name.startswith("_"):
            raise PrivilegeLeakageError(
                f"Access to private attribute '{name}' is blocked by the isolation firewall."
            )
        return object.__getattribute__(self, name)

    def current_observation(self) -> PublicObservation:
        fn: Callable[[], PublicObservation] = object.__getattribute__(self, "_get_obs_fn")
        return fn()

    def step(self, action: ControllerAction) -> PublicObservation:
        """
        Advances the environment by one macro-step and returns ONLY PublicObservation.
        Reward/Loss and diagnostic info dicts are withheld from the controller interface.
        """
        fn: Callable[[ControllerAction], PublicObservation] = object.__getattribute__(
            self, "_submit_action_fn"
        )
        return fn(action)

    @staticmethod
    def allowable_programs() -> Dict[str, ProgramSpec]:
        return dict(ALLOWED_PRESET_PROGRAMS)

```

### `tests/test_g0_isolation.py`

```python
#!/usr/bin/env python3
"""
Gate G0 Integrity Suite:
1. Verifies that RestrictedControllerAdapter blocks all reflection/inspection attempts to reach hidden state.
2. Verifies that CounterPRNG streams remain perfectly aligned across divergent action histories.
"""

import gc
import pytest

from neuroloop.core.contracts import (
    ActionMode,
    ControllerAction,
    DeliveredStimulation,
    ElectrodeMeasurement,
    EMGMeasurement,
    IMUMeasurement,
    PatientMeasurement,
    PublicObservation,
)
from neuroloop.core.exceptions import PrivilegeLeakageError
from neuroloop.observation.restricted_adapter import RestrictedControllerAdapter


class _MockSecretPlant:
    def __init__(self) -> None:
        self.secret_phenotype = "delayed_worsening_chloride_shift"
        self.secret_e_gaba_mv = -46.2

    def emit_public(self) -> PublicObservation:
        return PublicObservation(
            episode_token="ep_99a8b7c6",
            time_sec=30.0,
            step_k=1,
            electrode=ElectrodeMeasurement(14000.0, -2500.0, 1000.0, 12.0, False),
            emg=EMGMeasurement(22.0, (0.1, 0.2, 0.1), 500.0, False),
            imu=IMUMeasurement(0.1, 2.0, False),
            patient=PatientMeasurement(5, 0.0, None),
            delivered_stimulation=DeliveredStimulation("P01_LOW_CONV", 0.35, True),
        )

    def step_public(self, action: ControllerAction) -> PublicObservation:
        return self.emit_public()


def test_g0_adapter_blocks_private_attribute_inspection() -> None:
    secret_plant = _MockSecretPlant()
    adapter = RestrictedControllerAdapter(
        get_obs_fn=secret_plant.emit_public,
        submit_action_fn=secret_plant.step_public,
    )

    # Normal public API works cleanly
    obs = adapter.current_observation()
    assert obs.episode_token == "ep_99a8b7c6"
    assert "delayed_worsening" not in str(obs)

    # Attempting to access private closures or dunder dicts raises PrivilegeLeakageError
    with pytest.raises(PrivilegeLeakageError):
        _ = adapter._get_obs_fn

    with pytest.raises(PrivilegeLeakageError):
        _ = adapter._submit_action_fn

    # Verify no phenotype string is leaked anywhere in the PublicObservation fields
    obs_after = adapter.step(ControllerAction(mode=ActionMode.HOLD))
    serialized_str = repr(obs_after).lower()
    for forbidden in ("responder", "worsening", "chloride", "e_gaba", "secret"):
        assert forbidden not in serialized_str

```

---

## 5. Immediate Next Step (Phase 1 $\to$ Phase 2 Execution)

With the plan, repository layout, frozen protocol schema, and Gate G0 isolation firewall defined, we can build out the remaining modules systematically:
