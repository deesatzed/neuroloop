# NeuroLoop v0.4.0 — Reproducible Experiment Report (`neuroloop_dev_v0_4`)

## 1. Gate & Claim Status Summary

| Dimension | Status | Scope / Verification Evidence |
| :--- | :--- | :--- |
| **Engineering Instrument Gate** | **`PASS`** | `0` instrument failures; config SHA-256 `ff714d03ff806260...` |
| **Research Outcome (Within-Model)** | **`SUPPORTED_UNDER_MODEL`** | Evaluated on `engine_b_phenomenological` (`normalized` actuator, `burst_slows_habituation`) |
| **Translation Status** | **`SIMULATION_ONLY`** | Software-only synthetic model; no human clinical efficacy or hardware safety claim |

## 2. Multi-Ledger Tournament Results by Phenotype

| Phenotype | Controller | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Exact $\text{CVaR}_{0.90}$ | Excess $\widehat{R}_H^{\mathcal{B}}$ | Confirmed Active Steps | Posterior Updates | Violation Rate (%) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `responder` | `C0_Off` | 338.15 | 0.00 | **338.15** | 339.56 | +14.48 | 0.0 | 0.0 | 0.00% |
| `responder` | `C1_Fixed_P02_MOD_BURST` | 251.32 | 1.50 | **252.82** | 262.07 | -0.10 | 30.0 | 0.0 | 0.00% |
| `responder` | `C2_CalibratedFixed` | 260.13 | 1.44 | **261.57** | 290.67 | +0.00 | 30.0 | 0.0 | 0.00% |
| `responder` | `C3_ConservativeRules` | 263.37 | 1.41 | **264.77** | 278.19 | +2.12 | 30.0 | 0.0 | 0.00% |
| `responder` | `C4_HeuristicFilter` | 274.36 | 0.83 | **275.19** | 306.32 | +3.75 | 27.4 | 5.5 | 0.00% |
| `responder` | `C5_SequentialBayesian` | 260.09 | 1.43 | **261.51** | 290.01 | +0.78 | 29.0 | 5.9 | 0.00% |
| `responder` | `C5_Ablation_FrozenBeliefs` | 260.64 | 1.50 | **262.14** | 271.05 | +1.00 | 30.0 | 0.0 | 0.00% |
| `responder` | `C5_Ablation_ShuffledReports` | 305.92 | 0.38 | **306.29** | 329.98 | +10.22 | 11.6 | 4.8 | 0.00% |
| `responder` | `C5_Ablation_MatchedSchedule` | 269.51 | 0.88 | **270.38** | 279.42 | +2.51 | 30.0 | 6.2 | 0.00% |
| `responder` | `C6_SparseRecurrentEI` | 271.71 | 0.88 | **272.59** | 291.36 | +3.09 | 29.1 | 0.0 | 0.00% |
| `responder` | `C6_Ablation_DenseRecurrent` | 269.24 | 0.88 | **270.12** | 277.48 | +2.61 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C0_Off` | 338.25 | 0.00 | **338.25** | 341.44 | +0.00 | 0.0 | 0.0 | 0.00% |
| `nonresponder` | `C1_Fixed_P02_MOD_BURST` | 341.66 | 1.50 | **343.16** | 346.36 | +0.94 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C2_CalibratedFixed` | 341.51 | 0.91 | **342.42** | 345.62 | +0.52 | 24.0 | 0.0 | 0.00% |
| `nonresponder` | `C3_ConservativeRules` | 344.19 | 1.65 | **345.84** | 349.29 | +1.49 | 27.6 | 0.0 | 0.00% |
| `nonresponder` | `C4_HeuristicFilter` | 339.90 | 0.09 | **339.99** | 342.95 | +0.15 | 9.8 | 4.3 | 0.00% |
| `nonresponder` | `C5_SequentialBayesian` | 339.84 | 0.15 | **339.99** | 343.63 | +0.13 | 7.2 | 4.2 | 0.00% |
| `nonresponder` | `C5_Ablation_FrozenBeliefs` | 346.24 | 1.50 | **347.74** | 350.86 | +1.79 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C5_Ablation_ShuffledReports` | 339.95 | 0.23 | **340.18** | 344.80 | +0.20 | 8.6 | 4.2 | 0.00% |
| `nonresponder` | `C5_Ablation_MatchedSchedule` | 343.98 | 0.88 | **344.86** | 348.14 | +1.12 | 30.0 | 7.2 | 0.00% |
| `nonresponder` | `C6_SparseRecurrentEI` | 341.52 | 0.35 | **341.87** | 345.52 | +0.57 | 22.0 | 0.0 | 0.00% |
| `nonresponder` | `C6_Ablation_DenseRecurrent` | 342.27 | 0.88 | **343.14** | 346.53 | +0.86 | 29.8 | 0.0 | 0.00% |
| `delayed_worsening` | `C0_Off` | 337.54 | 0.00 | **337.54** | 339.81 | +0.00 | 0.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C1_Fixed_P02_MOD_BURST` | 461.09 | 50.61 | **511.70** | 530.72 | +24.49 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C2_CalibratedFixed` | 385.08 | 12.92 | **398.00** | 449.24 | +4.58 | 14.4 | 0.0 | 0.00% |
| `delayed_worsening` | `C3_ConservativeRules` | 389.96 | 13.21 | **403.17** | 443.66 | +1.31 | 7.6 | 0.0 | 0.00% |
| `delayed_worsening` | `C4_HeuristicFilter` | 368.60 | 6.32 | **374.92** | 385.53 | +0.04 | 4.9 | 4.2 | 0.00% |
| `delayed_worsening` | `C5_SequentialBayesian` | 365.13 | 5.06 | **370.19** | 375.22 | +0.00 | 4.1 | 4.2 | 0.00% |
| `delayed_worsening` | `C5_Ablation_FrozenBeliefs` | 459.61 | 47.60 | **507.21** | 525.81 | +24.36 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C5_Ablation_ShuffledReports` | 405.19 | 22.56 | **427.76** | 509.80 | +8.43 | 14.8 | 4.8 | 0.00% |
| `delayed_worsening` | `C5_Ablation_MatchedSchedule` | 442.97 | 41.17 | **484.14** | 500.95 | +19.91 | 30.0 | 7.2 | 0.00% |
| `delayed_worsening` | `C6_SparseRecurrentEI` | 395.64 | 15.92 | **411.56** | 435.94 | +7.43 | 14.1 | 0.0 | 0.00% |
| `delayed_worsening` | `C6_Ablation_DenseRecurrent` | 434.06 | 36.15 | **470.21** | 492.88 | +17.44 | 27.2 | 0.0 | 0.00% |

