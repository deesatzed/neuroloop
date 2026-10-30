## Assessment: preserve the research architecture, but repair the implementation before extending it

**The build plan is directionally strong. The supplied code is not yet a trustworthy implementation of that plan.** I reviewed both attachments, extracted and executed the standalone benchmark, ran the supplied isolation test, and tested several critical control paths.

The most important finding is not another theoretical refinement: **the code’s actuator, feedback, and learning logic are inconsistent in ways that invalidate its claimed benchmark explanation.**

I have prepared an improved build plan and an implementation handoff:

**NeuroLoop_Revised_Build_Plan.md[Revised build plan](sandbox:/mnt/data/NeuroLoop_Revised_Build_Plan.md)** · **NeuroLoop_GOAL.md[GOAL.md for the implementing SWE agent](sandbox:/mnt/data/NeuroLoop_GOAL.md)** · **NeuroLoop_Executed_Audit.md[Executed audit](sandbox:/mnt/data/NeuroLoop_Executed_Audit.md)**

The **NeuroLoop_Review_and_Handoff.zip[complete review package](sandbox:/mnt/data/NeuroLoop_Review_and_Handoff.zip)** includes preserved source, reproducible audit scripts, execution results, and a small set of tested foundational repairs. It is not a completed or fully repaired simulator.

---

## 1. The claimed benchmark does not reproduce

The second attachment presents its results as an “exact deterministic benchmark” and attributes the adaptive controller’s advantage to recognizing worsening and stopping stimulation. Pasted text (2)

Running the supplied code with its default experiment settings, while explicitly fixing `PYTHONHASHSEED=0`, produced:

| Scenario and controller | Supplied mean total loss | Executed mean total loss |
|---|---:|---:|
| Responder — calibrated fixed | 206.41 | **291.21** |
| Responder — Bayesian adaptive | 188.74 | **255.96** |
| Nonresponder — Bayesian adaptive | 250.11 | **284.08** |
| Delayed worsening — Bayesian adaptive | 264.18 | **298.42** |

The calibrated-fixed controller also accumulated **140 unsafe-proposal flags across the 20 responder episodes**, versus zero in the supplied table. The complete output is retained in the original_benchmark_hashseed0.txt[execution log](sandbox:/mnt/data/neuroloop_review/evidence/original_benchmark_hashseed0.txt).

Repeating that pinned run produced identical output in this environment. Changing only Python’s hash seed changed the results.

**These executed numbers are evidence of implementation problems—not a replacement efficacy benchmark.** The underlying defects mean neither table should currently be used to rank the controllers.

I cannot establish how the supplied table was generated. It would require a different code/configuration/environment record to explain the discrepancy.

---

## 2. The most consequential defect: the model applies stimulation it says it did not deliver

The code converts normalized intensity into current:

```python
desired_current_ma = 20.0 * normalized_intensity
```

It then calculates required voltage from impedance and imposes a **28 V** compliance limit. Meanwhile, the biological model calculates treatment effects directly from normalized intensity multiplied by contact quality. It never reconciles those effects with actual deliverable current. Pasted text (2) Pasted text (2)

Under the code’s own simplified resistance model:

\[
I_{\mathrm{LOW}}=20\times0.35=7\ \mathrm{mA}
\]

At its nominal full-contact resistance:

\[
V_{\mathrm{required}}=0.007\times12{,}500=87.5\ \mathrm{V}
\]

That exceeds the modeled 28 V limit even for the lowest active program.

In an executed test, the code reported failed delivery but still increased the biological analgesic state. This inconsistency is documented in the audit_results.json[audit results](sandbox:/mnt/data/neuroloop_review/evidence/audit_results.json).

### How I would fix it

Add a dedicated **virtual actuator** between the supervisor and the biological plant:

```text
Proposed action
      ↓
Supervisor-approved command
      ↓
Virtual actuator: contact, capacity, actual delivery
      ↓
Delivered exposure
      ↓
Biological state transition
```

The biological model must consume **delivered exposure**, never nominal settings.

For the first release, I recommend choosing one of two explicit modes:

**Normalized mode:** dimensionless stimulation and synthetic delivery constraints. This is sufficient to test controller behavior without pretending to model a physical device.

