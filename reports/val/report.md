# NeuroLoop v0.4.0 — Reproducible Experiment Report (`neuroloop_val_v0_4`)

## 1. Gate & Claim Status Summary

| Dimension | Status | Scope / Verification Evidence |
| :--- | :--- | :--- |
| **Engineering Instrument Gate** | **`PASS`** | `0` instrument failures; config SHA-256 `2d26c54c6e7ab202...` |
| **Research Outcome (Within-Model)** | **`SUPPORTED_UNDER_MODEL`** | Evaluated on `engine_b_phenomenological` (`normalized` actuator, `burst_slows_habituation`) |
| **Translation Status** | **`SIMULATION_ONLY`** | Software-only synthetic model; no human clinical efficacy or hardware safety claim |

## 2. Multi-Ledger Tournament Results by Phenotype

| Phenotype | Controller | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Exact $\text{CVaR}_{0.90}$ | Excess $\widehat{R}_H^{\mathcal{B}}$ | Confirmed Active Steps | Posterior Updates | Violation Rate (%) |
| :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `responder` | `C0_Off` | 338.66 | 0.00 | **338.66** | 340.41 | +14.38 | 0.0 | 0.0 | 0.00% |
| `responder` | `C1_Fixed_P02_MOD_BURST` | 255.58 | 1.50 | **257.08** | 267.17 | -0.06 | 30.0 | 0.0 | 0.00% |
| `responder` | `C2_CalibratedFixed` | 262.85 | 1.47 | **264.32** | 280.01 | +0.00 | 30.0 | 0.0 | 0.00% |
| `responder` | `C3_ConservativeRules` | 266.36 | 1.31 | **267.67** | 280.79 | +1.77 | 30.0 | 0.0 | 0.00% |
| `responder` | `C4_HeuristicFilter` | 275.85 | 0.88 | **276.73** | 295.75 | +3.67 | 28.2 | 5.3 | 0.00% |
| `responder` | `C5_SequentialBayesian` | 261.51 | 1.50 | **263.01** | 272.54 | +0.66 | 30.0 | 5.5 | 0.00% |
| `responder` | `C5_Ablation_FrozenBeliefs` | 263.89 | 1.50 | **265.39** | 275.10 | +1.18 | 30.0 | 0.0 | 0.00% |
| `responder` | `C5_Ablation_ShuffledReports` | 321.60 | 0.07 | **321.68** | 331.51 | +13.42 | 5.8 | 4.1 | 0.00% |
| `responder` | `C5_Ablation_MatchedSchedule` | 272.84 | 0.88 | **273.72** | 281.60 | +2.74 | 30.0 | 5.5 | 0.00% |
| `responder` | `C6_SparseRecurrentEI` | 272.48 | 0.88 | **273.36** | 281.29 | +2.71 | 29.9 | 0.0 | 0.00% |
| `responder` | `C6_Ablation_DenseRecurrent` | 272.34 | 0.88 | **273.21** | 281.29 | +2.65 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C0_Off` | 338.06 | 0.00 | **338.06** | 340.46 | +0.00 | 0.0 | 0.0 | 0.00% |
| `nonresponder` | `C1_Fixed_P02_MOD_BURST` | 341.48 | 1.50 | **342.98** | 345.37 | +0.94 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C2_CalibratedFixed` | 341.12 | 0.81 | **341.94** | 345.31 | +0.44 | 24.2 | 0.0 | 0.00% |
| `nonresponder` | `C3_ConservativeRules` | 343.76 | 1.73 | **345.49** | 348.89 | +1.45 | 28.8 | 0.0 | 0.00% |
| `nonresponder` | `C4_HeuristicFilter` | 339.45 | 0.13 | **339.58** | 342.33 | +0.13 | 9.3 | 4.9 | 0.00% |
| `nonresponder` | `C5_SequentialBayesian` | 339.46 | 0.15 | **339.61** | 344.73 | +0.15 | 7.5 | 4.8 | 0.00% |
| `nonresponder` | `C5_Ablation_FrozenBeliefs` | 345.09 | 1.50 | **346.59** | 348.55 | +1.66 | 30.0 | 0.0 | 0.00% |
| `nonresponder` | `C5_Ablation_ShuffledReports` | 341.09 | 0.97 | **342.07** | 346.20 | +0.65 | 19.9 | 5.2 | 0.00% |
| `nonresponder` | `C5_Ablation_MatchedSchedule` | 342.87 | 0.88 | **343.74** | 346.14 | +1.00 | 30.0 | 7.0 | 0.00% |
| `nonresponder` | `C6_SparseRecurrentEI` | 340.80 | 0.31 | **341.11** | 343.24 | +0.49 | 21.8 | 0.0 | 0.00% |
| `nonresponder` | `C6_Ablation_DenseRecurrent` | 341.57 | 0.88 | **342.44** | 345.16 | +0.78 | 29.6 | 0.0 | 0.00% |
| `delayed_worsening` | `C0_Off` | 338.02 | 0.00 | **338.02** | 341.24 | +0.00 | 0.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C1_Fixed_P02_MOD_BURST` | 459.09 | 50.37 | **509.46** | 522.44 | +25.62 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C2_CalibratedFixed` | 384.44 | 12.06 | **396.50** | 449.17 | +3.34 | 12.8 | 0.0 | 0.00% |
| `delayed_worsening` | `C3_ConservativeRules` | 380.70 | 10.41 | **391.11** | 429.94 | +1.02 | 6.8 | 0.0 | 0.00% |
| `delayed_worsening` | `C4_HeuristicFilter` | 368.79 | 6.30 | **375.09** | 387.90 | +0.00 | 4.9 | 4.8 | 0.00% |
| `delayed_worsening` | `C5_SequentialBayesian` | 367.04 | 5.56 | **372.59** | 380.69 | +0.00 | 4.5 | 4.9 | 0.00% |
| `delayed_worsening` | `C5_Ablation_FrozenBeliefs` | 456.58 | 47.09 | **503.67** | 517.16 | +25.22 | 30.0 | 0.0 | 0.00% |
| `delayed_worsening` | `C5_Ablation_ShuffledReports` | 410.92 | 25.60 | **436.52** | 513.30 | +11.85 | 16.8 | 5.7 | 0.00% |
| `delayed_worsening` | `C5_Ablation_MatchedSchedule` | 440.73 | 40.68 | **481.41** | 492.74 | +20.84 | 30.0 | 7.3 | 0.00% |
| `delayed_worsening` | `C6_SparseRecurrentEI` | 388.83 | 14.24 | **403.06** | 437.77 | +6.88 | 12.7 | 0.0 | 0.00% |
| `delayed_worsening` | `C6_Ablation_DenseRecurrent` | 430.48 | 35.24 | **465.72** | 487.99 | +17.46 | 26.7 | 0.0 | 0.00% |
| `null_effect` | `C0_Off` | 337.65 | 0.00 | **337.65** | 339.04 | +0.00 | 0.0 | 0.0 | 0.00% |
| `null_effect` | `C1_Fixed_P02_MOD_BURST` | 341.06 | 1.50 | **342.56** | 343.95 | +0.94 | 30.0 | 0.0 | 0.00% |
| `null_effect` | `C2_CalibratedFixed` | 341.23 | 1.06 | **342.28** | 344.94 | +0.61 | 26.6 | 0.0 | 0.00% |
| `null_effect` | `C3_ConservativeRules` | 343.35 | 1.79 | **345.14** | 348.78 | +1.50 | 27.9 | 0.0 | 0.00% |
| `null_effect` | `C4_HeuristicFilter` | 339.46 | 0.13 | **339.59** | 342.77 | +0.16 | 11.2 | 4.8 | 0.00% |
| `null_effect` | `C5_SequentialBayesian` | 339.53 | 0.15 | **339.68** | 343.56 | +0.20 | 9.1 | 4.8 | 0.00% |
| `null_effect` | `C5_Ablation_FrozenBeliefs` | 344.92 | 1.50 | **346.42** | 347.97 | +1.74 | 30.0 | 0.0 | 0.00% |
| `null_effect` | `C5_Ablation_ShuffledReports` | 340.51 | 0.75 | **341.26** | 344.88 | +0.54 | 16.9 | 5.0 | 0.00% |
| `null_effect` | `C5_Ablation_MatchedSchedule` | 342.86 | 0.88 | **343.74** | 346.34 | +1.10 | 30.0 | 6.9 | 0.00% |
| `null_effect` | `C6_SparseRecurrentEI` | 340.79 | 0.53 | **341.31** | 343.72 | +0.58 | 24.1 | 0.0 | 0.00% |
| `null_effect` | `C6_Ablation_DenseRecurrent` | 341.34 | 0.88 | **342.22** | 343.74 | +0.77 | 30.0 | 0.0 | 0.00% |
| `random_fault_window` | `C0_Off` | 337.65 | 0.00 | **337.65** | 339.64 | +15.63 | 0.0 | 0.0 | 0.00% |
| `random_fault_window` | `C1_Fixed_P02_MOD_BURST` | 248.65 | 1.50 | **250.15** | 264.44 | -0.07 | 31.1 | 0.0 | 0.00% |
| `random_fault_window` | `C2_CalibratedFixed` | 256.39 | 1.47 | **257.86** | 273.27 | +0.06 | 31.1 | 0.0 | 0.00% |
| `random_fault_window` | `C3_ConservativeRules` | 262.83 | 1.22 | **264.05** | 277.54 | +2.41 | 31.1 | 0.0 | 0.00% |
| `random_fault_window` | `C4_HeuristicFilter` | 276.57 | 1.14 | **277.72** | 325.57 | +5.25 | 26.8 | 5.8 | 0.00% |
| `random_fault_window` | `C5_SequentialBayesian` | 254.68 | 1.50 | **256.18** | 269.82 | +0.71 | 31.1 | 6.1 | 0.00% |
| `random_fault_window` | `C5_Ablation_FrozenBeliefs` | 257.39 | 1.50 | **258.89** | 272.32 | +1.29 | 31.1 | 0.0 | 0.00% |
| `random_fault_window` | `C5_Ablation_ShuffledReports` | 306.31 | 0.38 | **306.69** | 328.23 | +12.00 | 11.2 | 5.4 | 0.00% |
| `random_fault_window` | `C5_Ablation_MatchedSchedule` | 268.67 | 1.19 | **269.86** | 282.67 | +3.31 | 31.1 | 6.2 | 0.00% |
| `random_fault_window` | `C6_SparseRecurrentEI` | 270.12 | 1.19 | **271.30** | 288.37 | +3.58 | 30.0 | 0.0 | 0.00% |
| `random_fault_window` | `C6_Ablation_DenseRecurrent` | 268.05 | 1.19 | **269.24** | 281.98 | +3.24 | 31.1 | 0.0 | 0.00% |

