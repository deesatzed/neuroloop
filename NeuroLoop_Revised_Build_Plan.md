# NeuroLoop Lab — revised executable build plan

**Revision:** build-plan revision 1, based on the supplied v0.3.2 documents.  
**Status:** architectural direction retained; supplied benchmark and efficacy claims not accepted.  
**Scope:** software-only research. No stimulation hardware, patient treatment, or clinically validated parameter recommendations.  
**Primary deliverable:** a reproducible experiment that can distinguish an instrument defect, an uninformative sensor suite, and a genuinely ineffective adaptive policy.

## 1. Decision and source boundaries

Keep the partially observable controller boundary, history-dependent plants, paired disturbance streams, personalized-fixed comparator, independent model-form challenge, and tail-risk analysis. These are the right research requirements.

Do not build the next neural model on top of the supplied vertical slice without repairing its foundations. Executing the supplied code exposed defects that change its central conclusions. See `AUDIT.md` and the runnable evidence package.

This plan distinguishes three things:

- **Source facts:** behavior and requirements in supplied document S1 (master plan, 488 lines) and S2 (vertical slice, 792 lines).
- **Executed findings:** tests against the unmodified extracted snippets on Python 3.13.5, Linux x86_64. These are not Mac M4 performance tests.
- **Proposed design:** the changes below. Neither the proposed full simulator nor a biological reference model has been implemented or validated in this review.

The source snapshots are preserved. Do not overwrite them or retrospectively replace their reported results.

## 2. Critical repair order

| Priority | Problem | Required repair | Evidence required to close |
|---|---|---|---|
| P0 | Voltage-compliance telemetry and biological dose disagree | Introduce a real virtual-actuator stage; plant effects consume its delivered exposure, not requested intensity | Tests at zero output, partial delivery, normal delivery, disconnect, and reconnection |
| P0 | Bayesian belief never updates in the tested benchmark | Repair exposure accounting; prove report assimilation and posterior changes with deterministic fixtures | Belief trace showing known evidence changes beliefs; frozen-belief ablation |
| P0 | Published benchmark table does not reproduce | Withdraw it as a verified result; generate every table from retained event records | Source/config hashes, raw records, replayable commands, generated table |
| P0 | Python adapter is not a memory boundary | Define a threat model; use immutable data for trusted in-process tests and serialized process boundary for release runs | Deliberate leakage fixtures and restricted worker integration tests |
| P1 | Python `hash()` changes episode noise between processes | Use stable canonical identifiers and documented counter namespaces | Replay across different `PYTHONHASHSEED` values and execution order |
| P1 | Counterfactual calibrated comparator has no calibration history | Make calibration a recorded protocol with explicit controller checkpoint provenance | Forked comparator uses the patient's actual saved calibration |
| P1 | “Burst frequency” changes meaning between files | Separate pulse repetition, burst repetition, pulses per burst, pulse width, and duty structure | Pulse-event counts and waveform-label permutation tests |
| P1 | Zero pain is interpreted as missing; query action does not query | Validate action semantics and handle `None` explicitly | Boundary-value contract tests |
| P1 | Scientific success is made a prerequisite for reporting | Separate instrument gates from scientific outcomes | A legitimate negative result still produces a complete report |

Do not make the benchmark pass by changing voltage limits, clinical priors, loss weights, or thresholds without recording the scientific/design reason and starting a new protocol version.

## 3. Define the claim before selecting the model

The first question is:

> Under stated synthetic assumptions, does a feedback policy improve prespecified long-horizon outcomes over a fairly calibrated fixed policy, without unacceptable additional loss in nonresponding, worsening, or sensor-fault scenarios?

This is not a claim that surface electrodes measure nociceptor activity, that simulated waveforms inhibit human pain, or that an AI controller is superior clinically.

Define three evidence tiers:

1. **Instrument correctness:** the code implements its declared equations and contracts.
2. **Within-model decision evidence:** a controller performs better or worse under a specified synthetic model.
3. **Biological/physical relevance:** independent data support the model-to-device mapping. This tier is absent in the supplied implementation.

Never promote tier 1 or 2 results into tier 3 conclusions.

## 4. Architecture: make the actuator and clock explicit

