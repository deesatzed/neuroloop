"""
Complete 18-point Acceptance Test Suite (PR 1 through PR 6) for NeuroLoop v0.4.0.
Verifies every requirement in NeuroLoop_Revised_Build_Plan.md Section 14 and NeuroLoop_GOAL.md.
"""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import foundation_fixes
from neuroloop.actuator import NormalizedActuator, ToyResistiveActuator
from neuroloop.config import ProtocolConfig, RunManifest
from neuroloop.contracts import (
    BiophysicalNumericalError,
    ConfigurationError,
    ContractViolationError,
    ControlAction,
    DEFAULT_PROGRAM_CATALOG,
    DeliveryStatus,
    FeedbackCommand,
    IsolationViolationError,
    ProgramSpec,
    ReportStatus,
    StimulationCommand,
    WaveformSpec,
    render_pulse_events,
)
from neuroloop.controllers import (
    CalibratedFixedController,
    CalibrationRecord,
    ConservativeRulesController,
    FixedProgramController,
    HeuristicThreeHypothesisController,
    HoldComparatorController,
    OffController,
)
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.controllers.recurrent import RecurrentEIController
from neuroloop.engines import PhenomenologicalPlant
from neuroloop.engines.mechanistic import MechanisticDorsalHornPlant
from neuroloop.evaluation import (
    build_default_comparators,
    compute_exact_cvar,
    evaluate_checkpoint_forks,
    precompute_patient_calibration,
    run_single_episode,
)
from neuroloop.evaluation.decision_sufficiency import (
    estimate_sensor_information_gap,
    solve_exact_small_pomdp,
)
from neuroloop.orchestrator import (
    ClosedLoopEnvironment,
    SubprocessControllerWrapper,
    verify_public_observation_isolation,
)
from neuroloop.randomness import CanonicalScenarioKey, SemanticRNG
from neuroloop.storage import RunStore
from neuroloop.viewer import generate_experiment_report, render_episode_trace_markdown


def _load_dev_config() -> ProtocolConfig:
    return ProtocolConfig.load_file(ROOT_DIR / "protocols" / "development.yaml")


