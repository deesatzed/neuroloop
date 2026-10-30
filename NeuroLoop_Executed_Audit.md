# NeuroLoop v0.3.2 — executed audit and repair priorities

**Assessment: needs revision before inferential use.** The two-engine and partially observable research direction remains useful. The supplied runnable implementation does not establish the claimed adaptive-control results.

## Reviewed material and scope

S1: `Pasted text(20261029-234325).txt`, master plan and six scaffold snippets, 488 lines.  
S2: `Pasted text (2)(20261029-234353).txt`, standalone vertical slice and asserted benchmark table, 792 lines.

Full original text and extracted code are in `source_snapshot/`. The original source was not modified. Tests ran on Python 3.13.5, Linux x86_64, not the user's Mac. The supplied G0 test was executed, benchmark results were regenerated, and targeted paths were tested. No biological model, hardware, human dataset, patent position, OS security sandbox, or full simulator repair was validated.

## 1. Reported benchmark does not reproduce

With the original master seed and defaults (20 scenarios per phenotype, 3 phenotypes, 3 controllers, 40 steps), there are **60 distinct scenario/phenotype combinations and 180 controller episodes**. The table below is one explicitly pinned run with `PYTHONHASHSEED=0`. Repeating that run produced identical output in the same environment. Changing only `PYTHONHASHSEED` to 1 changed the output.

These are results of the defective supplied simulator. They are evidence of a reproducibility/implementation problem, NOT a valid clinical or controller-efficacy comparison.

| Phenotype | Controller | Reported mean loss | Executed mean loss | Reported unsafe proposals | Executed unsafe proposals |
|---|---|---:|---:|---:|---:|
| responder | C2_CalibratedFixed | 206.41 | 291.21 | 0 | 140 |
| responder | C3_SimpleRules | 200.85 | 252.85 | 0 | 0 |
| responder | C4_BayesianAdaptive | 188.74 | 255.96 | 0 | 0 |
| nonresponder | C2_CalibratedFixed | 252.92 | 288.74 | 0 | 80 |
| nonresponder | C3_SimpleRules | 269.45 | 291.88 | 0 | 0 |
| nonresponder | C4_BayesianAdaptive | 250.11 | 284.08 | 0 | 0 |
| delayed_worsening | C2_CalibratedFixed | 341.60 | 294.10 | 0 | 80 |
| delayed_worsening | C3_SimpleRules | 412.88 | 355.53 | 0 | 0 |
| delayed_worsening | C4_BayesianAdaptive | 264.18 | 298.42 | 0 | 0 |

Sources: claimed values S2:774–786; executed values `evidence/original_benchmark_hashseed0.txt` and `evidence/original_metrics_hashseed0.json`. Full CVaR and regret outputs are retained in the same evidence folder.

The supplied “exact deterministic” table cannot be accepted as an executed result of this code without a different code/configuration/environment record that explains the discrepancy. This audit does not establish how that table was produced.

## 2. The main physiological/control defect: nominal dose is not delivered dose

S2:380–384 maps normalized intensity to `20 * intensity` mA and limits voltage to 28 V. At nominal full contact the model's resistance is 12,500 ohms. Its LOW program therefore requests 7 mA, requiring 87.5 V under its own resistor approximation. All nonzero presets exceed that nominal limit.

In an executed LOW-program fixture:

- reported resistance: 12,805.9 ohms;
- nominal current: 7 mA;
- voltage required by the code's own resistance model: 89.6413 V;
- reported output: 28 V;
- implied actual current in that model: about 2.1865 mA;
- `delivery_confirmed`: false;
- new biological analgesic trace: nevertheless nonzero (0.4371586).

Biological transitions consume nominal intensity times contact (S2:299–312), not an actuator-computed delivered current/exposure. Consequently dose, telemetry, safety, and learning describe different physical situations.

**Repair:** a separate virtual actuator produces the only exposure accepted by the plant. Keep normalized simulation and electrical fixtures distinct. Do not merely increase voltage to make a benchmark run.

## 3. The adaptive controller does not learn in the tested run

