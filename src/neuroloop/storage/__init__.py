"""
Append-Only Event Storage, Separate Public/Privileged Streams, Invalid-Run Ledger,
and Indexed SQLite Telemetry Sink for NeuroLoop v0.4.0.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from neuroloop.config import RunManifest
from neuroloop.evaluation import CounterfactualAuditRecord, EpisodeSummaryRecord
from neuroloop.orchestrator import StepExecutionRecord, verify_public_observation_isolation


class RunStore:
    """
    Persists all artifacts of an experiment run into a directory:
      - `manifest.json`: Resolved configuration, hashes, program catalog, and provenance.
      - `public_events.jsonl`: Strictly public observation and action records (zero hidden variables).
      - `privileged_events.jsonl`: Step-level hidden plant states, actuator outputs, and losses.
      - `episodes.json`: Multi-ledger episode summaries.
      - `counterfactuals.json`: Checkpoint counterfactual fork records.
      - `invalid_runs.json`: Explicit instrument-failure ledger (never silently dropped).
      - `telemetry.sqlite`: Relational SQLite database for structured SQL assertions.
    """

    def __init__(self, output_dir: str | Path) -> None:
        self._dir = Path(output_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._public_path = self._dir / "public_events.jsonl"
        self._priv_path = self._dir / "privileged_events.jsonl"
        self._episodes_path = self._dir / "episodes.json"
        self._cf_path = self._dir / "counterfactuals.json"
        self._invalid_path = self._dir / "invalid_runs.json"
        self._manifest_path = self._dir / "manifest.json"
        self._sqlite_path = self._dir / "telemetry.sqlite"

    @property
    def output_dir(self) -> Path:
        return self._dir

    def write_manifest(self, manifest: RunManifest) -> None:
        self._manifest_path.write_text(manifest.to_json(), encoding="utf-8")

    def read_manifest(self) -> RunManifest:
        data = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        return RunManifest.from_dict(data)

    def write_run_artifacts(
        self,
        manifest: RunManifest,
        episode_summaries: Sequence[EpisodeSummaryRecord],
        step_records_by_episode: Sequence[tuple[EpisodeSummaryRecord, Sequence[StepExecutionRecord]]],
        counterfactual_records: Sequence[CounterfactualAuditRecord],
        invalid_runs: Sequence[Mapping[str, Any]],
        extra_metadata: Mapping[str, Any] | None = None,
    ) -> Dict[str, str]:
        self.write_manifest(manifest)

        with self._public_path.open("w", encoding="utf-8") as pub_f, self._priv_path.open(
            "w", encoding="utf-8"
        ) as priv_f:
            for ep_sum, steps in step_records_by_episode:
                for st in steps:
                    verify_public_observation_isolation(st.observation_before)
                    pub_row = {
                        "local_episode_sequence": ep_sum.local_episode_sequence,
                        "controller_name": ep_sum.controller_name,
                        "step_k": st.step_k,
                        "time_sec": st.time_sec,
                        "observation": st.observation_before.to_dict(),
                        "proposed_action": {
                            "stimulation": st.proposed_action.stimulation.value,
                            "feedback": st.proposed_action.feedback.value,
                            "target_program_id": st.proposed_action.target_program_id,
                            "prompt_id": st.proposed_action.prompt_id,
                            "observation_sequence": st.proposed_action.observation_sequence,
                        },
                    }
                    pub_f.write(json.dumps(pub_row, sort_keys=True, allow_nan=False) + "\n")

                    priv_row = {
                        "scenario_digest": ep_sum.scenario_digest,
                        "phenotype": ep_sum.phenotype,
                        "episode_index": ep_sum.episode_index,
                        "controller_name": ep_sum.controller_name,
                        "step_k": st.step_k,
                        "time_sec": st.time_sec,
                        "proposed_stimulation": st.proposed_action.stimulation.value,
                        "proposed_target": st.proposed_action.target_program_id,
                        "approved_program_id": st.supervision.approved_program.program_id,
                        "feedback_requested": st.supervision.feedback_requested,
                        "proposal_violated": st.supervision.proposal_violated,
                        "violation_reason": st.supervision.violation_reason,
                        "fault_latched_before": st.supervision.fault_latched_before,
                        "fault_latched_after": st.supervision.fault_latched_after,
                        "rearmed_this_step": st.supervision.rearmed_this_step,
                        "stop_latency_ms": st.supervision.stop_latency_ms,
                        "requested_intensity": st.exposure.requested_intensity,
                        "delivered_intensity": st.exposure.delivered_intensity,
                        "effective_current_ma": st.exposure.effective_current_ma,
                        "output_voltage_v": st.exposure.output_voltage_v,
                        "contact_factor": st.exposure.contact_factor,
                        "delivery_status": st.exposure.delivery_status.value,
                        "delivery_confirmed": st.exposure.delivery_confirmed,
                        "stimulation_effort": st.exposure.stimulation_effort,
                        "true_latent_pain": st.plant_output.true_latent_pain,
                        "true_functional_impairment": st.plant_output.true_functional_impairment,
                        "analgesic_trace": st.plant_output.analgesic_trace,
                        "habituation": st.plant_output.habituation,
                        "delayed_sensitization": st.plant_output.delayed_sensitization,
                        "query_burden": st.plant_output.query_burden,
                        "mechanistic_wdr_hz": st.plant_output.mechanistic_wdr_hz,
                        "intracellular_cl_mm": st.plant_output.intracellular_cl_mm,
                        "e_gaba_mv": st.plant_output.e_gaba_mv,
                        "observed_pain_report": st.observation_after.patient.last_pain_report,
                        "report_status": st.observation_after.patient.report_status.value,
                        "clinical_loss": st.loss.clinical_loss,
                        "safety_loss": st.loss.safety_loss,
                        "total_loss": st.loss.total_loss,
                        "controller_belief": st.controller_belief,
                    }
                    priv_f.write(json.dumps(priv_row, sort_keys=True, allow_nan=False) + "\n")

        ep_dicts = [ep.to_dict() for ep in episode_summaries]
        self._episodes_path.write_text(
            json.dumps(ep_dicts, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )

        cf_dicts = [asdict(cf) for cf in counterfactual_records]
        self._cf_path.write_text(
            json.dumps(cf_dicts, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )

        self._invalid_path.write_text(
            json.dumps(list(invalid_runs), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8"
        )

        if extra_metadata is not None:
            (self._dir / "extra_analysis.json").write_text(
                json.dumps(dict(extra_metadata), indent=2, sort_keys=True, allow_nan=False),
                encoding="utf-8",
            )

        self._populate_sqlite(episode_summaries, counterfactual_records)

        checksums = {
            "manifest_sha256": hashlib.sha256(self._manifest_path.read_bytes()).hexdigest(),
            "public_events_sha256": hashlib.sha256(self._public_path.read_bytes()).hexdigest(),
            "privileged_events_sha256": hashlib.sha256(self._priv_path.read_bytes()).hexdigest(),
            "episodes_sha256": hashlib.sha256(self._episodes_path.read_bytes()).hexdigest(),
            "counterfactuals_sha256": hashlib.sha256(self._cf_path.read_bytes()).hexdigest(),
        }
        (self._dir / "checksums.json").write_text(
            json.dumps(checksums, indent=2, sort_keys=True), encoding="utf-8"
        )
        return checksums

    def _populate_sqlite(
        self,
        episodes: Sequence[EpisodeSummaryRecord],
        counterfactuals: Sequence[CounterfactualAuditRecord],
    ) -> None:
        if self._sqlite_path.exists():
            self._sqlite_path.unlink()
        conn = sqlite3.connect(str(self._sqlite_path))
        try:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE episodes (
                    scenario_digest TEXT NOT NULL,
                    phenotype TEXT NOT NULL,
                    episode_index INTEGER NOT NULL,
                    controller_name TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    pain_time_integral REAL NOT NULL,
                    cumulative_clinical_loss REAL NOT NULL,
                    cumulative_safety_loss REAL NOT NULL,
                    cumulative_total_loss REAL NOT NULL,
                    delivered_effort_integral REAL NOT NULL,
                    total_queries_requested INTEGER NOT NULL,
                    confirmed_active_delivery_steps INTEGER NOT NULL,
                    proposal_violations INTEGER NOT NULL,
                    decision_violation_rate REAL NOT NULL,
                    posterior_update_count INTEGER NOT NULL,
                    calibrated_program_id TEXT
                )
                """
            )
            for ep in episodes:
                cur.execute(
                    """
                    INSERT INTO episodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ep.scenario_digest,
                        ep.phenotype,
                        ep.episode_index,
                        ep.controller_name,
                        ep.total_steps,
                        ep.pain_time_integral,
                        ep.cumulative_clinical_loss,
                        ep.cumulative_safety_loss,
                        ep.cumulative_total_loss,
                        ep.delivered_effort_integral,
                        ep.total_queries_requested,
                        ep.confirmed_active_delivery_steps,
                        ep.proposal_violations,
                        ep.decision_violation_rate,
                        ep.posterior_update_count,
                        ep.calibrated_program_id,
                    ),
                )
            cur.execute(
                """
                CREATE TABLE counterfactuals (
                    scenario_digest TEXT NOT NULL,
                    phenotype TEXT NOT NULL,
                    episode_index INTEGER NOT NULL,
                    candidate_controller TEXT NOT NULL,
                    checkpoint_step_k INTEGER NOT NULL,
                    horizon_steps INTEGER NOT NULL,
                    candidate_mean_loss REAL NOT NULL,
                    restricted_comparator_excess_loss REAL NOT NULL,
                    selected_best_comparator TEXT NOT NULL,
                    calibrated_comparator_program TEXT NOT NULL
                )
                """
            )
            for cf in counterfactuals:
                cur.execute(
                    """
                    INSERT INTO counterfactuals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cf.scenario_digest,
                        cf.phenotype,
                        cf.episode_index,
                        cf.candidate_controller,
                        cf.checkpoint_step_k,
                        cf.horizon_steps,
                        cf.candidate_mean_loss,
                        cf.restricted_comparator_excess_loss,
                        cf.selected_best_comparator,
                        cf.calibrated_comparator_program,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