## 3. Paired Scenario-Level Excess Loss (`C5_SequentialBayesian` vs `C2_CalibratedFixed`)

| Phenotype | $N$ Paired | Mean Excess Loss ($\Delta L$) | 95% CI | Exact $\text{CVaR}_{0.90}(\Delta L)$ | Relative Loss Reduction (%) |
| :--- | ---: | ---: | :--- | ---: | ---: |
| `responder` | 20 | -0.06 | [-6.54, +6.42] | +26.27 | +0.02% |
| `nonresponder` | 20 | -2.43 | [-3.36, -1.49] | +1.51 | +0.71% |
| `delayed_worsening` | 20 | -27.81 | [-42.32, -13.29] | -0.52 | +6.99% |

## 4. Decision Sufficiency & Sensor Information Gap (`G2`)

### 4.1 Exact Finite Calibration POMDP Analytical Benchmark
- **Full-State Oracle Expected Loss ($J^*_{\text{full}}$):** `9.2000`
- **Bayes-Optimal Partial Observer Expected Loss ($J^*_{\text{partial}}$):** `10.2830`
- **Blind Policy Expected Loss ($J^*_{\text{blind}}$):** `10.8400`
- **Exact Information Gap ($\Delta_{\text{info}} = J^*_{\text{partial}} - J^*_{\text{full}}$):** `1.0830`
- **Exact Value of Observation ($J^*_{\text{blind}} - J^*_{\text{partial}}$):** `0.5570`

### 4.2 Reference-Policy Sensor Ablation Estimates (`REFERENCE_POLICY_ESTIMATE`)

| Sensor Regime | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Est. Info Gap vs. Full-State Oracle |
| :--- | ---: | ---: | ---: | ---: |
| `Full_Sensors` | 320.58 | 2.21 | 322.79 | +8.45 |
| `Report_Only_NoImpedance` | 317.07 | 5.00 | 322.08 | +7.74 |
| `Impedance_Only_NoReports` | 385.49 | 16.87 | 402.36 | +88.02 |
| `Blind_NoImpedance_NoReports` | 396.91 | 26.78 | 423.68 | +109.35 |

## 5. Cross-Engine Transfer (Engine A Mechanistic GHK/KCC2) & Waveform Sensitivity Challenges