S2:573–595 increments `_active_stim_steps` only after confirmed active delivery and updates hypotheses only after at least two such steps. Across all **60 scenario/phenotype combinations**, the Bayesian policy had **1,020 active-output steps**, **zero confirmed active-output steps**, and **zero accumulated active-stimulation count**. Its final beliefs in every scenario were exactly `[0.5, 0.3, 0.2]`.

The policy instead repeatedly hits compliance gating and follows its fixed time-based program schedule. Its numerical results cannot be credited to evidence-based recognition of delayed worsening. The source's explanation at S2:790–792 is therefore unsupported by this implementation.

**Repair:** after consistent actuator delivery, require tests that known informative evidence changes beliefs and decisions. Add a frozen-belief ablation. The supplied three-hypothesis likelihood is still a heuristic with fixed expected deltas and no explicit dynamic carryover model; fixing the counter alone does not validate Bayesian efficacy estimation or value-of-information scheduling.

## 4. The adapter is an API wrapper, not a memory firewall

S1:369–377 stores bound methods. This expression retrieved the mock plant and its hidden phenotype:

```python
object.__getattribute__(adapter, "_get_obs_fn").__self__
```

The supplied `test_g0_isolation.py` still passed. It checks a few normal attribute accesses and output strings, not the claimed resistance to reflection or memory traversal (S1:457–480). The standalone tournament does not instantiate this adapter at all; it calls `ctrl.act(pub_obs)` directly (S2:727–730).

**Repair:** trusted mode gets only immutable data, with no hostile-code claim. Release evaluation uses fresh-process serialization and an explicit threat model. Untrusted code additionally requires OS-level permissions and resource restrictions. Hashing IDs and hiding underscored attributes are not a substitute.

## 5. Stable RNG implementation is undermined by unstable scenario keys

S2:697 uses `hash((pheno.value, ep_idx))`. Python string hashing is process-randomized. Thus the SHA-based noise generator is deterministic conditional on a scenario ID, but the scenario ID itself changes across default interpreter invocations.

**Repair:** stable canonical IDs; named semantic noise sources; manifests and cross-process replay tests. Keep bitwise guarantees scoped to a pinned numerical environment. Hashing a YAML file without consuming that resolved configuration is not experiment enforcement.

## 6. Comparator and counterfactual issues

The runner creates fresh `CalibratedFixedController()` comparators but never calibrates/resets them with the patient history (S2:687–690; S2:645–657). Audits begin at absolute step 8, after their calibration branches would have run. The tested comparator simply selected its default LOW setting, with both calibration measurements still `None`.

**Repair:** explicit saved calibration record and controller checkpoint. Compare continuation policies from the same checkpoint with their own observations. Record several shared future-noise replicates and pairwise outcomes. A per-realization minimum is a hindsight comparator, not automatically the minimum expected loss of a deployable policy. Do not claim globally optimal regret.

The first document specifies horizons 4/8/16 and 60 macrosteps; the second prose mentions horizon 12, while the runner uses horizon 8 and 40 macrosteps (S1:157–161; S2:26; S2:672–675; S2:716–724). Implement a single validated runtime protocol rather than several disconnected constants.

## 7. Other executed bugs and important static findings