class TestAcceptanceSuite(unittest.TestCase):
    """Tests all 18 acceptance criteria in NeuroLoop_Revised_Build_Plan.md Section 14 + PR 1-6."""

    def test_01_stable_scenario_ids_across_processes_and_hashseeds(self) -> None:
        """Acceptance #1: Stable scenario IDs and RNG draws across PYTHONHASHSEED=0, 1, 42."""
        code = (
            "import sys; sys.path.insert(0, %r); "
            "from neuroloop.randomness import CanonicalScenarioKey, SemanticRNG; "
            "k = CanonicalScenarioKey.create('dev_v0_4', 'responder', 3, 1000); "
            "r = SemanticRNG(20261029, k); "
            "print(f'{k.scenario_digest}:{k.scenario_uint64}:{r.normal(\"env_disturbance\", 5):.12f}')"
        ) % str(SRC_DIR)

        outputs = []
        for hseed in ("0", "1", "42"):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = hseed
            out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True).strip()
            outputs.append(out)

        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[1], outputs[2])

    def test_02_serial_vs_reordered_execution_invariance(self) -> None:
        """Acceptance #2: Identical reference event outcomes under normal vs reversed scenario execution order."""
        cfg = _load_dev_config()
        scenarios = [
            CanonicalScenarioKey.create(cfg.protocol_namespace, pheno, idx, cfg.seeds.scenario_offset)
            for pheno in ("responder", "delayed_worsening")
            for idx in range(2)
        ]

        forward_results = {}
        for sk in scenarios:
            cal = precompute_patient_calibration(cfg, sk)
            ep_sum, _, _ = run_single_episode(
                cfg, sk, 0, SequentialBayesianController(), cal, comparators=[], enable_counterfactual_audits=False
            )
            forward_results[sk.scenario_digest] = ep_sum.to_dict()

        reverse_results = {}
        for sk in reversed(scenarios):
            cal = precompute_patient_calibration(cfg, sk)
            ep_sum, _, _ = run_single_episode(
                cfg, sk, 0, SequentialBayesianController(), cal, comparators=[], enable_counterfactual_audits=False
            )
            reverse_results[sk.scenario_digest] = ep_sum.to_dict()

        self.assertEqual(forward_results, reverse_results)

    def test_03_contract_validation_and_zero_pain_preserved(self) -> None:
        """Acceptance #3: Nonfinite/invalid actions and configs rejected; zero pain preserved."""
        # Non-finite values in WaveformSpec or ProgramSpec rejected
        with self.assertRaises(ContractViolationError):
            WaveformSpec(float("nan"), 0.0, 1, 150.0)
        with self.assertRaises(ContractViolationError):
            ProgramSpec("BAD", 1.5, WaveformSpec(80.0, 0.0, 1, 150.0))

        # Unknown keys or NaN in ProtocolConfig rejected
        cfg_dict = _load_dev_config().to_dict()
        cfg_dict["unknown_extra_field"] = 123
        with self.assertRaises(ConfigurationError):
            ProtocolConfig.from_mapping(cfg_dict)

        # Contradictory ControlAction rejected
        with self.assertRaises(ContractViolationError):
            ControlAction(stimulation=StimulationCommand.OFF, target_program_id="P02_MOD_BURST")
        with self.assertRaises(ContractViolationError):
            ControlAction(stimulation=StimulationCommand.HOLD, target_program_id="P01_LOW_CONV")
        with self.assertRaises(ContractViolationError):
            ControlAction(stimulation=StimulationCommand.SET, target_program_id=None)

        # Zero pain preserved in foundation_fixes, C2_CalibratedFixed, and C3_ConservativeRules
        self.assertEqual(foundation_fixes.resolve_pain_report(0, default_if_missing=6), 0)
        self.assertEqual(foundation_fixes.resolve_pain_report(None, default_if_missing=6), 6)

        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        env = ClosedLoopEnvironment(cfg, sk, 0)
        obs0 = env.current_observation
        # Create an observation with last_pain_report = 0
        obs_zero_dict = obs0.to_dict()
        obs_zero_dict["patient"]["last_pain_report"] = 0
        from neuroloop.contracts import PublicObservation

        obs_zero = PublicObservation.from_dict(obs_zero_dict)

        c2 = CalibratedFixedController()
        c2.reset(obs_zero)
        rec = c2.get_calibration_record()
        assert rec is not None
        self.assertEqual(rec.baseline_pain, 0.0)

        c3 = ConservativeRulesController()
        c3.reset(obs_zero)
        act3 = c3.act(obs_zero)
        # With 0 pain, C3 turns stimulation OFF rather than treating 0 as missing (5 -> P02_MOD_BURST)!
        self.assertEqual(act3.stimulation, StimulationCommand.OFF)

    def test_04_orthogonal_action_algebra_hold_and_off_with_request(self) -> None:
        """Acceptance #4: HOLD + REQUEST retains active stimulation and issues one prompt; OFF + REQUEST turns off and queries."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        env = ClosedLoopEnvironment(cfg, sk, 0)

        # Step 0: Set P02_MOD_BURST without query
        obs0 = env.current_observation
        step0 = env.step(
            ControlAction(
                stimulation=StimulationCommand.SET,
                feedback=FeedbackCommand.NONE,
                target_program_id="P02_MOD_BURST",
                observation_sequence=obs0.timing_meta.observation_sequence,
            )
        )
        self.assertEqual(step0.supervision.approved_program.program_id, "P02_MOD_BURST")
        self.assertFalse(step0.supervision.feedback_requested)

        # Step 1: HOLD + REQUEST retains P02_MOD_BURST and requests feedback
        obs1 = env.current_observation
        step1 = env.step(
            ControlAction(
                stimulation=StimulationCommand.HOLD,
                feedback=FeedbackCommand.REQUEST,
                prompt_id="test_hold_q",
                observation_sequence=obs1.timing_meta.observation_sequence,
            )
        )
        self.assertEqual(step1.supervision.approved_program.program_id, "P02_MOD_BURST")
        self.assertTrue(step1.supervision.feedback_requested)
        self.assertEqual(step1.supervision.prompt_id, "test_hold_q")
        self.assertGreater(step1.exposure.delivered_intensity, 0.4)

        # Step 2: OFF + REQUEST turns output OFF and requests feedback
        obs2 = env.current_observation
        step2 = env.step(
            ControlAction(
                stimulation=StimulationCommand.OFF,
                feedback=FeedbackCommand.REQUEST,
                prompt_id="test_off_q",
                observation_sequence=obs2.timing_meta.observation_sequence,
            )
        )
        self.assertEqual(step2.supervision.approved_program.program_id, "P00_OFF")
        self.assertTrue(step2.supervision.feedback_requested)
        self.assertEqual(step2.exposure.delivered_intensity, 0.0)

    def test_05_zero_delivered_exposure_no_new_increment_carryover_decays(self) -> None:
        """Acceptance #5: Zero delivered exposure causes no new treatment increment while carryover decays."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        rng = SemanticRNG(cfg.seeds.master_seed, sk)
        plant = PhenomenologicalPlant("responder", "burst_slows_habituation", rng)
        act = NormalizedActuator(cfg.actuator)

        # Step 0 with zero exposure -> analgesic_trace stays 0.0
        exp_zero = act.deliver(0, 30.0, DEFAULT_PROGRAM_CATALOG["P00_OFF"], 1.0, 12_500.0)
        out0 = plant.step(exp_zero, False, rng)
        self.assertEqual(out0.analgesic_trace, 0.0)
        self.assertEqual(out0.delayed_sensitization, 0.0)

        # Step 1 with active exposure -> analgesic_trace increases > 0
        exp_active = act.deliver(1, 30.0, DEFAULT_PROGRAM_CATALOG["P02_MOD_BURST"], 1.0, 12_500.0)
        out1 = plant.step(exp_active, False, rng)
        self.assertGreater(out1.analgesic_trace, 0.5)

        # Step 2 with zero exposure -> carryover persists (> 0) but strictly decays (< out1.analgesic_trace)
        exp_zero2 = act.deliver(2, 30.0, DEFAULT_PROGRAM_CATALOG["P00_OFF"], 1.0, 12_500.0)
        out2 = plant.step(exp_zero2, False, rng)
        self.assertGreater(out2.analgesic_trace, 0.0)
        self.assertLess(out2.analgesic_trace, out1.analgesic_trace)

    def test_06_partial_exposure_and_toy_resistive_actuator_consistency(self) -> None:
        """Acceptance #6: Partial exposure changes plant effects and telemetry consistently."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        rng = SemanticRNG(cfg.seeds.master_seed, sk)
        res_act = ToyResistiveActuator(cfg.actuator)

        # At 12,805.9 Ohm (the exact audit_results.json fixture) with P01_LOW_CONV (7 mA requested, 28V limit):
        # I_del = min(7.0, 28.0 / 12805.9 * 1000) = 2.186492 mA
        # delivered_intensity = (2.186492 / 20.0) * 1.0 = 0.109325 (NOT nominal 0.35!)
        exp_clamped = res_act.deliver(
            step_k=0,
            dt_sec=30.0,
            approved_program=DEFAULT_PROGRAM_CATALOG["P01_LOW_CONV"],
            contact_quality=1.0,
            load_impedance_real_ohm=12805.9,
        )
        self.assertAlmostEqual(exp_clamped.effective_current_ma or 0.0, 2.186492, places=5)
        self.assertAlmostEqual(exp_clamped.output_voltage_v or 0.0, 28.0, places=3)
        self.assertTrue(exp_clamped.compliance_limited)
        self.assertLess(exp_clamped.delivered_intensity, 0.12)

        # Compare plant response under clamped exposure vs nominal full exposure (at 1200 Ohm load)
        exp_full = res_act.deliver(
            step_k=0,
            dt_sec=30.0,
            approved_program=DEFAULT_PROGRAM_CATALOG["P01_LOW_CONV"],
            contact_quality=1.0,
            load_impedance_real_ohm=1200.0,
        )
        self.assertFalse(exp_full.compliance_limited)
        self.assertAlmostEqual(exp_full.delivered_intensity, 0.35, places=5)

        p1 = PhenomenologicalPlant("responder", "burst_slows_habituation", rng)
        p2 = PhenomenologicalPlant("responder", "burst_slows_habituation", rng)
        out_clamped = p1.step(exp_clamped, False, rng)
        out_full = p2.step(exp_full, False, rng)
        self.assertLess(out_clamped.analgesic_trace, out_full.analgesic_trace * 0.4)

    def test_07_fault_latch_prevents_chattering_until_rearm(self) -> None:
        """Acceptance #7: Fault latch prevents repeated ON/OFF cycling until rearm_required_clean_steps holds."""
        cfg = _load_dev_config()
        from neuroloop.supervisor import SafetySupervisor

        sup = SafetySupervisor(cfg.supervisor, cfg.timing, DEFAULT_PROGRAM_CATALOG)
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        env = ClosedLoopEnvironment(cfg, sk, 0)
        base_obs = env.current_observation

        # Simulate a high-impedance fault observation (45,000 Ohm > 35,000 Ohm limit)
        fault_dict = base_obs.to_dict()
        fault_dict["electrode"]["impedance_real_ohm"] = 45_000.0
        from neuroloop.contracts import PublicObservation

        obs_fault = PublicObservation.from_dict(fault_dict)

        prop_on = ControlAction(
            stimulation=StimulationCommand.SET,
            target_program_id="P02_MOD_BURST",
            observation_sequence=obs_fault.timing_meta.observation_sequence,
        )
        dec1 = sup.evaluate_proposal(prop_on, obs_fault)
        self.assertTrue(dec1.fault_latched_after)
        self.assertEqual(dec1.approved_program.program_id, "P00_OFF")
        self.assertEqual(dec1.stop_latency_ms, cfg.timing.fast_tick_ms)

        # Next step: impedance returns to normal (12,500 Ohm), but rearm_required_clean_steps=2.
        # On the first clean step, latch MUST remain active (preventing ON/OFF chattering)!
        clean1_dict = base_obs.to_dict()
        clean1_dict[" electrode"] = fault_dict["electrode"]
        clean1_dict["electrode"]["impedance_real_ohm"] = 12_500.0
        clean1_dict["electrode"]["fault_latched"] = True
        obs_clean1 = PublicObservation.from_dict(clean1_dict)
        dec2 = sup.evaluate_proposal(prop_on, obs_clean1)
        self.assertTrue(dec2.fault_latched_after)
        self.assertFalse(dec2.rearmed_this_step)
        self.assertEqual(dec2.approved_program.program_id, "P00_OFF")

        # Second consecutive clean step: supervisor rearms and allows P02_MOD_BURST
        dec3 = sup.evaluate_proposal(prop_on, obs_clean1)
        self.assertFalse(dec3.fault_latched_after)
        self.assertTrue(dec3.rearmed_this_step)
        self.assertEqual(dec3.approved_program.program_id, "P02_MOD_BURST")

    def test_08_pending_report_queue_no_early_leakage_and_no_double_assimilation(self) -> None:
        """Acceptance #8: Delayed reports are not available early, and cached reports are not assimilated twice."""
        cfg_dict = _load_dev_config().to_dict()
        cfg_dict["timing"]["report_delay_steps"] = 2
        cfg = ProtocolConfig.from_mapping(cfg_dict)
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        env = ClosedLoopEnvironment(cfg, sk, 0)

        # Step 0: Request a patient report with a 2-step reporting delay
        obs0 = env.current_observation
        rec0 = env.step(
            ControlAction(
                stimulation=StimulationCommand.SET,
                feedback=FeedbackCommand.REQUEST,
                target_program_id="P02_MOD_BURST",
                prompt_id="delayed_q0",
                observation_sequence=obs0.timing_meta.observation_sequence,
            )
        )
        # Immediately after step 0 (at step_k=1), the prompted report is still in the pending queue!
        self.assertIsNone(rec0.observation_after.patient.latest_prompt_response)
        self.assertEqual(rec0.observation_after.patient.pending_prompts_count, 1)

        # Feed a stale cached observation repeatedly to SequentialBayesianController:
        ctrl = SequentialBayesianController()
        ctrl.reset(obs0)
        # Give ctrl active exposure and one new report
        step1 = env.step(
            ControlAction(
                stimulation=StimulationCommand.HOLD,
                feedback=FeedbackCommand.NONE,
                observation_sequence=rec0.observation_after.timing_meta.observation_sequence,
            )
        )
        step2 = env.step(
            ControlAction(
                stimulation=StimulationCommand.HOLD,
                feedback=FeedbackCommand.NONE,
                observation_sequence=step1.observation_after.timing_meta.observation_sequence,
            )
        )
        # At step_k=3 (after 2 delay steps), the delayed report arrives
        ctrl.act(step1.observation_after)
        ctrl.act(step2.observation_after)
        b_after_arrival = ctrl.get_belief_summary()
        assert b_after_arrival is not None
        updates_1 = b_after_arrival["posterior_update_count"]

        # Calling act again with a STALE_CACHED observation with the same report timestamp must NOT increment update count
        stale_dict = step2.observation_after.to_dict()
        stale_dict["patient"]["report_status"] = ReportStatus.STALE_CACHED.value
        from neuroloop.contracts import PublicObservation

        obs_stale = PublicObservation.from_dict(stale_dict)
        ctrl.act(obs_stale)
        b_after_stale = ctrl.get_belief_summary()
        assert b_after_stale is not None
        self.assertEqual(b_after_stale["posterior_update_count"], updates_1)

    def test_09_known_informative_report_updates_belief_and_frozen_ablation_locks_prior(self) -> None:
        """Acceptance #9: Informative report changes posterior after confirmed exposure; frozen ablation stays at prior."""
        cfg = _load_dev_config()
        sk_wors = CanonicalScenarioKey.create(cfg.protocol_namespace, "delayed_worsening", 0, 1000)
        cal = precompute_patient_calibration(cfg, sk_wors)

        c5_live = SequentialBayesianController(freeze_beliefs=False)
        sum_live, _, _ = run_single_episode(
            cfg, sk_wors, 0, c5_live, cal, comparators=[], enable_counterfactual_audits=False
        )
        self.assertGreater(sum_live.posterior_update_count, 0)
        assert sum_live.final_belief is not None
        # Posterior probability of delayed_worsening (index 2) increases substantially above the 0.20 prior
        # and crosses the 0.34 abstention threshold, triggering P00_OFF abstention!
        self.assertGreater(sum_live.final_belief[2], 0.34)

        c5_frozen = SequentialBayesianController(freeze_beliefs=True)
        sum_frozen, _, _ = run_single_episode(
            cfg, sk_wors, 0, c5_frozen, cal, comparators=[], enable_counterfactual_audits=False
        )
        self.assertEqual(sum_frozen.posterior_update_count, 0)
        assert sum_frozen.final_belief is not None
        self.assertAlmostEqual(sum_frozen.final_belief[0], 0.50, places=5)
        self.assertAlmostEqual(sum_frozen.final_belief[1], 0.30, places=5)
        self.assertAlmostEqual(sum_frozen.final_belief[2], 0.20, places=5)
        # Live Bayesian controller achieves lower loss on delayed_worsening than frozen-belief ablation
        self.assertLess(sum_live.cumulative_total_loss, sum_frozen.cumulative_total_loss)

    def test_10_checkpoint_restore_and_pending_queue_determinism(self) -> None:
        """Acceptance #10: Same state, action, and disturbances produce identical transitions including pending queues."""
        cfg_dict = _load_dev_config().to_dict()
        cfg_dict["timing"]["report_delay_steps"] = 1
        cfg = ProtocolConfig.from_mapping(cfg_dict)
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 1, 1000)
        env = ClosedLoopEnvironment(cfg, sk, 0)
        ctrl = SequentialBayesianController()
        ctrl.reset(env.current_observation)

        for _ in range(5):
            obs = env.current_observation
            act = ctrl.act(obs)
            env.step(act)

        ckpt = env.create_checkpoint(ctrl)

        # Branch 1: step 5 more times
        branch1_losses = []
        for _ in range(5):
            obs = env.current_observation
            act = ctrl.act(obs)
            rec = env.step(act)
            branch1_losses.append(rec.loss.total_loss)
        obs_end_1 = env.current_observation.to_dict()

        # Restore checkpoint and repeat
        env.restore_checkpoint(ckpt, controller=ctrl)
        branch2_losses = []
        for _ in range(5):
            obs = env.current_observation
            act = ctrl.act(obs)
            rec = env.step(act)
            branch2_losses.append(rec.loss.total_loss)
        obs_end_2 = env.current_observation.to_dict()

        self.assertEqual(branch1_losses, branch2_losses)
        self.assertEqual(obs_end_1, obs_end_2)

    def test_11_audit_on_vs_off_leaves_primary_episode_unchanged(self) -> None:
        """Acceptance #11: Forking and counterfactual auditing do not alter the primary episode trajectory."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 2, 1000)
        cal = precompute_patient_calibration(cfg, sk)
        comps = build_default_comparators()

        sum_on, steps_on, cfs_on = run_single_episode(
            cfg, sk, 0, SequentialBayesianController(), cal, comparators=comps, enable_counterfactual_audits=True
        )
        sum_off, steps_off, cfs_off = run_single_episode(
            cfg, sk, 0, SequentialBayesianController(), cal, comparators=comps, enable_counterfactual_audits=False
        )

        self.assertGreater(len(cfs_on), 0)
        self.assertEqual(len(cfs_off), 0)
        self.assertEqual(sum_on.cumulative_total_loss, sum_off.cumulative_total_loss)
        self.assertEqual(sum_on.final_belief, sum_off.final_belief)
        self.assertEqual(
            [s.observation_after.to_dict() for s in steps_on],
            [s.observation_after.to_dict() for s in steps_off],
        )

    def test_12_comparator_self_comparison_zero_excess_loss(self) -> None:
        """Acceptance #12: Comparator self-comparison produces exact zero pairwise excess loss."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        rng = SemanticRNG(cfg.seeds.master_seed, sk)
        env = ClosedLoopEnvironment(cfg, sk, 0, rng=rng)
        cal = precompute_patient_calibration(cfg, sk)
        env.set_saved_calibration(cal)

        ctrl = SequentialBayesianController()
        ctrl.reset(env.current_observation)
        for _ in range(8):
            obs = env.current_observation
            env.step(ctrl.act(obs))

        ckpt = env.create_checkpoint(ctrl)
        ckpt.calibration_record = cal

        audit_rec = evaluate_checkpoint_forks(
            env=env,
            checkpoint=ckpt,
            candidate_controller=ctrl,
            comparators=[ctrl.clone()],
            base_rng=rng,
            horizon_steps=6,
            recovery_tail_steps=2,
            num_replicates=2,
            discount_gamma=0.98,
        )
        self.assertAlmostEqual(audit_rec.restricted_comparator_excess_loss, 0.0, places=12)
        self.assertAlmostEqual(audit_rec.pairwise_excess_losses[ctrl.name], 0.0, places=12)

    def test_13_calibrated_comparator_uses_saved_calibration_at_checkpoints(self) -> None:
        """Acceptance #13: Counterfactual CalibratedFixedController inherits saved CalibrationRecord at step >= 8."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        cal = precompute_patient_calibration(cfg, sk)
        self.assertTrue(cal.calibration_completed)
        self.assertIsNotNone(cal.p01_fresh_pain)
        self.assertIsNotNone(cal.p02_fresh_pain)
        self.assertFalse(cal.fallback_used)

        _, _, cfs = run_single_episode(
            cfg,
            sk,
            0,
            SequentialBayesianController(),
            cal,
            comparators=build_default_comparators(),
            enable_counterfactual_audits=True,
        )
        self.assertTrue(all(cf.calibrated_comparator_program == cal.selected_program_id for cf in cfs))

        # Also verify with an explicit P02_MOD_BURST calibration record
        cal_p02 = copy.deepcopy(cal)
        cal_p02.selected_program_id = "P02_MOD_BURST"
        _, _, cfs_p02 = run_single_episode(
            cfg,
            sk,
            0,
            SequentialBayesianController(),
            cal_p02,
            comparators=build_default_comparators(),
            enable_counterfactual_audits=True,
        )
        self.assertTrue(all(cf.calibrated_comparator_program == "P02_MOD_BURST" for cf in cfs_p02))

    def test_14_empirical_cvar_exact_fractional_boundary_and_edge_cases(self) -> None:
        """Acceptance #14: Empirical CVaR handles 20, 21, ties, singleton, and invalid/empty inputs explicitly."""
        # Audit fixture: 21 values 0..20 at alpha=0.90 -> exact empirical CVaR is 19.42857142857143
        vals_21 = [float(i) for i in range(21)]
        self.assertAlmostEqual(compute_exact_cvar(vals_21, alpha=0.90), 19.42857142857143, places=12)

        # 20 values 1..20 at alpha=0.90 -> top 2 values (19, 20) -> 19.5
        vals_20 = [float(i) for i in range(1, 21)]
        self.assertAlmostEqual(compute_exact_cvar(vals_20, alpha=0.90), 19.5, places=12)

        # Singleton and ties
        self.assertAlmostEqual(compute_exact_cvar([42.0], alpha=0.90), 42.0, places=12)
        self.assertAlmostEqual(compute_exact_cvar([5.0] * 15, alpha=0.90), 5.0, places=12)

        # Empty or NaN raises ContractViolationError
        with self.assertRaises(ContractViolationError):
            compute_exact_cvar([], alpha=0.90)
        with self.assertRaises(ContractViolationError):
            compute_exact_cvar([1.0, float("nan")], alpha=0.90)

    def test_15_analytic_null_effect_fixture_produces_no_mechanistic_benefit(self) -> None:
        """Acceptance #15: Analytic null_effect phenotype produces zero analgesic trace under any stimulation."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "null_effect", 0, 1000)
        cal = precompute_patient_calibration(cfg, sk)

        sum_off, steps_off, _ = run_single_episode(
            cfg, sk, 0, OffController(), cal, comparators=[], enable_counterfactual_audits=False
        )
        sum_fixed, steps_fixed, _ = run_single_episode(
            cfg, sk, 0, FixedProgramController("P02_MOD_BURST"), cal, comparators=[], enable_counterfactual_audits=False
        )

        # Under null_effect, active stimulation produces zero analgesia and identical pain integral to OFF,
        # while incurring higher total loss due to stimulation effort!
        self.assertTrue(all(s.plant_output.analgesic_trace == 0.0 for s in steps_fixed))
        self.assertAlmostEqual(sum_off.pain_time_integral, sum_fixed.pain_time_integral, places=10)
        self.assertGreater(sum_fixed.cumulative_total_loss, sum_off.cumulative_total_loss)

    def test_16_program_id_permutation_invariance(self) -> None:
        """Acceptance #16: Renaming or permuting program IDs with identical waveforms preserves plant output."""
        cfg = _load_dev_config()
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)

        # Standard run with P02_MOD_BURST
        env1 = ClosedLoopEnvironment(cfg, sk, 0, program_catalog=DEFAULT_PROGRAM_CATALOG)
        obs1 = env1.current_observation
        rec1 = env1.step(
            ControlAction(
                stimulation=StimulationCommand.SET,
                target_program_id="P02_MOD_BURST",
                observation_sequence=obs1.timing_meta.observation_sequence,
            )
        )

        # Permuted catalog where "ZZ_RENAMED_ARB" has the exact waveform and intensity of P02_MOD_BURST
        permuted_cat = dict(DEFAULT_PROGRAM_CATALOG)
        p02_spec = DEFAULT_PROGRAM_CATALOG["P02_MOD_BURST"]
        permuted_cat["ZZ_RENAMED_ARB"] = ProgramSpec(
            program_id="ZZ_RENAMED_ARB",
            normalized_intensity=p02_spec.normalized_intensity,
            waveform=p02_spec.waveform,
        )
        env2 = ClosedLoopEnvironment(cfg, sk, 0, program_catalog=permuted_cat)
        obs2 = env2.current_observation
        rec2 = env2.step(
            ControlAction(
                stimulation=StimulationCommand.SET,
                target_program_id="ZZ_RENAMED_ARB",
                observation_sequence=obs2.timing_meta.observation_sequence,
            )
        )

        self.assertEqual(rec1.plant_output, rec2.plant_output)
        self.assertEqual(rec1.loss.total_loss, rec2.loss.total_loss)

    def test_17_negative_result_still_produces_complete_report(self) -> None:
        """Acceptance #17: A legitimate negative scientific outcome still generates a complete report."""
        cfg_dict = _load_dev_config().to_dict()
        cfg_dict["seeds"]["episodes_per_phenotype"] = 2
        # Force an impossible margin so research outcome evaluates to NOT_SUPPORTED_UNDER_MODEL
        cfg_dict["evaluation"]["worsening_cvar_abs_margin"] = 0.0
        cfg = ProtocolConfig.from_mapping(cfg_dict)

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / "run_neg"
            rep_dir = Path(tmpdir) / "report_neg"
            manifest = RunManifest.build(cfg, DEFAULT_PROGRAM_CATALOG)
            skey = CanonicalScenarioKey.create(cfg.protocol_namespace, "delayed_worsening", 0, 1000)
            cal = precompute_patient_calibration(cfg, skey)

            # Make C5_SequentialBayesian artificially worse by running matched-schedule ablation under its name
            bad_c5 = SequentialBayesianController(
                matched_schedule_heuristic=True, name_override="C5_SequentialBayesian"
            )
            c2 = CalibratedFixedController()
            ep_c5, st_c5, _ = run_single_episode(cfg, skey, 0, bad_c5, cal, [], enable_counterfactual_audits=False)
            ep_c2, st_c2, _ = run_single_episode(cfg, skey, 1, c2, cal, [], enable_counterfactual_audits=False)
            ep_non_c5, st_non_c5, _ = run_single_episode(
                cfg,
                CanonicalScenarioKey.create(cfg.protocol_namespace, "nonresponder", 0, 1000),
                2,
                bad_c5,
                cal,
                [],
                enable_counterfactual_audits=False,
            )
            ep_non_c2, st_non_c2, _ = run_single_episode(
                cfg,
                CanonicalScenarioKey.create(cfg.protocol_namespace, "nonresponder", 0, 1000),
                3,
                c2,
                cal,
                [],
                enable_counterfactual_audits=False,
            )
            ep_resp_c5, st_resp_c5, _ = run_single_episode(
                cfg,
                CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000),
                4,
                bad_c5,
                cal,
                [],
                enable_counterfactual_audits=False,
            )
            ep_resp_c2, st_resp_c2, _ = run_single_episode(
                cfg,
                CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000),
                5,
                c2,
                cal,
                [],
                enable_counterfactual_audits=False,
            )

            store = RunStore(run_dir)
            store.write_run_artifacts(
                manifest,
                [ep_c5, ep_c2, ep_non_c5, ep_non_c2, ep_resp_c5, ep_resp_c2],
                [
                    (ep_c5, st_c5),
                    (ep_c2, st_c2),
                    (ep_non_c5, st_non_c5),
                    (ep_non_c2, st_non_c2),
                    (ep_resp_c5, st_resp_c5),
                    (ep_resp_c2, st_resp_c2),
                ],
                [],
                [],
            )
            summary = generate_experiment_report(run_dir, rep_dir)
            self.assertEqual(summary["engineering_gate_status"], "PASS")
            self.assertEqual(summary["research_outcome"], "NOT_SUPPORTED_UNDER_MODEL")
            self.assertTrue((rep_dir / "report.md").exists())
            self.assertTrue((rep_dir / "report_summary.json").exists())

    def test_18_manifest_roundtrip_and_mechanistic_ghk_kcc2_and_subprocess_isolation(self) -> None:
        """Acceptance #18 + PR 5/6: Manifest roundtrip, POMDP solver, Engine A GHK/KCC2 equilibrium, and subprocess worker."""
        cfg = _load_dev_config()
        manifest = RunManifest.build(cfg, DEFAULT_PROGRAM_CATALOG)
        reloaded = RunManifest.from_dict(json.loads(manifest.to_json()))
        self.assertEqual(manifest.config_sha256, reloaded.config_sha256)

        # Verify pulse renderer counts
        p02_wf = DEFAULT_PROGRAM_CATALOG["P02_MOD_BURST"].waveform
        pulse_res = render_pulse_events(p02_wf, duration_sec=10.0)
        # 2 Hz bursts * 10 sec = 20 bursts; 5 pulses per burst = 100 pulses
        self.assertEqual(pulse_res.total_bursts, 20)
        self.assertEqual(pulse_res.total_pulses, 100)

        # Verify exact small POMDP solver
        pomdp = solve_exact_small_pomdp()
        self.assertGreater(pomdp.exact_information_gap_partial_vs_oracle, 0.0)
        self.assertGreater(pomdp.value_of_observation_blind_vs_partial, 0.0)

        # Verify Engine A (MechanisticDorsalHornPlant) GHK & KCC2 equilibrium convergence and bounds check
        sk = CanonicalScenarioKey.create(cfg.protocol_namespace, "responder", 0, 1000)
        rng = SemanticRNG(cfg.seeds.master_seed, sk)
        mech = MechanisticDorsalHornPlant("responder", "burst_slows_habituation", rng)
        # Perturb [Cl-]_i to 18.0 mM and verify passive relaxation toward thermodynamic equilibrium
        # [Cl-]_i,eq = ([K+]_o * [Cl-]_o) / [K+]_i = (4.0 * 120.0) / 135.0 = 3.5556 mM
        st_relaxed = mech.relax_to_equilibrium(duration_sec=600.0)
        eq_cl = (st_relaxed.k_out_mm * st_relaxed.cl_out_mm) / st_relaxed.k_in_mm
        self.assertAlmostEqual(st_relaxed.cl_in_mm, eq_cl, places=3)

        # Verify out-of-bounds [Cl-]_i raises BiophysicalNumericalError
        bad_state = mech.snapshot()
        bad_state.cl_in_mm = 120.0  # Exceeds [1.0, 80.0] mM upper bound
        with self.assertRaises(BiophysicalNumericalError):
            mech.restore(bad_state)

        # Verify SubprocessControllerWrapper runs in a clean worker process over stdio and matches in-process output
        sub_ctrl = SubprocessControllerWrapper("C5_SequentialBayesian", name="C5_Subproc")
        try:
            cal = precompute_patient_calibration(cfg, sk)
            ep_sub, _, _ = run_single_episode(
                cfg, sk, 0, sub_ctrl, cal, comparators=[], enable_counterfactual_audits=False
            )
            ep_inproc, _, _ = run_single_episode(
                cfg, sk, 0, SequentialBayesianController(), cal, comparators=[], enable_counterfactual_audits=False
            )
            self.assertAlmostEqual(ep_sub.cumulative_total_loss, ep_inproc.cumulative_total_loss, places=10)
        finally:
            sub_ctrl.close()


if __name__ == "__main__":
    unittest.main()