```text
Frozen protocol + scenario manifest + counter-indexed disturbances
                              |
                    Experiment orchestrator
                              |
        public observation -> controller worker -> proposed action
                              |
                     safety supervisor
                              |
                  approved command / stop
                              |
            virtual actuator + contact/load dynamics
                              |
                    delivered exposure
                              |
                        plant engine
                              |
                sensor pipeline + report scheduler
                              |
                      next observation

Privileged evaluator: events, checkpoints, hidden outcomes, forks, reports.
The evaluator is never a controller dependency.
```

### 4.1 Ownership

- `orchestrator/`: simulation clock, scheduling, controller lifecycle, and episode termination.
- `controllers/`: public-observation processing, beliefs, and actions only.
- `supervisor/`: independent permissible-action rules and stop/rearm state machine. It uses declared accessible telemetry, not hidden phenotype or pain truth.
- `actuator/`: maps an approved command and physical or normalized load to actual delivered exposure.
- `engines/`: biological/phenomenological state transitions driven by delivered exposure. No controller, supervisor, or scoring imports.
- `sensors/`: causal sensing, feature windows, delayed/missing reports, and measurement artifacts.
- `evaluation/`: privileged outcome calculation, comparison, checkpoint forks, statistics.
- `storage/`: append-only event records, manifests, checksums, and generated tables.
- `viewer/`: reads stored events; no separate simulation or outcome implementation.

These boundaries replace the monolithic `SyntheticPatientPlant.step()`, which currently performs supervision, sensing, biological transitions, and loss calculation together (S2:277–365).

### 4.2 Two actuator modes, never a silent mixture

**MVP: normalized mode.** Use dimensionless exposure and explicitly synthetic contact/capacity constraints. Name the burden `stimulation_effort`, not physical energy. Do not display invented mA or a clinical safety claim.

**Later: toy-electrical mode.** Implement a declared electrical load model, finite compliance, actual output, and pulse integration. A simple resistor is acceptable for an engineering fixture, but not as an implicit patient-electrode model. A sensing impedance at one frequency must not silently stand in for the full load seen by a stimulation pulse.

For the resistor fixture only:

\[
I_{del}=\min(I_{cmd},V_{max}/R),\qquad V_{del}=I_{del}R.
\]

Return a status such as `OFF`, `FULL`, `PARTIAL`, or `FAULT`; partial delivery is not the same as no delivery. The plant's exposure calculation must use the returned actuator record.

Any future physical energy metric must integrate delivered voltage and current over time. Any charge metric must integrate current over each phase. Normalized intensity squared is not automatically joules or a tissue-safety measure.

### 4.3 Time and report semantics

Define integer timestamps for the event scheduler. Every record needs acquisition time, availability time, window start/end, and an observation sequence number. A controller sees only observations available by its decision time.

Do not represent a safety response only at 30-second controller steps. Give faults, stop commands, and rearm logic their own declared event timing. Measure worst-case simulated stop latency. The POC timing is an engineering assumption, not a device safety standard.

Write slow dynamics in explicit time units. For an exponential state:

\[
x(t+\Delta t)=e^{-\Delta t/\tau}x(t)+(1-e^{-\Delta t/\tau})x_{target}.
\]

If stochastic terms approximate continuous-time diffusion, their increment scale must be consistent with elapsed time. When changing step sizes, reuse an appropriately coupled noise path rather than comparing unrelated noise realizations.

Use a pending-report queue containing prompt ID, sampled state/time, availability time, response status, and reported value. Query burden affects completion and quality through declared synthetic parameters. An ignored prompt is not a zero pain report. Cached reports are not new evidence.

## 5. Public contracts and isolation

### 5.1 Actions

Replace redundant `QUERY_PATIENT` mode plus a separate Boolean with orthogonal components:

```text
ControlAction:
  stimulation: HOLD | SET(program_id) | OFF
  feedback: NONE | REQUEST(prompt_id)
  observation_sequence: integer
```

`HOLD + REQUEST` must retain stimulation and request feedback. `OFF + REQUEST` must turn output off and request feedback. Validate unknown programs, nonfinite values, invalid enums, unknown fields, stale sequence numbers, and contradictory combinations. `0` is a valid pain report; only `None` means missing.

Keep the program catalog immutable and validated at initialization. Frozen dataclasses are useful value containers; they do not provide range validation or a security boundary by themselves.