**Toy-electrical mode:** a declared electrical model that calculates actual current, voltage, and exposure consistently. A resistor is acceptable as a test fixture, but not as an unacknowledged model of tissue and electrode behavior.

**Do not simply raise the voltage limit until the benchmark looks better.** That would conceal the defect rather than resolve the model.

---

## 3. The “Bayesian adaptive” controller never updates its beliefs in the tested benchmark

This is the strongest reason to withdraw the current scientific interpretation.

The controller counts stimulation exposure only when `delivery_confirmed` is true. It updates its hypotheses only after at least two confirmed active steps. Pasted text (2)

Across all **60 tested scenarios—20 for each phenotype—**I found:

- **1,020 steps with nominally active output, but zero confirmed active-delivery steps.**
- The controller’s active-stimulation counter remained zero.
- Its belief vector remained exactly **`[0.5, 0.3, 0.2]`** in every scenario.

The retained audit_results.json[belief and delivery traces](sandbox:/mnt/data/neuroloop_review/evidence/audit_results.json) show this directly.

Consequently, the current controller cannot be earning its advantage through posterior recognition of delayed worsening. It is responding to compliance flags and following a time-based program schedule.

### How I would improve the acceptance tests

Before any controller tournament, require a deterministic fixture demonstrating:

> Known delivered exposure → informative new observation → appropriate posterior change → potentially different action.

Then add a **frozen-belief ablation**: run the same controller with belief updating disabled.

If its decisions and outcomes do not change, the result cannot be attributed to learning.

Even after repairing delivery, I would initially describe the existing implementation as a **three-hypothesis heuristic filter**. Its fixed likelihoods and entropy-triggered questions do not yet implement the dynamic treatment-response model or expected value-of-information calculation described in the proposal. Pasted text (2)

---

## 4. The isolation “firewall” is bypassable—and its test still passes

The adapter stores bound methods referencing the plant. I recovered the hidden plant using:

```python
object.__getattribute__(adapter, "_get_obs_fn").__self__
```