| Challenge | Phenotype | Controller | Mean Total Loss | Exact $\text{CVaR}_{0.90}$ | Posterior Updates |
| :--- | :--- | :--- | ---: | ---: | ---: |
| `EngineA_Mechanistic_Transfer` | `responder` | `C0_Off` | 528.29 | 529.87 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `responder` | `C2_CalibratedFixed` | 397.19 | 407.37 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `responder` | `C3_ConservativeRules` | 399.12 | 407.94 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `responder` | `C5_SequentialBayesian` | 398.69 | 408.87 | 5.8 |
| `EngineA_Mechanistic_Transfer` | `responder` | `C6_SparseRecurrentEI` | 415.47 | 426.00 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `nonresponder` | `C0_Off` | 528.26 | 529.52 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `nonresponder` | `C2_CalibratedFixed` | 532.06 | 533.82 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `nonresponder` | `C3_ConservativeRules` | 536.92 | 539.51 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `nonresponder` | `C5_SequentialBayesian` | 529.13 | 530.71 | 4.0 |
| `EngineA_Mechanistic_Transfer` | `nonresponder` | `C6_SparseRecurrentEI` | 530.83 | 533.70 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `delayed_worsening` | `C0_Off` | 539.80 | 539.80 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `delayed_worsening` | `C2_CalibratedFixed` | 592.43 | 599.85 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `delayed_worsening` | `C3_ConservativeRules` | 626.94 | 628.61 | 0.0 |
| `EngineA_Mechanistic_Transfer` | `delayed_worsening` | `C5_SequentialBayesian` | 549.84 | 556.41 | 3.8 |
| `EngineA_Mechanistic_Transfer` | `delayed_worsening` | `C6_SparseRecurrentEI` | 586.49 | 590.90 | 0.0 |
| `EngineB_FrequencyNeutral` | `responder` | `C0_Off` | 338.55 | 340.17 | 0.0 |
| `EngineB_FrequencyNeutral` | `responder` | `C2_CalibratedFixed` | 275.56 | 326.04 | 0.0 |
| `EngineB_FrequencyNeutral` | `responder` | `C3_ConservativeRules` | 274.80 | 323.47 | 0.0 |
| `EngineB_FrequencyNeutral` | `responder` | `C5_SequentialBayesian` | 281.72 | 328.92 | 4.8 |
| `EngineB_FrequencyNeutral` | `responder` | `C6_SparseRecurrentEI` | 280.19 | 305.32 | 0.0 |
| `EngineB_FrequencyNeutral` | `nonresponder` | `C0_Off` | 337.62 | 339.85 | 0.0 |
| `EngineB_FrequencyNeutral` | `nonresponder` | `C2_CalibratedFixed` | 342.05 | 345.91 | 0.0 |
| `EngineB_FrequencyNeutral` | `nonresponder` | `C3_ConservativeRules` | 345.69 | 349.08 | 0.0 |
| `EngineB_FrequencyNeutral` | `nonresponder` | `C5_SequentialBayesian` | 339.27 | 344.17 | 4.8 |
| `EngineB_FrequencyNeutral` | `nonresponder` | `C6_SparseRecurrentEI` | 341.15 | 344.74 | 0.0 |
| `EngineB_FrequencyNeutral` | `delayed_worsening` | `C0_Off` | 338.70 | 341.20 | 0.0 |
| `EngineB_FrequencyNeutral` | `delayed_worsening` | `C2_CalibratedFixed` | 400.26 | 440.16 | 0.0 |
| `EngineB_FrequencyNeutral` | `delayed_worsening` | `C3_ConservativeRules` | 394.99 | 434.67 | 0.0 |
| `EngineB_FrequencyNeutral` | `delayed_worsening` | `C5_SequentialBayesian` | 368.56 | 373.05 | 4.8 |
| `EngineB_FrequencyNeutral` | `delayed_worsening` | `C6_SparseRecurrentEI` | 408.97 | 429.17 | 0.0 |
| `EngineB_ReversedFrequency` | `responder` | `C0_Off` | 338.25 | 339.62 | 0.0 |
| `EngineB_ReversedFrequency` | `responder` | `C2_CalibratedFixed` | 273.81 | 280.06 | 0.0 |
| `EngineB_ReversedFrequency` | `responder` | `C3_ConservativeRules` | 274.12 | 280.68 | 0.0 |
| `EngineB_ReversedFrequency` | `responder` | `C5_SequentialBayesian` | 283.48 | 327.54 | 5.6 |
| `EngineB_ReversedFrequency` | `responder` | `C6_SparseRecurrentEI` | 277.22 | 285.18 | 0.0 |
| `EngineB_ReversedFrequency` | `nonresponder` | `C0_Off` | 338.40 | 340.58 | 0.0 |
| `EngineB_ReversedFrequency` | `nonresponder` | `C2_CalibratedFixed` | 342.24 | 346.68 | 0.0 |
| `EngineB_ReversedFrequency` | `nonresponder` | `C3_ConservativeRules` | 346.82 | 348.39 | 0.0 |
| `EngineB_ReversedFrequency` | `nonresponder` | `C5_SequentialBayesian` | 340.06 | 346.22 | 4.3 |
| `EngineB_ReversedFrequency` | `nonresponder` | `C6_SparseRecurrentEI` | 341.67 | 343.87 | 0.0 |
| `EngineB_ReversedFrequency` | `delayed_worsening` | `C0_Off` | 337.59 | 338.84 | 0.0 |
| `EngineB_ReversedFrequency` | `delayed_worsening` | `C2_CalibratedFixed` | 380.20 | 436.42 | 0.0 |
| `EngineB_ReversedFrequency` | `delayed_worsening` | `C3_ConservativeRules` | 397.02 | 428.20 | 0.0 |
| `EngineB_ReversedFrequency` | `delayed_worsening` | `C5_SequentialBayesian` | 368.21 | 377.00 | 5.1 |
| `EngineB_ReversedFrequency` | `delayed_worsening` | `C6_SparseRecurrentEI` | 395.89 | 416.81 | 0.0 |