### 5.2 Observations

Public observations may contain causal telemetry, measurement quality flags computed from available signals, patient reports, and actual delivered-action history. They must not include hidden mechanisms, latent losses, oracle predictions, future reports, scenario parameters, or evaluator diagnostics.

Public diagnostic quality is not forbidden; privileged labels masquerading as diagnostic quality are forbidden.

Do not give controllers a stable phenotype-derived token. Use a local episode sequence only when necessary. Held-out scenario keys, internal IDs, and counterfactual stream keys stay evaluator-side.

### 5.3 Threat model

**Trusted research mode:** a controller is cooperative code that receives an immutable observation value and returns an action. This is an API discipline, not hostile-code containment.

**Release evaluation mode:** a fresh worker process receives only serialized messages through a bounded protocol. Do not pass callbacks, plant references, evaluator references, pickle objects, or inherited privileged handles. Use a clean worker start rather than a fork inheriting the parent experiment heap.

A separate process alone is not a security sandbox for adversarial code. If untrusted code is allowed, restrict filesystem access, network access, credentials, process inspection, and resource usage using an appropriate OS/container boundary. Do not claim “zero bytes reachable by any memory traversal.” Document the tested adversary and remaining side channels.

The orchestrator owns `step()`. The controller does not receive a callable that can advance the environment arbitrarily.

## 6. Reproducibility and randomness

Use a stable canonical scenario digest or explicit scenario index. Never derive simulation identity with Python's built-in `hash()`.

Separate:

- patient-parameter sampling;
- action-independent environmental disturbances;
- sensor disturbances;
- reporting/compliance latent random variables;
- controller exploration randomness;
- calibration randomization;
- counterfactual replicate identity.

A key should identify `(protocol_namespace, scenario_key, source, time_or_event_index, entity_id, draw_index, audit_replicate)`. Do not include controller ID in shared environmental disturbances. Do include an appropriate policy key for controller-specific stochastic decisions.

Common random numbers require a declared coupling, not merely identical seeds. Action-dependent probabilities should transform common underlying uniforms under the branch's own state. Each branch has its own observations, pending-report queue, supervisor state, actuator state, and controller memory.

Use SHA-based draws as a simple slow reference if desired. For throughput, benchmark a vetted counter-based generator such as Philox behind the same semantic key API. A blanket ban on every stateful generator object is unnecessary; the requirement is stable semantic streams, including documented library internals and snapshot/replay behavior.

Reproducibility tiers:

1. Bitwise event replay on a pinned reference CPU/software environment.
2. Serial/parallel and run-order invariance in that environment.
3. Declared numerical tolerance and distributional agreement across backends/platforms.

Record the code commit, dirty-tree diff hash, resolved protocol, program catalog, model parameters, dependency lock, numerical dtype, solver, platform, and random-stream schema. A hash of a YAML file does not prove that the file was used. The resolved runtime configuration must be the only source of these settings.

## 7. Pseudo-frequency and circuit scope

Retain the user's interest in pseudo frequencies, but make the abstraction explicit.

A waveform specification should distinguish:

- pulse repetition frequency within an active train;
- burst repetition frequency;
- pulses per burst or burst duration;
- pulse width and interphase interval;
- polarity/phase structure;
- normalized amplitude or explicitly modeled current, not both implicitly;
- electrode configuration when supported.

A pulse-event renderer can be tested independently of the neural simulator. Test pulse counts, timing, burst boundaries, and integrated exposure. An 80 Hz label need not cause 80 neural spikes/s, and a burst rate of 2 Hz must not overwrite an intraburst 100 Hz pulse rate.

The current `f < 10` rule makes a particular program habituate more slowly by construction (S2:303–312). Keep such behavior only as a labeled toy scenario. Add plants with no frequency effect, reversed ordering, and different timing effects. Include equal-effort comparisons when studying timing effects, so amplitude is not the explanation.

Permutation test: changing an arbitrary program ID must not change biological output. A controller may use declared waveform features, not a hardcoded privileged association with the name `P02`.

## 8. Model families, calibration, and fair baselines

### 8.1 Build the fast engine first

Begin with the three supplied phenomenological response types, but label them synthetic. Extend parameter distributions only after the harness is correct. Currently the episodes vary noise more than patient physiology; noise replication is not a validated patient population.

