# NeuroLoop v0.4.0 — Extended 2×2×2 Transfer Matrix & Report-Delay Sensitivity Report

## 1. Exact Finite Calibration POMDP & Sensor Information-Gap Analysis (`G2`)

- **Full-State Oracle Expected Loss ($J^*_{\text{full}}$):** `9.2000`
- **Bayes-Optimal Partial Observer Expected Loss ($J^*_{\text{partial}}$):** `10.2830`
- **Blind Policy Expected Loss ($J^*_{\text{blind}}$):** `10.8400`
- **Exact Information Gap ($\Delta_{\text{info}} = J^*_{\text{partial}} - J^*_{\text{full}}$):** `1.0830`
- **Exact Value of Observation ($J^*_{\text{blind}} - J^*_{\text{partial}}$):** `0.5570`

| Sensor Regime | Mean Clinical Loss | Mean Safety Loss | Mean Total Loss | Est. Info Gap vs. Full-State Oracle |
| :--- | ---: | ---: | ---: | ---: |
| `Full_Sensors` | 320.58 | 2.21 | **322.79** | +8.45 |
| `Report_Only_NoImpedance` | 317.07 | 5.00 | **322.08** | +7.74 |
| `Impedance_Only_NoReports` | 385.49 | 16.87 | **402.36** | +88.02 |
| `Blind_NoImpedance_NoReports` | 396.91 | 26.78 | **423.68** | +109.35 |

## 2. 2×2×2 Factorial Sensitivity Matrix (`Engine` × `Actuator` × `Habituation`)

| Engine | Actuator | Habituation | Phenotype | `C2_CalibratedFixed` Loss ($\text{CVaR}_{0.90}$) | `C5_SequentialBayesian` Loss ($\text{CVaR}_{0.90}$) | `C5_FrozenBeliefs` Loss | Paired Advantage ($\Delta L = C5 - C2$) |
| :--- | :--- | :--- | :--- | ---: | ---: | ---: | ---: |
| `engine_b_phenomenological` | `normalized` | `burst_slows_habituation` | `responder` | 264.81 (288.11) | **262.06** (268.04) | 265.14 | **-2.75** |
| `engine_b_phenomenological` | `normalized` | `burst_slows_habituation` | `nonresponder` | 342.94 (347.07) | **340.14** (344.51) | 347.85 | **-2.81** |
| `engine_b_phenomenological` | `normalized` | `burst_slows_habituation` | `delayed_worsening` | 400.61 (450.13) | **367.83** (374.93) | 502.40 | **-32.78** |
| `engine_b_phenomenological` | `normalized` | `frequency_neutral` | `responder` | 270.36 (279.70) | **280.70** (326.80) | 274.01 | **+10.35** |
| `engine_b_phenomenological` | `normalized` | `frequency_neutral` | `nonresponder` | 342.61 (345.23) | **339.80** (341.73) | 347.87 | **-2.80** |
| `engine_b_phenomenological` | `normalized` | `frequency_neutral` | `delayed_worsening` | 396.98 (486.83) | **366.50** (371.92) | 499.72 | **-30.48** |
| `engine_b_phenomenological` | `toy_resistive` | `burst_slows_habituation` | `responder` | 257.73 (266.56) | **257.74** (266.48) | 263.24 | **+0.01** |
| `engine_b_phenomenological` | `toy_resistive` | `burst_slows_habituation` | `nonresponder` | 342.20 (346.22) | **338.98** (346.02) | 349.84 | **-3.22** |
| `engine_b_phenomenological` | `toy_resistive` | `burst_slows_habituation` | `delayed_worsening` | 392.66 (448.35) | **365.20** (368.79) | 509.41 | **-27.46** |
| `engine_b_phenomenological` | `toy_resistive` | `frequency_neutral` | `responder` | 268.26 (287.36) | **266.58** (274.26) | 272.52 | **-1.69** |
| `engine_b_phenomenological` | `toy_resistive` | `frequency_neutral` | `nonresponder` | 342.18 (346.85) | **339.37** (347.34) | 349.86 | **-2.81** |
| `engine_b_phenomenological` | `toy_resistive` | `frequency_neutral` | `delayed_worsening` | 389.84 (452.40) | **370.96** (378.27) | 520.24 | **-18.88** |
| `engine_a_mechanistic` | `normalized` | `burst_slows_habituation` | `responder` | 398.34 (407.83) | **399.87** (409.23) | 403.09 | **+1.53** |
| `engine_a_mechanistic` | `normalized` | `burst_slows_habituation` | `nonresponder` | 532.92 (534.40) | **530.02** (530.77) | 536.81 | **-2.90** |
| `engine_a_mechanistic` | `normalized` | `burst_slows_habituation` | `delayed_worsening` | 594.51 (599.53) | **549.17** (556.36) | 601.67 | **-45.34** |
| `engine_a_mechanistic` | `normalized` | `frequency_neutral` | `responder` | 416.11 (424.01) | **424.54** (480.87) | 421.12 | **+8.43** |
| `engine_a_mechanistic` | `normalized` | `frequency_neutral` | `nonresponder` | 533.06 (534.60) | **529.38** (530.69) | 536.73 | **-3.68** |
| `engine_a_mechanistic` | `normalized` | `frequency_neutral` | `delayed_worsening` | 595.02 (599.52) | **549.40** (556.47) | 601.22 | **-45.62** |
| `engine_a_mechanistic` | `toy_resistive` | `burst_slows_habituation` | `responder` | 393.82 (414.78) | **395.02** (416.16) | 399.32 | **+1.20** |
| `engine_a_mechanistic` | `toy_resistive` | `burst_slows_habituation` | `nonresponder` | 533.55 (535.39) | **529.71** (531.08) | 539.88 | **-3.84** |
| `engine_a_mechanistic` | `toy_resistive` | `burst_slows_habituation` | `delayed_worsening` | 599.61 (605.32) | **548.40** (556.31) | 610.12 | **-51.22** |
| `engine_a_mechanistic` | `toy_resistive` | `frequency_neutral` | `responder` | 414.24 (427.10) | **415.80** (428.43) | 419.87 | **+1.57** |
| `engine_a_mechanistic` | `toy_resistive` | `frequency_neutral` | `nonresponder` | 533.46 (535.23) | **529.17** (530.28) | 540.74 | **-4.29** |
| `engine_a_mechanistic` | `toy_resistive` | `frequency_neutral` | `delayed_worsening` | 602.48 (604.98) | **547.63** (550.67) | 608.58 | **-54.85** |