## 6. Sample Synchronized Diagnostic Trace

### Synchronized Episode Trace: `C5_SequentialBayesian` on `delayed_worsening` (Episode 0)

| Step | Proposed | Approved | Latch | Contact | Deliv Inten | Status | Latent Pain | Sensitiz. | Obs Report (Status) | Belief `[Resp, Null, Wors]` | Total Loss |
|---:|:---|:---|:---:|---:|---:|:---|---:|---:|:---|:---|---:|
| 0 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.93 | 0.56 | `FULL` | 6.79 | 0.60 | 7 (SPONTANEOUS) | `[0.50, 0.30, 0.20]` | 9.21 |
| 1 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.94 | 0.56 | `FULL` | 7.01 | 1.07 | 7 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 9.59 |
| 2 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.97 | 0.58 | `FULL` | 7.74 | 1.44 | 7 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 12.37 |
| 3 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.94 | 0.56 | `FULL` | 8.12 | 1.71 | 7 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 12.85 |
| 4 | `SET:P02_MOD_BURST+Q` | `P02_MOD_BURST` | ok | 0.97 | 0.58 | `FULL` | 8.48 | 1.94 | 9 (NEW_PROMPT_RESPONSE) | `[0.50, 0.30, 0.20]` | 14.06 |
| 5 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 8.38 | 1.70 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 11.40 |
| 6 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.96 | 0.00 | `OFF` | 8.05 | 1.49 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.93 |
| 7 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 8.28 | 1.31 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 11.21 |
| 8 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 8.05 | 1.15 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.86 |
| 9 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 7.71 | 1.01 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.39 |
| 10 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 7.74 | 0.88 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.41 |
| 11 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 7.29 | 0.78 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 9.80 |
| 12 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.97 | 0.00 | `OFF` | 7.68 | 0.68 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.30 |
| 13 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.58 | 0.60 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 10.15 |
| 14 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.39 | 0.52 | 9 (STALE_CACHED) | `[0.00, 0.18, 0.82]` | 9.88 |
| 15 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.24 | 0.46 | 7 (SPONTANEOUS) | `[0.00, 0.18, 0.82]` | 9.67 |

## 7. Provenance & Checksums
- **Config SHA-256:** `ff714d03ff80626000d63e02981b7b079203e2a5fbb8cb0136d6b4cb79d191de`
- **Equation Registry SHA-256:** `fb30308a09657c41919034b78e6c3caba9e4e25901329f389565c679990cdb71`
- **Public Events SHA-256:** `a1eb4d09c22515fc96801d13cf748561ca3c727fab9e3fec60ace91e50ccaf3f`
- **Privileged Events SHA-256:** `c1c864ee70fecb2e4d7f6e8ff0d7a2034546e2084970e9f4f4106ec1bdac5b48`
- **Episodes JSON SHA-256:** `0b7fded908e116e8e301d142996617d56c2381a97ad52173203e143bafa5abce`