Add scenario families for unknown direction of response, variable delays, no treatment effect, baseline flares/remission, activity changes, report bias, and randomized fault onset/duration. Fixed fault timing at steps 18–24 can remain a unit test, not the generalization benchmark.

Do not invent WDR firing for Engine B if that engine has no neuronal output. Compare engines using a shared task-level outcome definition; retain engine-specific mechanistic outputs separately.

### 8.2 Calibration is its own protocol

Use a shared, recorded calibration budget for all controllers claiming personalized performance. Define program order randomization, exposure duration, carryover handling, feedback allowance, stopping, and failed-calibration fallback. Do not infer a response from an old report or an unconfirmed dose.

The calibrated-fixed policy locks its treatment choice, not its safety behavior. It still receives the same independent fault stop/rearm protection as the adaptive policy.

For continuation experiments, give compared policies the same calibration record and same post-calibration checkpoint. For whole-episode comparisons, include calibration burden in every relevant policy's outcome. Declare which estimand is primary.

Include OFF in the tournament, not only in counterfactual audits. Include a simple conservative rule policy and an adaptive heuristic without learned beliefs.

### 8.3 Bayesian claim discipline

Until a real sequential generative likelihood is implemented, call the supplied policy a **three-hypothesis heuristic filter**, not a calibrated particle/grid estimator or a value-of-information optimizer.

A minimally defensible Bayesian baseline maintains latent carryover/delayed-effect states and conditions its likelihood on actual delivery, elapsed time, report timing, and baseline uncertainty. Validate it first on a small known model. Report posterior calibration and predictive checks. Entropy thresholding is an uncertainty heuristic; expected decision improvement minus query cost is the intended value-of-information calculation.

Run mandatory ablations: frozen beliefs, shuffled informative reports, impedance-only, report-only, and heuristic policy with the same stimulation schedule. A policy that behaves identically when beliefs are frozen cannot credit its results to learning.

## 9. Counterfactual evaluation without false precision

Checkpoint the entire environment and controller state: plant, actuator, supervisor latch, scheduler queues, sensor buffers, patient response state, controller memory, and controller RNG state. Support explicit engine capability declarations. Do not assume `deepcopy` is a valid checkpoint for compiled neural engines.

At each audit checkpoint, compare specified continuation policies from the same current state. A saved calibrated program comes from that patient's calibration, not a new uninitialized controller. Replaying a policy on an observation history and resetting a policy at an audit point are different experiments; label them.

Use multiple horizons stated in seconds and multiple shared future-noise replicates. Report pairwise expected losses first. For a finite baseline set B:

\[
\widehat R_H^B = \overline L_H(\pi_{candidate})-\min_{b\in B}\overline L_H(b).
\]

This is restricted comparator excess loss, not global optimal regret. A minimum selected from finite noisy estimates has selection bias; use independent selection/evaluation replicates where an unbiased selected-comparator estimate is important, or report the approximation and the full pairwise matrix.

Do not average a per-realization clairvoyant minimum and call it the expected value of one deployable comparator. Negative restricted comparator loss is possible when the candidate beats every listed baseline.

Audit continuation forks are local decisions conditional on the current history. They are not an explanation of the entire past episode. Keep whole-episode randomized policy comparisons as the main performance estimand.

No terminal horizon may silently erase delayed harm. Either include a prespecified recovery/observation tail, use a validated terminal penalty, or explicitly limit the claim to the observed horizon. Count observations from overlapping audits as dependent within an episode.

## 10. Outcomes and inference

Keep separate ledgers for:

- synthetic clinical burden: pain-time integral and functional outcome, each displayed;
- treatment burden: delivered effort/exposure and query burden;
- safety: invalid proposals, delivered-envelope violations, continued delivery during a detected fault, rearm failures, and synthetic worsening events;
- instrument failures: exceptions, numerical divergence, timeouts, protocol mismatch, missing records.

A failed simulation is not quietly excluded or converted to a favorable zero loss. An empty result is unavailable, not zero.

Use time-integrated outcomes or clearly normalized averages. State every unit and denominator. A count of 140 violations across 800 decisions is a 17.5% decision-level violation rate, not 140% and not a per-episode probability. Report both decision-level and episode-level quantities when useful.