## 3. Multi-Step Report-Lag Sensitivity Sweep (`report_delay_steps` $\in \{0, 1, 2, 3\}$)

| Report Delay (steps) | Phenotype | `C2_CalibratedFixed` Loss | `C5_SequentialBayesian` Loss ($\text{CVaR}_{0.90}$) | `C5` Active Steps | `C5_FrozenBeliefs` Loss | `C6_SparseRecurrentEI` Loss |
| :---: | :--- | ---: | ---: | ---: | ---: | ---: |
| `0` (0s) | `delayed_worsening` | 388.58 | **369.28** (374.27) | 4.0 | 504.29 | 405.72 |
| `0` (0s) | `nonresponder` | 342.36 | **339.43** (340.97) | 4.1 | 347.91 | 341.62 |
| `0` (0s) | `responder` | 262.55 | **259.62** (272.56) | 30.0 | 263.09 | 273.27 |
| `1` (30s) | `delayed_worsening` | 403.16 | **371.02** (386.95) | 4.6 | 496.77 | 407.44 |
| `1` (30s) | `nonresponder` | 343.79 | **340.14** (346.02) | 8.0 | 346.56 | 341.52 |
| `1` (30s) | `responder` | 262.10 | **265.56** (334.97) | 27.2 | 261.52 | 271.51 |
| `2` (60s) | `delayed_worsening` | 410.51 | **371.58** (384.72) | 4.7 | 496.19 | 408.60 |
| `2` (60s) | `nonresponder` | 342.23 | **339.44** (341.88) | 5.9 | 345.89 | 341.51 |
| `2` (60s) | `responder` | 281.87 | **256.70** (265.59) | 30.0 | 258.57 | 268.51 |
| `3` (90s) | `delayed_worsening` | 433.78 | **386.37** (396.50) | 6.3 | 507.56 | 416.77 |
| `3` (90s) | `nonresponder` | 341.93 | **340.15** (343.14) | 9.0 | 345.91 | 341.91 |
| `3` (90s) | `responder` | 284.57 | **259.95** (265.00) | 30.0 | 261.72 | 271.17 |