## 3. Paired Scenario-Level Excess Loss (`C5_SequentialBayesian` vs `C2_CalibratedFixed`)

| Phenotype | $N$ Paired | Mean Excess Loss ($\Delta L$) | 95% CI | Exact $\text{CVaR}_{0.90}(\Delta L)$ | Relative Loss Reduction (%) |
| :--- | ---: | ---: | :--- | ---: | ---: |
| `responder` | 20 | -1.31 | [-4.07, +1.45] | +0.87 | +0.50% |
| `nonresponder` | 20 | -2.32 | [-3.36, -1.29] | +2.55 | +0.68% |
| `delayed_worsening` | 20 | -23.91 | [-36.10, -11.72] | -4.04 | +6.03% |
| `null_effect` | 20 | -2.61 | [-3.47, -1.74] | +0.29 | +0.76% |
| `random_fault_window` | 20 | -1.68 | [-5.08, +1.72] | +0.90 | +0.65% |

## 6. Sample Synchronized Diagnostic Trace

### Synchronized Episode Trace: `C5_SequentialBayesian` on `delayed_worsening` (Episode 0)

| Step | Proposed | Approved | Latch | Contact | Deliv Inten | Status | Latent Pain | Sensitiz. | Obs Report (Status) | Belief `[Resp, Null, Wors]` | Total Loss |
|---:|:---|:---|:---:|---:|---:|:---|---:|---:|:---|:---|---:|
| 0 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.97 | 0.58 | `FULL` | 6.76 | 0.60 | 7 (SPONTANEOUS) | `[0.50, 0.30, 0.20]` | 9.18 |
| 1 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.98 | 0.59 | `FULL` | 7.14 | 1.05 | 7 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 9.77 |
| 2 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.94 | 0.56 | `FULL` | 7.91 | 1.38 | 7 (STALE_CACHED) | `[0.50, 0.30, 0.20]` | 12.53 |
| 3 | `SET:P02_MOD_BURST` | `P02_MOD_BURST` | ok | 0.94 | 0.57 | `FULL` | 8.02 | 1.64 | 8 (SPONTANEOUS) | `[0.50, 0.30, 0.20]` | 12.72 |
| 4 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 8.06 | 1.43 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.93 |
| 5 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 7.90 | 1.25 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.69 |
| 6 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 7.80 | 1.09 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.52 |
| 7 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 7.73 | 0.95 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.42 |
| 8 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.62 | 0.83 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.24 |
| 9 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 7.77 | 0.73 | 8 (STALE_CACHED) | `[0.00, 0.17, 0.83]` | 10.43 |
| 10 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 7.55 | 0.63 | 7 (SPONTANEOUS) | `[0.00, 0.17, 0.83]` | 10.11 |
| 11 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.97 | 0.00 | `OFF` | 7.26 | 0.55 | 7 (STALE_CACHED) | `[0.00, 0.15, 0.85]` | 9.72 |
| 12 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.94 | 0.00 | `OFF` | 7.33 | 0.48 | 7 (STALE_CACHED) | `[0.00, 0.15, 0.85]` | 9.79 |
| 13 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.93 | 0.00 | `OFF` | 7.45 | 0.42 | 7 (STALE_CACHED) | `[0.00, 0.15, 0.85]` | 9.95 |
| 14 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.26 | 0.37 | 7 (STALE_CACHED) | `[0.00, 0.15, 0.85]` | 9.68 |
| 15 | `OFF:P00_OFF` | `P00_OFF` | ok | 0.95 | 0.00 | `OFF` | 7.10 | 0.32 | 7 (STALE_CACHED) | `[0.00, 0.15, 0.85]` | 9.46 |

## 7. Provenance & Checksums
- **Config SHA-256:** `2d26c54c6e7ab202a70c64cc9bc9f3c905ee4e54d24b00285564aeb6696f2ca3`
- **Equation Registry SHA-256:** `fb30308a09657c41919034b78e6c3caba9e4e25901329f389565c679990cdb71`
- **Public Events SHA-256:** `2c4894697f7e58818ef556df308cb897b7d896575f9b57cab305a595deba5a6a`
- **Privileged Events SHA-256:** `aeb0887a9a9275ff38b5138ab3f496b39be87b9adaa898760e7f625fb90c639b`
- **Episodes JSON SHA-256:** `c3db8c227f4a37afd70dd7100e731d66b33cbbeb2ed2f7bd6efb120564a93d78`