| Finding | Evidence | Consequence / repair |
|---|---|---|
| Zero pain becomes missing/default | `report or 6` and `report or 5` at S2:492,538,564; tested zero yields calibration baseline 6 and rule program P02 | Test `is None`; preserve legitimate zero |
| `QUERY_PATIENT` does not request feedback | Source action defaults and supervisor S2:99–103,194–216; tested action turns output OFF and leaves feedback false | Orthogonal stimulation and query components |
| Empirical CVaR incorrect for fractional tail counts | S2:661–669; for losses 0..20, supplied 19.0 versus exact empirical 19.4285714 | Include fractional boundary mass |
| Empty outcomes return zero risk | `compute_cvar_90([])` returned 0 | Raise/report unavailable |
| Program P02 changes meaning | S1:252 has 100 Hz pulse, 2 Hz burst; S2:94 gives a single pulse frequency of 2 Hz | One waveform schema and tested event timing |
| Burst benefit is built into the toy plant | S2:303–312 explicitly lowers habituation below 10 Hz | Label hypothetical; test alternative/no-effect/reversed mappings |
| Faults always occur at steps 18–24 | S2:293–297 | Keep as a fixture; randomize challenge timing and duration |
| Stimulation effort is labeled energy without physical integration | S2:344–346 | Call it normalized effort, or model actual energy |
| Claim of delayed patient reports exceeds implementation | S2:386–402 generates prompted reports in the next observation; no pending delay queue | Distinguish staleness from independent reporting delay |
| Frozen dataclasses do not validate value ranges | S1:240–246 and contracts contain comments but no range validators | Validate types, finite numbers, units, timing, and action combinations |
| Independent plants/report pipeline absent from standalone slice | S2 contains only `SyntheticPatientPlant`; no Engine A, Parquet sink, or information-gap computation | Mark these as future deliverables, not achieved gates |

## 8. Build-plan changes, not only code changes

The master plan requires every earlier gate to pass before the next phase can begin (S1:7–16), while placing evidence reports last. That would obstruct reporting a legitimate failure of adaptive control. Instrument correctness must block inferential claims; failure to demonstrate superiority must not block reporting.

The proposed Phase 2 simultaneously requires both fast and detailed biological engines. Move the expensive reference engine after a complete fast-loop and evaluator. Bring a simple trace viewer and result generation forward. Numerical/biological provenance begins when equations are introduced, not only at the final dossier phase.

The prior thresholds (20%, 10%, fixed absolute CVaR margins) are development choices without validated clinical meaning. Preserve them as historical proposals, not established acceptance requirements. Calibrate research endpoints before opening a distinct held-out evaluation set.

## 9. Repairs delivered in this package

`foundation_fixes.py` provides small replacements for stable IDs, zero/missing handling, orthogonal action semantics, fractional-mass empirical CVaR, and a clearly labeled resistor-fixture actuator. **24 focused tests passed** in the review environment. These helpers do not constitute a corrected simulator and do not fix the biological model, estimator, supervisor lifecycle, isolation architecture, or counterfactual experiment.

`BUILD_PLAN.md` replaces the build sequence with an instrument-first plan, explicit actuator/scheduler interfaces, fair calibration, properly labeled comparator analysis, independent model validation, and negative-result reporting.

`GOAL.md` gives the implementing SWE agent scoped pull requests and acceptance evidence. No repaired adaptive-controller superiority table is supplied because a valid replacement requires changes to model assumptions and experimental design, not only mechanical bug fixes.

## 10. Verification receipts and outside technical references

Executed evidence:

- `evidence/audit_results.json` — defect reproductions and per-controller summaries.
- `evidence/original_metrics_hashseed0.json` — all 180 original episode results.
- `evidence/original_benchmark_hashseed0.txt` — original printed table.
- `evidence/original_benchmark_hashseed1.txt` — sensitivity to interpreter hash seed.
- `evidence/supplied_g0_test.txt` — original isolation test passes despite demonstrated bypass.
- `evidence/foundation_tests.txt` — tested helper repairs.

Outside sources consulted to check software semantics, not to replace the attached plan:

- Python data model: bound methods, base attribute access, salted hashes. https://docs.python.org/3.13/reference/datamodel.html
- Python dataclasses: generated methods do not normally inspect annotated value types. https://docs.python.org/3/library/dataclasses.html
- NumPy Philox: explicit counter/key interface and fixed-seed integer stream guarantees. https://numpy.org/doc/stable/reference/random/bit_generators/philox.html
- PyTorch reproducibility: limitations across versions/platforms. https://docs.pytorch.org/docs/stable/notes/randomness.html
- Brian2 computational methods: runtime versus C++ standalone capabilities and restrictions. https://brian2.readthedocs.io/en/stable/user/computation.html

The current documents supply no experiment validating neural selectivity, human pain relief, hardware safety, or patentability. Those questions remain outside this code audit.