Compute exact empirical CVaR with fractional quantile-boundary mass. With 20 episodes and alpha=0.90, the estimate uses only two worst episodes; treat that as a smoke-test summary, not reliable tail non-inferiority evidence.

For a non-inferiority claim, prespecify a justified absolute margin and require an appropriate one-sided uncertainty bound on the relevant excess risk/loss to remain within the margin. Resample at the independent scenario/patient level, preserving policy pairing. If repeated episodes share a patient, use a patient-level hierarchy. Set sample size from desired precision and event prevalence, not an arbitrary fixed 20.

Report CVaR of each policy and the distribution/tail of paired excess loss; they answer different questions. Multiplicity and subgroup selection must be handled in the prespecified analysis plan.

The information-gap identity is useful theoretically, but a difference between two imperfect controllers is not an exact Bayes-optimal information bound. Build a small finite POMDP with an exact solution to test the evaluator; report reference-policy estimates for the larger model with their approximation status.

## 11. Two-engine strategy without circular validation

Use three explicit roles, not two ambiguously named models:

- **A: mechanistic reference.** Literature-backed equations, units, numerical tests, and reproduction targets.
- **A-fast: optional emulator of A.** Fit only on development data and validate on held-out inputs/parameters. It is not an independent biological challenge.
- **B: independently specified phenomenological challenge.** Different model structure and prespecified response assumptions. It can share serialization and utilities, not copied treatment-response equations.

Start with B as the fast instrument-development engine. Add A after the evaluation machinery works. A-fast is optional, justified by actual profiling.

Keep A's reference assumptions and B's challenge assumptions registered before evaluating frozen controllers. Controllers may train on development instances of both for a general robustness study; a claimed zero-shot direction requires a genuinely untouched target distribution. Repeatedly tuning after seeing B results converts B into development data.

Brian2 runtime and C++ standalone have different capabilities. Prove supported checkpointing and feedback execution rather than assuming a Python macro-loop maps directly to standalone. Reproduce selected published behaviors, not a blanket promise of spike-for-spike equality across different solvers and platforms.

## 12. Revised build sequence

| Sprint | Build | Acceptance evidence | Does a negative scientific result block the next step? |
|---|---|---|---|
| S0: audit quarantine | Archive supplied inputs; regenerate their output; mark unverified table; issue registry | Source hashes, reproduced table, demonstrated failures | Not applicable |
| S1: contracts and instrument | One config path, validated actions, normalized actuator, scheduler, safe stop/rearm, public/evaluator boundary | Contract, units, replay, zero-dose, fault, query, and leakage tests | No scientific claim yet |
| S2: complete minimal loop | Engine B, OFF/fixed/rules, calibration record, event sink, single-episode inspection | One-command 3-phenotype experiment; trace explains every decision | No; report honest results |
| S3: valid evaluator | Checkpoint forks, saved comparators, exact small-model tests, CVaR, paired intervals | Analytic fixtures, branch noninterference, audit-on/off equality | No; instrument errors do block |
| S4: information and adaptation | Genuine sequential estimator; sparse-query comparison; sensor and belief ablations | Decision sufficiency estimates and frozen-policy benchmark | No; unsupported/inconclusive is a valid outcome |
| S5: mechanistic reference | Equation/source registry, A, optional A-fast, unit and solver verification | Model credibility report with defined domain and deviations | A credibility failure blocks biological claims, not B reporting |
| S6: independent transfer | Frozen model-form challenge; null/worsening/fault families; capacity-matched recurrent contenders | Mean/tail/event outcomes with uncertainty and failures | No; determines stop/redesign/research decision |
| S7: evidence handoff | Generated report, sensor-value map, limitations, next bench experiment | Every conclusion linked to retained data and protocol | No requirement that AI wins |

A simple inspection viewer belongs in S2, not after all science succeeds. Its purpose is diagnosing dose, state, reports, and decisions. A polished interactive dashboard remains optional until the instrument is reliable.

## 13. Engineering gates versus research outcomes

**Engineering gates:** `PASS`, `FAIL`, or `NOT_IMPLEMENTED`. Failures prevent inferential claims.

