# NeuroLoop v0.4.0 — Closed-Loop Adaptive Neuromodulation Research Instrument

> **Scope & Claim Tier (`SIMULATION_ONLY`):** NeuroLoop is a reproducible, deterministic software research instrument for evaluating sequential state-space inference, sparse patient-report querying, counterfactual twin auditing, and biophysical dorsal-horn robustness in closed-loop neuromodulation simulations. It makes **no** human clinical efficacy, clinical dosing, or hardware safety certification claims.

---

## 1. Architecture & Core Design Principles

1. **Physical Closed-Loop Separation (`Proposed` vs. `Delivered` Exposure):**
   - Controllers emit a strictly orthogonal [`ControlAction`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/contracts/__init__.py) (`StimulationCommand` $\in \{\text{HOLD}, \text{SET}, \text{OFF}\}$ $\times$ `FeedbackCommand` $\in \{\text{NONE}, \text{REQUEST}\}$).
   - [`SafetySupervisor`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/supervisor/__init__.py) enforces impedance limits, fault latching, and clean-step rearm hysteresis (`rearm_required_clean_steps`) on a fast-tick clock (`stop_latency_ms = 1000`).
   - [`NormalizedActuator`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/actuator/__init__.py) and [`ToyResistiveActuator`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/actuator/__init__.py) compute physical [`DeliveredExposure`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/contracts/__init__.py) (`delivered_intensity`, `contact_factor`, `delivery_status`) from contact impedance and compliance voltage limits.
   - Both plant engines evolve **exclusively** from `DeliveredExposure`. When `delivered_intensity == 0.0`, no new analgesic, habituation, or sensitization increment occurs, while existing carryover decays.

2. **Two Plant Engines (`Engine B` & `Engine A`):**
   - [`PhenomenologicalPlant`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/engines/__init__.py) (`engine_b_phenomenological`): Three-timescale dynamical system tracking short-term analgesia $a_k$, medium-term habituation $h_k$, and delayed sensitization $w_k$.
   - [`MechanisticDorsalHornPlant`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/engines/mechanistic.py) (`engine_a_mechanistic`): Biophysical dorsal-horn circuit model integrating explicit pulse trains ([`render_pulse_events`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/contracts/__init__.py)), intracellular chloride accumulation $[\text{Cl}^-]_i$, Goldman-Hodgkin-Katz (GHK) $\text{Cl}^-/\text{HCO}_3^-$ GABAergic reversal potential $E_{\text{GABA}}$, and electroneutral $\text{K}^+$-$\text{Cl}^-$ cotransporter (KCC2) extrusion driven by the chemical potential $\ln(([\text{K}^+]_i[\text{Cl}^-]_i)/([\text{K}^+]_o[\text{Cl}^-]_o))$.

3. **Delayed & Asynchronous Patient Feedback Queue:**
   - [`PendingReportQueue`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/sensors/__init__.py) enforces integer-millisecond availability (`available_at_ms`), preventing early report leakage (`PENDING_UNAVAILABLE`) and marking repeated reads as `STALE_CACHED` so controllers assimilate each report innovation exactly once.