This works because the stored callable retains its instance reference. The supplied adapter stores exactly that kind of reference, and Python documents both the base attribute-access mechanism and bound methods’ `__self__` attribute. Pasted text [Python documentation](https://docs.python.org/3.13/reference/datamodel.html)

**The supplied G0 isolation test passed despite this bypass.** It tests ordinary access to selected private attributes and searches observation strings for forbidden words; it does not establish the claimed resistance to inspection or memory traversal. Pasted text

The standalone tournament also does not instantiate that adapter—it directly passes observations to `ctrl.act()`. Pasted text (2)

### My replacement

Use two explicitly different operating modes:

**Trusted development mode:** cooperative controller code receives an immutable observation and returns an action. Call this an API boundary, not a security boundary.

**Release evaluation mode:** a fresh controller process receives serialized observations and returns validated actions. It receives no callbacks, plant objects, evaluator objects, or inherited privileged handles.

For genuinely untrusted controller code, add operating-system restrictions on files, network access, credentials, process inspection, and resources. A separate process alone is not a complete sandbox.

The revised acceptance criterion should be:

> “No privileged information crosses the declared boundary under the documented threat model.”

Not:

> “Zero bytes are reachable by any inspection or memory traversal.”

---

## 5. Several smaller defects also affect the experiment

These are worth fixing now because they are inexpensive and will otherwise contaminate later work.

### Reproducibility breaks before the counter-based generator is called

The runner creates scenario IDs with:

```python
hash((pheno.value, ep_idx))
```

Python string hashes are salted between interpreter processes. The SHA-based generator is deterministic **conditional on its input ID**, but that ID is not stable. Pasted text (2) [Python documentation](https://docs.python.org/3.13/reference/datamodel.html)

Replace it with a canonical stable identifier and test replay across fresh processes, different `PYTHONHASHSEED` values, and different execution orders.

### The counterfactual “calibrated” comparator is not calibrated

The evaluator creates a new `CalibratedFixedController` and starts auditing at step 8 or later. Its calibration logic depends on earlier absolute step numbers, so that new comparator never obtains the patient’s calibration history. In the tested path, it simply uses its default low program. Pasted text (2) Pasted text (2)

A counterfactual comparator must receive the **actual saved calibration record and appropriate controller state**, not just the same class name.

### Zero pain is treated as missing

Expressions such as `last_pain_report or 6` and `last_pain_report or 5` replace a valid zero with a nonzero default. I reproduced a zero-pain observation becoming a calibration baseline of six. Pasted text (2) Pasted text (2)

Use explicit `is None` handling.

### The query action does not necessarily query

`QUERY_PATIENT` exists as an action mode, but feedback delivery depends on a separate Boolean. Its default combination can turn stimulation off without requesting feedback. Pasted text (2) Pasted text (2)

Use orthogonal action components: stimulation command plus optional feedback request.

### The frequency definitions drift between files

The master scaffold defines P02 as **100 Hz pulses with a 2 Hz burst frequency**. The standalone implementation collapses P02 to a single `pulse_freq_hz=2.0` value, then grants lower habituation to frequencies below 10 Hz. Those are different models. Pasted text Pasted text (2) Pasted text (2)

Create one waveform contract separating pulse repetition, burst repetition, pulse width, burst duration or pulse count, and amplitude.

### CVaR needs exact boundary handling

The supplied function averages an integer number of worst observations. With 21 losses numbered 0–20, it returns **19.0**, whereas the empirical worst-10% mean with fractional boundary mass is **19.4286**. It also returns zero for an empty dataset. Pasted text (2)

This does not explain the original 20-episode table discrepancy, but it will matter as experiment sizes change.

The review package includes tested helper repairs for these value-handling, action, identifier, and CVaR issues.

---

## 6. The largest improvement to the build plan: separate engineering gates from research outcomes

The master plan says no phase may begin until the previous phase passes, while putting reports and evidence dossiers last. Some intermediate gates require adaptive superiority. Pasted text

That creates a methodological problem:

> A correct experiment showing that adaptive control does not help could prevent the project from reaching its reporting phase.

I would use three separate statuses:

| Category | Statuses | Meaning |
|---|---|---|
| **Instrument correctness** | Pass / Fail / Not implemented | Is the experiment implemented correctly? |
| **Research result** | Supported / Not supported / Inconclusive | Does the hypothesis hold under the tested model? |
| **Translation status** | Simulation only / Bench tested / Further evidence required | What external relevance has actually been established? |

**Instrument failures block scientific claims. Negative scientific results do not block reporting.**

The previously proposed 10% and 20% targets should remain development proposals until their outcome scales and rationale are established. The team must not adjust simulated physiology or loss weights merely to make those thresholds pass.

---

## 7. The improved build sequence

I would replace the current six-phase sequence with the following. This retains the intended architecture but gets a trustworthy experiment working sooner.

| Stage | Deliverable | What must be demonstrated |
|---|---|---|
| **S0 — Preserve and audit** | Original inputs, regenerated outputs, defect register | Every existing performance claim has a provenance record |
| **S1 — Repair the instrument** | Validated contracts, configuration, actuator, scheduler, stop/rearm logic | Delivery consistency, reproducibility, correct queries, no future information |
| **S2 — Complete the minimal loop** | Fast synthetic plant; OFF, fixed, rules, and calibrated-fixed policies; event logs | One end-to-end run whose decisions can be explained from its trace |
| **S3 — Validate the evaluator** | Checkpoints, saved comparators, paired rollouts, CVaR and uncertainty | Self-comparison, analytic fixtures, and audit-on/off equivalence |
| **S4 — Add genuine adaptation** | Sequential estimator, feedback scheduling, sensor and belief ablations | Evidence that the model actually learns and that learning changes decisions |
| **S5 — Add the mechanistic reference** | Brian2 model, equation provenance, numerical validation | Defined validity domain and reproduced reference behaviors |
| **S6 — Test independent model assumptions** | Frozen cross-model challenges and later recurrent/connectome contenders | Benefits, failures, and tail outcomes under mismatch |
| **S7 — Produce the decision dossier** | Generated report and proposed bench experiments | Conclusions remain useful even when AI loses |

**Two sequencing changes matter particularly.**

First, move the detailed mechanistic engine later. Building both engines before the basic evaluator is trustworthy multiplies the debugging burden.

Second, move a simple episode viewer and generated reports earlier. A synchronized view of commanded exposure, delivered exposure, contact, reports, beliefs, and decisions would have made the present compliance/learning defect obvious.

The advanced execution backend should also follow actual requirements. Brian2 runtime permits Python-based network operations that C++ standalone does not directly support; the plan should not assume arbitrary Python feedback and checkpoint branching will work identically in both. [brian2.readthedocs.io](https://brian2.readthedocs.io/en/stable/user/computation.html)

---

## 8. What the first useful simulator should actually demonstrate

I would define the first release around **three diagnostic questions**, not a sophisticated neural animation.

### Does the intervention reach the simulated plant?

The trace must reconcile the proposed command, supervisor decision, actuator output, biological exposure, and reported delivery status.

A useful test is:

> Zero newly delivered exposure produces no new treatment-induced state increment, although existing carryover may persist.

That wording avoids incorrectly requiring all prior analgesic effects to disappear immediately.

### Does the controller learn from information that was actually available?

Every report needs acquisition and availability timestamps. Duplicate or stale reports must not be counted repeatedly as independent new evidence.

The controller should behave differently under informative observations versus frozen or shuffled observations. Otherwise, its apparent performance may come from its fixed schedule rather than feedback.

### Does the comparison give the baseline a fair chance?

The calibrated-fixed controller should have a credible calibration protocol, fresh reports, confirmed delivery, and the same independent safety protections.

“Fixed treatment” must not mean “continues blindly through faults.”

For counterfactual audits, fork the entire relevant state—not only biology—including the actuator, supervisor latch, report queue, sensor buffers, controller memory, and random-stream state.

These are proposed requirements in the revised plan, not features I am claiming to have completed.

---

## 9. Keep the pseudo-frequency research, but stop encoding the hoped-for answer

The current fast plant explicitly makes the low-frequency-labeled program habituate more slowly. That is acceptable as a **declared toy scenario**, but an optimizer preferring that program has only rediscovered a programmed assumption. Pasted text (2)

For the revised simulator, I would require waveform tests in which:

- Timing matters, does not matter, or has a different effect.
- Arbitrary program names are permuted without changing plant behavior.
- Relevant waveform comparisons control for delivered effort, so “better timing” is not simply greater exposure.

A useful distinction is:

**Waveform renderer:** generates the intended pulse/burst timing and verifies its structure.

**Recruitment model:** maps the delivered waveform to uncertain neural recruitment.

**Circuit model:** evolves excitation, inhibition, carryover, and other modeled states.

These should remain separate. A pulse frequency is not automatically a neural firing frequency, and a waveform renderer does not establish analgesic efficacy.

I would also distinguish the **independent challenge model** from a **fast surrogate fitted to the mechanistic engine**. A surrogate can accelerate experiments, but it is not an independent test of its parent model’s assumptions.

---

## 10. What I delivered—and what remains unproven

The revised documents provide a concrete implementation order rather than another layer of architectural praise.

The package contains the **revised build plan**, **SWE-agent GOAL.md**, **executed audit**, original source snapshots, raw benchmark outputs, and small corrective helpers. **Twenty-four focused tests passed for those helpers**, covering stable identifiers, zero-versus-missing handling, action semantics, empirical CVaR, and a clearly labeled resistor delivery fixture.

**I have not supplied a “corrected AI wins” table.** Repairing the full simulator requires decisions about delivery, calibration, dynamics, and evaluation that would change the experiment. Producing a new favorable table before those decisions are explicit would repeat the original problem.

### Bottom line

**Proceed with the project, but treat this as an instrument-repair milestone—not as a validated foundation ready for more complex AI.**

The immediate goal should be:

> **A small simulator whose delivered actions, observations, learning updates, and comparisons agree with one another—and whose report remains scientifically useful when adaptive control does not win.**

Once that works, the mechanistic circuit and connectome-inspired controller become meaningful experiments rather than additional complexity built on misleading feedback.



Not sure if these are still relevant?Implement Phase 2: Engine A (Mechanistic Dorsal Horn with GHK & KCC2) and Engine B

Implement Phase 3: Gate G2 Decision Sufficiency & Sensor Ablation Engine

Implement Phase 4/5: DuckDB Parquet Telemetry Sink & Twin-World Evaluator