**Research outcomes:** `SUPPORTED_UNDER_MODEL`, `NOT_SUPPORTED_UNDER_MODEL`, or `INCONCLUSIVE`. None prevents result generation.

**Translation status:** `SIMULATION_ONLY`, `BENCH_TESTED`, or a separately supported clinical status. This project starts at `SIMULATION_ONLY`.

Do not freeze the unexplained 10%, 20%, 8.0, 5.0, and 2.5 thresholds as scientific truths. Development may explore sensible scales; after pilot calibration, freeze justified thresholds before independent evaluation. Never tune plant response to guarantee a controller passes.

## 14. Concrete first-release acceptance suite

1. Stable scenario IDs across fresh interpreters and different `PYTHONHASHSEED` settings.
2. Identical reference event log under serial versus reordered parallel execution.
3. Nonfinite/invalid actions rejected; zero pain preserved.
4. `HOLD + REQUEST` does not switch output and creates one prompt.
5. Zero delivered exposure causes no new treatment-induced state increment, while existing carryover can persist.
6. Partial exposure changes plant effects and telemetry consistently.
7. Fault latch prevents repeated ON/OFF cycling until a declared rearm condition holds.
8. Duplicate observations cannot be assimilated twice; unavailable reports cannot be used early.
9. A known informative report changes the appropriate belief state after a known delivered exposure.
10. Same state/action/disturbances produce the same transition, including pending queues.
11. Forking and auditing do not alter the primary episode.
12. Comparator self-comparison produces zero pairwise excess loss.
13. Calibrated comparator uses the saved calibration program and memory.
14. Empirical CVaR handles 20, 21, ties, singleton, and invalid/empty inputs explicitly.
15. An analytic no-treatment-effect fixture produces no claimed mechanistic benefit.
16. Program-ID permutation preserves plant output.
17. A legitimate no-advantage result still produces a complete report.
18. Runtime protocol hashes match the resolved configuration and generated output.

These are proposed acceptance requirements. The review package's small tested helper module does not implement or certify this full suite.

## 15. Proposed repository and executable interface

```text
src/neuroloop/
  contracts/        # public schemas, action algebra, units
  config/           # validated protocol and resolved manifest
  randomness/       # stable keys and semantic counter streams
  orchestrator/     # scheduler, checkpoints, controller lifecycle
  supervisor/       # stop, rearm, exposure envelope, audit reasons
  actuator/         # normalized mode; separate toy-electrical mode
  engines/          # B first; A and A-fast optional later
  sensors/          # causal features, reports, delay queues
  controllers/      # simple baselines first; learned candidates later
  evaluation/       # pairwise rollouts, sufficiency, tail/event metrics
  storage/          # typed records and append-only persistence
  viewer/           # trace reader only
protocols/
  development.yaml
  validation.yaml
  frozen/           # access-controlled or separately held challenge manifests
models/assumptions/  # equation provenance and claim scope
```

Target commands to implement, not claims that these commands already exist:

```bash
neuroloop validate-config protocols/development.yaml
neuroloop run --protocol protocols/development.yaml --output runs/smoke
neuroloop replay runs/smoke/manifest.json
neuroloop audit runs/smoke --checks invariants,counterfactual,leakage
neuroloop report runs/smoke --output reports/smoke
```

The first complete run produces resolved configuration, manifest, step records, episode records, controller belief traces, counterfactual records, invalid-run ledger, and a generated report. Store hidden and public streams separately. Avoid an endlessly expanding JSON column when typed fields are required for assertions.

## 16. Not in the first release

No full fly connectome, unrestricted online RL, cloud agent orchestrator, custom hardware, clinical frequency discovery claim, automatic patent drafting, or high-resolution pulse simulation across entire hour-long cohorts.

Add complexity only after identifying a demonstrated limitation. A connectome-inspired controller is a later contender and must beat conventional recurrent and sparsity-matched randomized baselines under the same observation and interaction budget.

## 17. Definition of done

A new reader can reproduce the run, inspect actual delivered exposure, see which observations were available at every decision, replay the checkpoint forks, independently recompute the main metrics, and discover all important limitations without consulting the implementation author.

Success may be a negative result. The output should tell us which control strategy to test next, which sensors appear useful under which assumptions, and which physical/biological measurements are still required. It must not imply that synthetic success establishes analgesia or patentability.
