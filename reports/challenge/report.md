# NeuroLoop v0.4.0 — Reproducible Experiment Report (`neuroloop_frozen_challenge_v0_4`)

## 1. Gate & Claim Status Summary

| Dimension | Status | Scope / Verification Evidence |
| :--- | :--- | :--- |
| **Engineering Instrument Gate** | **`PASS`** | `0` instrument failures; config SHA-256 `7e8a31c9c982755f...` |
| **Research Outcome (Within-Model)** | **`SUPPORTED_UNDER_MODEL`** | Evaluated on `engine_a_mechanistic` (`normalized` actuator, `burst_slows_habituation`) |
| **Translation Status** | **`SIMULATION_ONLY`** | Software-only synthetic model; no human clinical efficacy or hardware safety claim |

## 2. Multi-Ledger Tournament Results by Phenotype

| Phenotype | Controller | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Exact $\text{CVaR}_{0.90}$ | Excess $\widehat{R}_H^{\mathcal{B}}$ | Confirmed Active Steps | Posterior Updates | Violation Rate (%) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `responder` | `C0_Off` | 528.33 | 0.00 | **528.33** | 529.69 | +25.28 | 0.0 | 0.0 | 0.00% |
| `responder` | `C1_Fixed_P02_MOD_BURST` | 388.98 | 1.50 | **390.48** | 411.33 | +0.00 | 30.0 | 0.0 | 0.00% |
| `responder` | `C2_CalibratedFixed` | 396.77 | 1.50 | **398.27** | 418.75 | +0.00 | 30.0 | 0.0 | 0.00% |
| `responder` | `C3_ConservativeRules` | 399.29 | 2.00 | **401.29** | 420.31 | +0.88 | 30.0 | 0.0 | 0.00% |
| `responder` | `C4_HeuristicFilter` | 414.07 | 0.88 | **414.94** | 434.18 | +4.83 | 30.0 | 5.0 | 0.00% |
| `responder` | `C5_SequentialBayesian` | 398.22 | 1.50 | **399.72** | 420.30 | +1.45 | 30.0 | 5.4 | 0.00% |
| `responder` | `C5_Ablation_FrozenBeliefs` | 400.99 | 1.50 | **402.49** | 422.97 | +2.09 | 30.0 | 0.0 | 0.00% |
| `responder` | `C5_Ablation_ShuffledReports` | 401.49 | 1.43 | **402.91** | 443.64 | +1.87 | 29.1 | 5.6 | 0.00% |
| `responder` | `C5_Ablation_MatchedSchedule` | 414.31 | 0.88 | **415.19** | 434.54 | +4.72 | 30.0 | 5.4 | 0.00% |
| `responder` | `C6_SparseRecurrentEI` | 416.36 | 0.88 | **417.24** | 438.85 | +5.27 | 29.6 | 0.0 | 0.00% |
| `responder` | `C6_Ablation_DenseRecurrent` | 414.30 | 0.88 | **415.17** | 434.24 | +4.76 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C0_Off` | 528.54 | 0.00 | **528.54** | 529.91 | +0.19 | 0.0 | 0.0 | 0.00% |
| `nonresponder` | `C1_Fixed_P02_MOD_BURST` | 530.05 | 1.50 | **531.55** | 533.91 | +0.71 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C2_CalibratedFixed` | 531.18 | 1.43 | **532.60** | 535.07 | +0.67 | 28.9 | 0.0 | 0.00% |
| `nonresponder` | `C3_ConservativeRules` | 535.12 | 2.12 | **537.24** | 539.35 | +1.74 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C4_HeuristicFilter` | 530.06 | 0.04 | **530.10** | 532.11 | +0.28 | 9.1 | 4.6 | 0.00% |
| `nonresponder` | `C5_SequentialBayesian` | 529.52 | 0.00 | **529.52** | 531.07 | +0.19 | 4.4 | 4.1 | 0.00% |
| `nonresponder` | `C5_Ablation_FrozenBeliefs` | 534.21 | 1.50 | **535.71** | 538.40 | +1.56 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C5_Ablation_ShuffledReports` | 531.32 | 1.43 | **532.74** | 535.50 | +0.86 | 28.1 | 5.4 | 0.00% |
| `nonresponder` | `C5_Ablation_MatchedSchedule` | 532.52 | 0.88 | **533.39** | 535.72 | +1.02 | 30.0 | 7.2 | 0.00% |
| `nonresponder` | `C6_SparseRecurrentEI` | 530.46 | 0.61 | **531.07** | 533.58 | +0.51 | 27.5 | 0.0 | 0.00% |
| `nonresponder` | `C6_Ablation_DenseRecurrent` | 530.64 | 0.88 | **531.51** | 533.64 | +0.59 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C0_Off` | 539.80 | 0.00 | **539.80** | 539.80 | +0.00 | 0.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C1_Fixed_P02_MOD_BURST` | 547.27 | 52.98 | **600.25** | 600.76 | +10.26 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C2_CalibratedFixed` | 548.52 | 50.85 | **599.36** | 599.74 | +10.27 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C3_ConservativeRules` | 551.80 | 75.06 | **626.86** | 628.56 | +14.98 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C4_HeuristicFilter` | 543.17 | 15.05 | **558.22** | 572.23 | +1.16 | 10.4 | 5.2 | 0.00% |
| `delayed_worsening` | `C5_SequentialBayesian` | 541.86 | 8.81 | **550.66** | 561.25 | +0.18 | 5.2 | 4.8 | 0.00% |
| `delayed_worsening` | `C5_Ablation_FrozenBeliefs` | 550.97 | 50.14 | **601.11** | 602.47 | +10.58 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C5_Ablation_ShuffledReports` | 547.73 | 46.24 | **593.97** | 599.42 | +9.20 | 27.7 | 6.0 | 0.00% |
| `delayed_worsening` | `C5_Ablation_MatchedSchedule` | 548.65 | 43.73 | **592.38** | 594.09 | +8.71 | 30.0 | 7.8 | 0.00% |
| `delayed_worsening` | `C6_SparseRecurrentEI` | 546.40 | 41.52 | **587.92** | 591.22 | +7.68 | 28.5 | 0.0 | 0.00% |
| `delayed_worsening` | `C6_Ablation_DenseRecurrent` | 546.77 | 43.73 | **590.50** | 591.22 | +8.25 | 30.0 | 0.0 | 0.00% |

