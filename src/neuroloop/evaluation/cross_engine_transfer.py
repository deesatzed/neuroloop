"""
Stage 4 (PR 6): Cross-Engine Transfer & Waveform Assumption Challenge Evaluator.
Tests frozen controllers across:
  1. Engine B (Phenomenological) -> Engine A (Mechanistic Dorsal Horn with GHK & KCC2).
  2. Frequency response challenges: `burst_slows_habituation`, `frequency_neutral`,
     and `burst_accelerates_habituation`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Sequence

from neuroloop.config import ProtocolConfig
from neuroloop.controllers import (
    AbstractController,
    CalibratedFixedController,
    ConservativeRulesController,
    OffController,
)
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.controllers.recurrent import RecurrentEIController
from neuroloop.evaluation import compute_exact_cvar, precompute_patient_calibration, run_single_episode
from neuroloop.randomness import CanonicalScenarioKey


@dataclass(frozen=True)
class TransferEvaluationRow:
    challenge_name: str
    engine_mode: str
    frequency_mode: str
    phenotype: str
    controller_name: str
    n_episodes: int
    mean_clinical_loss: float
    mean_safety_loss: float
    mean_total_loss: float
    cvar90_total_loss: float
    decision_violation_rate: float
    mean_posterior_updates: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def run_cross_engine_and_frequency_challenges(
    base_config: ProtocolConfig,
    n_episodes_per_phenotype: int = 10,
) -> List[TransferEvaluationRow]:
    challenges = [
        ("EngineA_Mechanistic_Transfer", "engine_a_mechanistic", "burst_slows_habituation"),
        ("EngineB_FrequencyNeutral", "engine_b_phenomenological", "frequency_neutral"),
        ("EngineB_ReversedFrequency", "engine_b_phenomenological", "burst_accelerates_habituation"),
    ]
    controllers: List[AbstractController] = [
        OffController(),
        CalibratedFixedController(),
        ConservativeRulesController(),
        SequentialBayesianController(),
        RecurrentEIController(ablate_ei_structure=False),
    ]

    rows: List[TransferEvaluationRow] = []
    for chal_name, eng_mode, freq_mode in challenges:
        cfg_dict = base_config.to_dict()
        cfg_dict["engine_mode"] = eng_mode
        cfg_dict["frequency_response_mode"] = freq_mode
        cfg_dict["protocol_namespace"] = f"{base_config.protocol_namespace}_{chal_name.lower()}"
        chal_cfg = ProtocolConfig.from_mapping(cfg_dict)

        for pheno in ("responder", "nonresponder", "delayed_worsening"):
            scenarios = [
                CanonicalScenarioKey.create(
                    chal_cfg.protocol_namespace, pheno, ep_idx, chal_cfg.seeds.scenario_offset
                )
                for ep_idx in range(n_episodes_per_phenotype)
            ]
            cal_records = [precompute_patient_calibration(chal_cfg, sk) for sk in scenarios]

            for ctrl in controllers:
                clin_l: List[float] = []
                safe_l: List[float] = []
                tot_l: List[float] = []
                viol_rates: List[float] = []
                updates: List[int] = []

                for idx, (skey, cal_rec) in enumerate(zip(scenarios, cal_records)):
                    ep_sum, _, _ = run_single_episode(
                        config=chal_cfg,
                        scenario_key=skey,
                        local_episode_sequence=idx,
                        controller=ctrl,
                        saved_calibration=cal_rec,
                        comparators=[],
                        enable_counterfactual_audits=False,
                    )
                    clin_l.append(ep_sum.cumulative_clinical_loss)
                    safe_l.append(ep_sum.cumulative_safety_loss)
                    tot_l.append(ep_sum.cumulative_total_loss)
                    viol_rates.append(ep_sum.decision_violation_rate)
                    updates.append(ep_sum.posterior_update_count)

                n = len(tot_l)
                rows.append(
                    TransferEvaluationRow(
                        challenge_name=chal_name,
                        engine_mode=eng_mode,
                        frequency_mode=freq_mode,
                        phenotype=pheno,
                        controller_name=ctrl.name,
                        n_episodes=n,
                        mean_clinical_loss=sum(clin_l) / n,
                        mean_safety_loss=sum(safe_l) / n,
                        mean_total_loss=sum(tot_l) / n,
                        cvar90_total_loss=compute_exact_cvar(tot_l, alpha=chal_cfg.evaluation.cvar_alpha),
                        decision_violation_rate=sum(viol_rates) / n,
                        mean_posterior_updates=sum(updates) / n,
                    )
                )
    return rows
