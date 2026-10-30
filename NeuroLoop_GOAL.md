# GOAL — repair the NeuroLoop instrument before extending it

## Mission

Build a software-only, reproducible closed-loop neuromodulation research instrument. Determine when feedback adds decision value over careful fixed personalization. Do not design the simulator to make adaptive AI win.

Read `BUILD_PLAN.md` and `AUDIT.md` first. The supplied v0.3.2 benchmark table is not a verified baseline. Preserve the original inputs and results as historical evidence.

## Current verified state

The supplied vertical slice runs, but its output differs from its reported table. Its modeled output voltage cannot deliver the nominal preset currents under its own load model; biological effects still use nominal intensity. The Bayesian controller never updates beliefs in the 60 scenarios audited. The proposed in-process adapter exposes the hidden plant through a bound-method reference. Python `hash()` makes scenario noise process-dependent. Counterfactual calibrated comparators are not calibrated at audit checkpoints.

The review package contains tested helper replacements for a few pure functions only. It is not a repaired simulator or a completed application.

## Implementation order

### PR 1 — configuration and value contracts

- Establish a single resolved configuration object; reject unknown keys and nonfinite values.
- Preserve all simulator assumptions in the manifest.
- Replace Python `hash()` episode keys with stable canonical scenario IDs.
- Use orthogonal stimulation commands (`HOLD`, `SET`, `OFF`) and optional feedback requests.
- Preserve zero pain; distinguish stale, missing, ignored, and new reports.
- Remove claims that dataclasses or attribute overrides provide a memory firewall.
- Add public/evaluator separation and explicit trusted-mode threat documentation.

**Acceptance:** deterministic ID tests across fresh processes; action truth-table tests; zero/missing distinction; exact manifest roundtrip.

### PR 2 — actual delivery and timing

- Implement `NormalizedActuator` first, with explicit synthetic units.
- Keep `ToyResistiveActuator` separate and labeled nonclinical when used in fixtures.
- Route plant updates exclusively through delivered exposure.
- Add safety latch, explicit rearm, and separate fast event timing from slow policy timing.
- Add pending-report queue and sensor-window metadata.
- Move safety, sensors, and losses out of the plant class.

**Acceptance:** zero-dose and partial-dose consistency; fault-response latency; no fault-induced on/off chattering; no future-report leakage; timestep tests for slow dynamics.

### PR 3 — honest minimal experiment

- Retain three synthetic phenotypes initially.
- Add OFF, fixed, conservative rules, and calibrated fixed policies.
- Implement a shared calibration protocol with confirmed exposure and fresh reports.
- Record every proposal, approval, delivered dose, observation, report, stop, rearm, and loss component.
- Generate a simple trace view and report from these records.
- Include negative and incomplete experiment outcomes.

**Acceptance:** one end-to-end command and complete replay; no hand-entered benchmark results.

### PR 4 — evaluator correctness

- Snapshot all environment state, queues, safety state, and controller state.
- Implement pairwise continuation policies from the same checkpoint.
- Carry the actual saved calibration into the fixed comparator.
- Use multiple shared future-noise replicates; retain pairwise results before selecting a minimum.
- Implement fractional-mass empirical CVaR and explicit missing-result handling.
- Prespecify recovery-tail treatment for delayed harm.

**Acceptance:** audit-on/off leaves main trajectory unchanged; self-comparison zero; analytic fixtures; exact CVaR tests; no discarded failed runs.

### PR 5 — sequential decision model

- Rename the old heuristic honestly; do not treat entropy thresholds as computed value of information.
- Implement and validate a sequential observation likelihood with carryover, baseline uncertainty, exposure, and report age.
- Demonstrate posterior updating on informative fixtures.
- Compare against frozen-belief and matched-heuristic ablations.
- Estimate decision sufficiency without claiming exact information bounds from approximate solvers.

**Acceptance:** belief and decision ablations; held-out paired effects and uncertainty. AI superiority is NOT required for software acceptance.

### PR 6 — mechanistic and independent challenges

- Add Brian2 reference only after the instrument works.
- Register equations, parameter provenance, units, numerical integration, and reproduction targets.
- Keep mechanistic reference A, optional A-fast surrogate, and independent B challenge distinct.
- Verify actual backend capabilities before promising live Python feedback or arbitrary checkpoints in compiled mode.
- Add recurrent/connectome contenders only when a measured baseline limitation warrants them.

**Acceptance:** documented validity domain, failure cases, null scenarios, waveform-label invariance, and frozen cross-model evaluation.

## Nonnegotiable expectations

1. No hardware control, medical treatment recommendations, or validated human frequency claims.
2. No changing model physiology or thresholds to force a 10% win.
3. No source-file edits that conceal earlier claims or output.
4. No report of biological benefit based solely on an invalid composite score.
5. No privileged loss or phenotype access during deployment-style controller evaluation.
6. No assertion of zero risk from observing zero simulated events.
7. No “publication-ready,” “patentable,” or “zero-leakage” labels without scoped evidence.
8. All new behavior requires a test that would fail when that behavior is broken.

## Required handoff after each PR

State what changed, which tests actually ran, which claims remain unsupported, which scientific assumptions were introduced, and how to reproduce the output. Distinguish implementation completion from scientific support.

## Definition of first useful completion

A single local experiment runs all three synthetic response types, produces public observations and actual delivered exposure, compares fair baselines, records controller belief changes, executes trustworthy checkpoint audits, and generates a report that remains useful when the adaptive controller loses.