## 3. Paired Scenario-Level Excess Loss (`C5_SequentialBayesian` vs `C2_CalibratedFixed`)

| Phenotype | $N$ Paired | Mean Excess Loss ($\Delta L$) | 95% CI | Exact $\text{CVaR}_{0.90}(\Delta L)$ | Relative Loss Reduction (%) |
| :--- | ---: | ---: | :--- | ---: | ---: |
| `responder` | 20 | +1.45 | [+1.21, +1.70] | +2.34 | -0.36% |
| `nonresponder` | 20 | -3.09 | [-3.41, -2.77] | -1.86 | +0.58% |
| `delayed_worsening` | 20 | -48.70 | [-50.67, -46.73] | -38.33 | +8.13% |

## 6. Sample Synchronized Diagnostic Trace

### Synchronized Episode Trace: `C5_SequentialBayesian` on `delayed_worsening` (Episode 0)

| Step | Proposed | Approved | Latch | Contact | Deliv Inten | Status | Latent Pain | Sensitiz. | Obs Report (Status) | Belief `[Resp, Null, Wors]` | Total Loss |
|---:|:---|:---|:---:|---:|---:|:---|---:|---:|:---|:---|---:|
| 0 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.94 | 0.56 | `FULL` | 9.02 | 1.54 | 10 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 14.03 |
| 1 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.95 | 0.57 | `FULL` | 10.00 | 1.66 | 10 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 15.37 |
| 2 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.95 | 0.57 | `FULL` | 10.00 | 1.77 | 10 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 15.38 |
| 3 | `SET:P02_MOD_BURST+Q` | `P02_MOD_BURST` | ok | 0.94 | 0.57 | `FULL` | 10.00 | 1.86 | 10 (PENDING_UNAVAILABLE) | `[0.50, 0.30, 0.20]` | 16.01 |
| 4 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.92 | 0.55 | `FULL` | 10.00 | 1.93 | 10 (NEW_PROMPT_RESPONSE) | `[0.50, 0.30, 0.20]` | 15.35 |
| 5 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.97 | 0.00 | `OFF` | 10.00 | 1.88 | 10 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.58 |
| 6 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.91 | 0.00 | `OFF` | 10.00 | 1.83 | 10 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.57 |
| 7 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 10.00 | 1.79 | 10 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.56 |
| 8 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 10.00 | 1.75 | 10 (SPONTANEOUS) | `[0.12, 0.53, 0.35]` | 13.56 |
| 9 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 10.00 | 1.72 | 10 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.55 |
| 10 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 10.00 | 1.69 | 10 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.54 |
| 11 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 10.00 | 1.66 | 9 (SPONTANEOUS) | `[0.12, 0.53, 0.35]` | 13.54 |
| 12 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 10.00 | 1.63 | 9 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.54 |
| 13 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 10.00 | 1.61 | 9 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.53 |
| 14 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 10.00 | 1.59 | 9 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.53 |
| 15 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 10.00 | 1.57 | 9 (STALE_CACHED) | `[0.12, 0.53, 0.35]` | 13.52 |

## 7. Provenance & Checksums
- **Config SHA-256:** `7e8a31c9c982755fd4f87b61508d3126d963f2cb39bedf5bf79cdf540c9be284`
- **Equation Registry SHA-256:** `fb30308a09657c41919034b78e6c3caba9e4e25901329f389565c679990cdb71`
- **Public Events SHA-256:** `df76917c9163132dcde561a05512a2170a1a9228d045c9252f4a903018313e45`
- **Privileged Events SHA-256:** `39fcc0818ba8655e9bccd7828e49cb4d7466d26baf5265cc3ef3b8b12b07c2ee`
- **Episodes JSON SHA-256:** `6e69d03e8aab2b57ba0563c671e949ca8ef8ffbeaba21f7e93df637f4dd8d95d`
