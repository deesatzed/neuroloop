"""
Executable Command-Line Interface for NeuroLoop v0.4.0.
Implements the target commands from NeuroLoop_Revised_Build_Plan.md Section 15:
  - `neuroloop validate-config <protocol.yaml>`
  - `neuroloop run --protocol <protocol.yaml> --output <runs/dir>`
  - `neuroloop replay <runs/dir/manifest.json>`
  - `neuroloop audit <runs/dir> --checks invariants,counterfactual,leakage`
  - `neuroloop report <runs/dir> --output <reports/dir>`
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

from neuroloop.config import ProtocolConfig, RunManifest
from neuroloop.contracts import DEFAULT_PROGRAM_CATALOG
from neuroloop.evaluation import (
    CounterfactualAuditRecord,
    EpisodeSummaryRecord,
    build_default_comparators,
    build_default_tournament_controllers,
    compute_paired_excess_summary,
    precompute_patient_calibration,
    run_single_episode,
)
from neuroloop.evaluation.cross_engine_transfer import run_cross_engine_and_frequency_challenges
from neuroloop.evaluation.decision_sufficiency import (
    estimate_sensor_information_gap,
    solve_exact_small_pomdp,
)
from neuroloop.evaluation.sensitivity import run_sensitivity_suite
from neuroloop.orchestrator import StepExecutionRecord, verify_public_observation_isolation
from neuroloop.randomness import CanonicalScenarioKey
from neuroloop.storage import RunStore
from neuroloop.viewer import generate_experiment_report
from neuroloop.viewer.dashboard import generate_interactive_dashboard


def execute_protocol_tournament(
    config: ProtocolConfig,
    include_ablations: bool = True,
    include_extended_analysis: bool = True,
) -> Tuple[
    RunManifest,
    List[EpisodeSummaryRecord],
    List[Tuple[EpisodeSummaryRecord, List[StepExecutionRecord]]],
    List[CounterfactualAuditRecord],
    List[Dict[str, Any]],
    Dict[str, Any],
]:
    manifest = RunManifest.build(config, DEFAULT_PROGRAM_CATALOG)
    controllers = build_default_tournament_controllers(include_ablations=include_ablations)
    comparators = build_default_comparators()

    episode_summaries: List[EpisodeSummaryRecord] = []
    step_records_by_ep: List[Tuple[EpisodeSummaryRecord, List[StepExecutionRecord]]] = []
    all_cf_records: List[CounterfactualAuditRecord] = []
    invalid_runs: List[Dict[str, Any]] = []

    local_ep_seq = 0
    total_scenarios = len(config.phenotypes) * config.seeds.episodes_per_phenotype
    scen_counter = 0
    for pheno in config.phenotypes:
        for ep_idx in range(config.seeds.episodes_per_phenotype):
            scen_counter += 1
            sys.stderr.write(
                f"\r[neuroloop] Running scenario {scen_counter}/{total_scenarios} "
                f"({pheno} ep {ep_idx + 1}/{config.seeds.episodes_per_phenotype})..."
            )
            sys.stderr.flush()
            skey = CanonicalScenarioKey.create(
                protocol_namespace=config.protocol_namespace,
                phenotype=pheno,
                episode_index=ep_idx,
                scenario_offset=config.seeds.scenario_offset,
            )
            cal_record = precompute_patient_calibration(config, skey, DEFAULT_PROGRAM_CATALOG)

            for ctrl in controllers:
                try:
                    ep_sum, steps, cfs = run_single_episode(
                        config=config,
                        scenario_key=skey,
                        local_episode_sequence=local_ep_seq,
                        controller=ctrl,
                        saved_calibration=cal_record,
                        comparators=comparators,
                        enable_counterfactual_audits=True,
                        program_catalog=DEFAULT_PROGRAM_CATALOG,
                    )
                    episode_summaries.append(ep_sum)
                    step_records_by_ep.append((ep_sum, steps))
                    all_cf_records.extend(cfs)
                except Exception as exc:
                    invalid_runs.append({
                        "scenario_digest": skey.scenario_digest,
                        "phenotype": pheno,
                        "episode_index": ep_idx,
                        "controller_name": ctrl.name,
                        "error_type": type(exc).__name__,
                        "error_message": str(exc),
                    })
                local_ep_seq += 1
    sys.stderr.write("\n")
    sys.stderr.flush()

    extra_analysis: Dict[str, Any] = {}
    if episode_summaries:
        paired_list: List[Dict[str, Any]] = []
        for pheno in config.phenotypes:
            try:
                p_stats = compute_paired_excess_summary(
                    episode_summaries,
                    candidate_name="C5_SequentialBayesian",
                    baseline_name="C2_CalibratedFixed",
                    phenotype=pheno,
                    alpha=config.evaluation.cvar_alpha,
                )
                p_stats["phenotype"] = pheno
                paired_list.append(p_stats)
            except Exception:
                pass
        extra_analysis["paired_comparisons"] = paired_list

    if include_extended_analysis:
        pomdp_res = solve_exact_small_pomdp()
        extra_analysis["exact_small_pomdp"] = dataclasses.asdict(pomdp_res)
        sensor_abl = estimate_sensor_information_gap(config, n_episodes_per_phenotype=min(8, config.seeds.episodes_per_phenotype))
        extra_analysis["sensor_ablations"] = [dataclasses.asdict(x) for x in sensor_abl]
        transfer_rows = run_cross_engine_and_frequency_challenges(
            config, n_episodes_per_phenotype=min(10, config.seeds.episodes_per_phenotype)
        )
        extra_analysis["transfer_challenges"] = [r.to_dict() for r in transfer_rows]

    return (
        manifest,
        episode_summaries,
        step_records_by_ep,
        all_cf_records,
        invalid_runs,
        extra_analysis,
    )


def cmd_validate_config(args: argparse.Namespace) -> int:
    cfg = ProtocolConfig.load_file(args.protocol)
    print(f"VALID: protocol_id={cfg.protocol_id} version={cfg.protocol_version} sha256={cfg.config_sha256()}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = ProtocolConfig.load_file(args.protocol)
    manifest, episodes, steps_by_ep, cfs, invalid, extra = execute_protocol_tournament(
        cfg,
        include_ablations=not args.skip_ablations,
        include_extended_analysis=not args.skip_extended,
    )
    store = RunStore(args.output)
    checksums = store.write_run_artifacts(manifest, episodes, steps_by_ep, cfs, invalid, extra)
    print(f"RUN COMPLETE: {len(episodes)} episodes written to {store.output_dir}")
    print(f"episodes_sha256={checksums['episodes_sha256']}")
    return 0 if not invalid else 1


def cmd_replay(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    run_dir = manifest_path.parent
    store = RunStore(run_dir)
    manifest = store.read_manifest()
    orig_checksums = json.loads((run_dir / "checksums.json").read_text(encoding="utf-8"))

    _, episodes, _, _, invalid, _ = execute_protocol_tournament(
        manifest.resolved_config,
        include_ablations=True,
        include_extended_analysis=False,
    )
    replayed_ep_bytes = json.dumps(
        [e.to_dict() for e in episodes], indent=2, sort_keys=True, allow_nan=False
    ).encode("utf-8")
    replayed_sha = hashlib.sha256(replayed_ep_bytes).hexdigest()

    if replayed_sha != orig_checksums["episodes_sha256"]:
        print(f"REPLAY MISMATCH: expected {orig_checksums['episodes_sha256']}, got {replayed_sha}")
        return 1
    print(f"REPLAY BITWISE VERIFIED: episodes_sha256={replayed_sha}")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    run_dir = Path(args.run_dir)
    pub_path = run_dir / "public_events.jsonl"
    priv_path = run_dir / "privileged_events.jsonl"
    cf_path = run_dir / "counterfactuals.json"
    invalid_path = run_dir / "invalid_runs.json"

    from neuroloop.contracts import PublicObservation

    pub_count = 0
    with pub_path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            obs = PublicObservation.from_dict(row["observation"])
            verify_public_observation_isolation(obs)
            pub_count += 1

    # Check dose vs exposure consistency in privileged events
    priv_count = 0
    with priv_path.open("r", encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if row["delivered_intensity"] == 0.0 and row["stimulation_effort"] != 0.0:
                raise AssertionError(f"Zero delivered_intensity had nonzero effort: {row}")
            priv_count += 1

    cfs = json.loads(cf_path.read_text(encoding="utf-8"))
    for cf in cfs:
        if cf["calibrated_comparator_program"] == "uncalibrated":
            raise AssertionError(f"Uncalibrated comparator detected at audit step: {cf}")

    invalids = json.loads(invalid_path.read_text(encoding="utf-8"))
    if invalids:
        raise AssertionError(f"Invalid runs present in ledger: {invalids}")

    print(
        f"AUDIT PASSED ({args.checks}): verified {pub_count} public events, "
        f"{priv_count} privileged events, and {len(cfs)} counterfactual records."
    )
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    summary = generate_experiment_report(args.run_dir, args.output)
    print(
        f"REPORT GENERATED: gate={summary['engineering_gate_status']} "
        f"outcome={summary['research_outcome']} -> {Path(args.output) / 'report.md'}"
    )
    return 0


def cmd_sensitivity(args: argparse.Namespace) -> int:
    cfg = ProtocolConfig.load_file(args.protocol)
    run_sensitivity_suite(cfg, args.output, n_episodes_per_phenotype=args.episodes)
    print(f"SENSITIVITY SUITE COMPLETE -> {Path(args.output) / 'sensitivity_matrix.md'}")
    return 0


def cmd_dashboard(args: argparse.Namespace) -> int:
    out_path = generate_interactive_dashboard(args.workspace, args.output)
    print(f"DASHBOARD GENERATED -> {out_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="neuroloop", description="NeuroLoop v0.4.0 Research Instrument CLI")
    sub = p.add_subparsers(dest="subcommand", required=True)

    p_val = sub.add_parser("validate-config", help="Validate a protocol YAML/JSON file")
    p_val.add_argument("protocol", help="Path to protocol configuration file")
    p_val.set_defaults(func=cmd_validate_config)

    p_run = sub.add_parser("run", help="Run a closed-loop neuromodulation experiment")
    p_run.add_argument("--protocol", required=True, help="Path to protocol configuration file")
    p_run.add_argument("--output", required=True, help="Directory for output run artifacts")
    p_run.add_argument("--skip-ablations", action="store_true", help="Skip ablation controllers")
    p_run.add_argument("--skip-extended", action="store_true", help="Skip extended transfer/sensor analysis")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("replay", help="Replay a run from its manifest.json and verify bitwise match")
    p_rep.add_argument("manifest", help="Path to runs/<name>/manifest.json")
    p_rep.set_defaults(func=cmd_replay)

    p_aud = sub.add_parser("audit", help="Audit stored run records for invariants, counterfactuals, and leakage")
    p_aud.add_argument("run_dir", help="Path to run output directory")
    p_aud.add_argument("--checks", default="invariants,counterfactual,leakage", help="Comma-separated check list")
    p_aud.set_defaults(func=cmd_audit)

    p_rpt = sub.add_parser("report", help="Generate Markdown and JSON scientific reports from stored run records")
    p_rpt.add_argument("run_dir", help="Path to run output directory")
    p_rpt.add_argument("--output", required=True, help="Path to report output directory")
    p_rpt.set_defaults(func=cmd_report)

    p_sens = sub.add_parser("sensitivity", help="Run 2x2x2 factorial sensitivity matrix and report-delay sweep")
    p_sens.add_argument("--protocol", default="protocols/development.yaml", help="Base protocol file")
    p_sens.add_argument("--output", default="reports", help="Output directory for sensitivity_matrix.md/.json")
    p_sens.add_argument("--episodes", type=int, default=10, help="Episodes per phenotype per cell")
    p_sens.set_defaults(func=cmd_sensitivity)

    p_dash = sub.add_parser("dashboard", help="Generate standalone interactive HTML/SVG dashboard")
    p_dash.add_argument("--workspace", default=".", help="Workspace root directory")
    p_dash.add_argument("--output", default="reports/dashboard.html", help="Output HTML file path")
    p_dash.set_defaults(func=cmd_dashboard)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