4. **Canonical Counter-Based Randomness (`PYTHONHASHSEED`-Invariant):**
   - [`CanonicalScenarioKey`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/randomness/__init__.py) and [`SemanticRNG`](file:///Users/o2satz/Downloads/NeuroLoop/src/neuroloop/randomness/__init__.py) derive independent SHA-256 counter streams per semantic channel (`patient_prior`, `baseline_process`, `contact_faults`, `observation_noise`, `report_emissions`, `counterfactual_branch`), ensuring identical trajectories regardless of process hash seed or execution order.

---

## 2. Controller Tournament & Causal Ablation Suite

| Controller ID | Description |
| :--- | :--- |
| `C0_Off` | Open-loop zero stimulation baseline |
| `C1_Fixed_P02_MOD_BURST` | Open-loop fixed moderate burst stimulation |
| `C2_CalibratedFixed` | Patient-specific 6-step calibration followed by fixed best program |
| `C3_ConservativeRules` | Clinical heuristic rule controller with fault/pain thresholds |
| `C4_HeuristicFilter` | Static 3-hypothesis heuristic filter without carryover state propagation |
| `C5_SequentialBayesian` | **Primary Adaptive Controller:** 7-particle sequential state-space filter with carryover propagation and Expected Value of Information (EVoI) sparse querying |
| `C5_Ablation_FrozenBeliefs` | Locks posterior at prior `[0.50, 0.30, 0.20]` (`posterior_update_count == 0`) |
| `C5_Ablation_ShuffledReports` | Permutes incoming report innovations to test causal report-exposure alignment |
| `C5_Ablation_MatchedSchedule` | Updates beliefs normally on the same query schedule, but ignores posterior when selecting actions |
| `C6_SparseRecurrentEI` | 24-unit Dale's-law Excitatory/Inhibitory sparse recurrent network policy |
| `C6_Ablation_DenseRecurrent` | Dense unconstrained recurrent ablation |

---

## 3. Quickstart & CLI Reference

All commands run inside `/Users/o2satz/Downloads/NeuroLoop/.venv` with zero external runtime dependencies beyond Python's standard library:

```bash
# 1. Run the 18-point Acceptance Test Suite
.venv/bin/python -m unittest discover -s tests -v

# 2. Validate protocol files
.venv/bin/neuroloop validate-config protocols/development.yaml
.venv/bin/neuroloop validate-config protocols/validation.yaml
.venv/bin/neuroloop validate-config protocols/frozen/challenge.yaml

# 3. Execute tournament, verify bitwise replay, audit ledgers, and build report
.venv/bin/neuroloop run --protocol protocols/development.yaml --output runs/smoke
.venv/bin/neuroloop replay runs/smoke/manifest.json
.venv/bin/neuroloop audit runs/smoke --checks invariants,counterfactual,leakage
.venv/bin/neuroloop report runs/smoke --output reports/smoke

# 4. Run 2x2x2 factorial sensitivity matrix & report-lag sweep
.venv/bin/neuroloop sensitivity --protocol protocols/development.yaml --output reports --episodes 10

# 5. Generate standalone interactive HTML/SVG dashboard or launch live GUI Studio
.venv/bin/neuroloop dashboard --workspace . --output reports/dashboard.html
.venv/bin/neuroloop gui --port 8765
```

---

## 4. Key Generated Reports & Artifacts

- [reports/smoke/report.md](file:///Users/o2satz/Downloads/NeuroLoop/reports/smoke/report.md) — Development protocol report (`Engine B`, 0-step report delay, plus POMDP & Cross-Engine Transfer sections)
- [reports/val/report.md](file:///Users/o2satz/Downloads/NeuroLoop/reports/val/report.md) — Validation protocol report (`Engine B`, 1-step report delay, 5 phenotypes including `null_effect` and `random_fault_window`)
- [reports/challenge/report.md](file:///Users/o2satz/Downloads/NeuroLoop/reports/challenge/report.md) — Frozen Mechanistic Challenge report (`Engine A` biophysical dorsal horn, `release_subprocess` controller isolation)
- [reports/sensitivity_matrix.md](file:///Users/o2satz/Downloads/NeuroLoop/reports/sensitivity_matrix.md) — 2×2×2 Factorial Matrix (`Engine` $\times$ `Actuator` $\times$ `Habituation`) & Multi-Step Report-Lag Sweep (`d` $\in \{0, 1, 2, 3\}$)
- [reports/dashboard.html](file:///Users/o2satz/Downloads/NeuroLoop/reports/dashboard.html) — Self-contained interactive HTML/SVG Trajectory, Belief Simplex & Counterfactual Explorer
- [NeuroLoop_Final_Verification_Synthesis.md](file:///Users/o2satz/Downloads/NeuroLoop/NeuroLoop_Final_Verification_Synthesis.md) — Executive synthesis across all protocols, audits, and acceptance tests
