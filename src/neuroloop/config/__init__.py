"""
Strict configuration validation and resolved manifest provenance for NeuroLoop v0.4.0.
Rejects unknown keys, duplicate keys, and non-finite values.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from neuroloop.contracts import ConfigurationError, require_finite, require_int_non_negative, require_range


def _strict_object_pairs_hook(pairs: List[Tuple[str, Any]]) -> Dict[str, Any]:
    """Rejects duplicate keys in JSON/YAML-subset configuration files."""
    result: Dict[str, Any] = {}
    for k, v in pairs:
        if k in result:
            raise ConfigurationError(f"Duplicate configuration key detected: {k!r}")
        result[k] = v
    return result


def _reject_non_finite_constant(val: str) -> Any:
    raise ConfigurationError(f"Non-finite constant {val!r} is forbidden in configuration.")


def _validate_exact_keys(data: Mapping[str, Any], allowed: Sequence[str], section: str) -> None:
    if not isinstance(data, Mapping):
        raise ConfigurationError(f"Section '{section}' must be a mapping, got {type(data).__name__}")
    allowed_set = set(allowed)
    actual_set = set(data.keys())
    unknown = sorted(actual_set - allowed_set)
    missing = sorted(allowed_set - actual_set)
    if unknown:
        raise ConfigurationError(f"Unknown keys in '{section}': {unknown}")
    if missing:
        raise ConfigurationError(f"Missing required keys in '{section}': {missing}")


@dataclass(frozen=True)
class TimingConfig:
    macro_step_dt_sec: float
    fast_tick_ms: int
    episode_steps: int
    calibration_steps: int
    report_delay_steps: int
    recovery_tail_steps: int
    rearm_required_clean_steps: int

    def __post_init__(self) -> None:
        require_range(self.macro_step_dt_sec, "macro_step_dt_sec", 1.0, 3600.0)
        require_int_non_negative(self.fast_tick_ms, "fast_tick_ms")
        if self.fast_tick_ms <= 0 or int(round(self.macro_step_dt_sec * 1000)) % self.fast_tick_ms != 0:
            raise ConfigurationError("macro_step_dt_sec (in ms) must be an exact positive multiple of fast_tick_ms.")
        require_int_non_negative(self.episode_steps, "episode_steps")
        if self.episode_steps < 6:
            raise ConfigurationError("episode_steps must be >= 6.")
        require_int_non_negative(self.calibration_steps, "calibration_steps")
        require_int_non_negative(self.report_delay_steps, "report_delay_steps")
        require_int_non_negative(self.recovery_tail_steps, "recovery_tail_steps")
        require_int_non_negative(self.rearm_required_clean_steps, "rearm_required_clean_steps")
        if self.rearm_required_clean_steps < 1:
            raise ConfigurationError("rearm_required_clean_steps must be >= 1.")


@dataclass(frozen=True)
class SeedConfig:
    master_seed: int
    episodes_per_phenotype: int
    scenario_offset: int

    def __post_init__(self) -> None:
        require_int_non_negative(self.master_seed, "master_seed")
        require_int_non_negative(self.episodes_per_phenotype, "episodes_per_phenotype")
        if self.episodes_per_phenotype < 1:
            raise ConfigurationError("episodes_per_phenotype must be >= 1.")
        require_int_non_negative(self.scenario_offset, "scenario_offset")


@dataclass(frozen=True)
class CounterfactualConfig:
    audit_steps: Tuple[int, ...]
    horizons_steps: Tuple[int, ...]
    num_noise_replicates: int
    discount_gamma: float

    def __post_init__(self) -> None:
        for s in self.audit_steps:
            require_int_non_negative(s, "audit_steps item")
        for h in self.horizons_steps:
            require_int_non_negative(h, "horizons_steps item")
            if h < 1:
                raise ConfigurationError("Counterfactual horizon must be >= 1.")
        require_int_non_negative(self.num_noise_replicates, "num_noise_replicates")
        if self.num_noise_replicates < 1:
            raise ConfigurationError("num_noise_replicates must be >= 1.")
        require_range(self.discount_gamma, "discount_gamma", 0.01, 1.0)


@dataclass(frozen=True)
class SupervisorConfig:
    max_safe_impedance_ohm: float
    max_intensity_under_fault: float
    latch_on_fault: bool

    def __post_init__(self) -> None:
        require_range(self.max_safe_impedance_ohm, "max_safe_impedance_ohm", 1000.0, 1e6)
        require_range(self.max_intensity_under_fault, "max_intensity_under_fault", 0.0, 1.0)
        if not isinstance(self.latch_on_fault, bool):
            raise ConfigurationError("latch_on_fault must be a boolean.")


@dataclass(frozen=True)
class ActuatorConfig:
    max_current_ma: float
    compliance_voltage_v: float
    nominal_impedance_ohm: float
    toy_resistive_ohm: float

    def __post_init__(self) -> None:
        require_range(self.max_current_ma, "max_current_ma", 0.1, 100.0)
        require_range(self.compliance_voltage_v, "compliance_voltage_v", 1.0, 200.0)
        require_range(self.nominal_impedance_ohm, "nominal_impedance_ohm", 100.0, 1e6)
        require_range(self.toy_resistive_ohm, "toy_resistive_ohm", 100.0, 1e6)


@dataclass(frozen=True)
class LossWeightsConfig:
    w_latent_pain: float
    w_functional_impairment: float
    w_stimulation_effort: float
    w_query_burden_base: float
    w_proposal_violation: float
    w_fault_stimulation: float
    w_worsening_escalation: float

    def __post_init__(self) -> None:
        for fname in (
            "w_latent_pain",
            "w_functional_impairment",
            "w_stimulation_effort",
            "w_query_burden_base",
            "w_proposal_violation",
            "w_fault_stimulation",
            "w_worsening_escalation",
        ):
            require_range(getattr(self, fname), fname, 0.0, 1000.0)


@dataclass(frozen=True)
class EvaluationConfig:
    cvar_alpha: float
    exploratory_relative_benefit_pct: float
    nonresponder_cvar_abs_margin: float
    worsening_cvar_abs_margin: float

    def __post_init__(self) -> None:
        require_range(self.cvar_alpha, "cvar_alpha", 0.01, 0.999)
        require_range(self.exploratory_relative_benefit_pct, "exploratory_relative_benefit_pct", 0.0, 100.0)
        require_range(self.nonresponder_cvar_abs_margin, "nonresponder_cvar_abs_margin", 0.0, 1000.0)
        require_range(self.worsening_cvar_abs_margin, "worsening_cvar_abs_margin", 0.0, 1000.0)


ALLOWED_ENGINE_MODES = ("engine_b_phenomenological", "engine_a_mechanistic", "engine_a_fast_surrogate")
ALLOWED_ACTUATOR_MODES = ("normalized", "toy_resistive")
ALLOWED_ISOLATION_MODES = ("trusted_in_process", "release_subprocess")
ALLOWED_FREQ_MODES = ("burst_slows_habituation", "frequency_neutral", "burst_accelerates_habituation")
ALLOWED_PHENOTYPES = (
    "responder",
    "nonresponder",
    "delayed_worsening",
    "null_effect",
    "baseline_flare",
    "random_fault_window",
)


@dataclass(frozen=True)
class ProtocolConfig:
    protocol_id: str
    protocol_version: str
    protocol_namespace: str
    freeze_status: str
    claim_tier: str
    engine_mode: str
    actuator_mode: str
    isolation_mode: str
    frequency_response_mode: str
    timing: TimingConfig
    seeds: SeedConfig
    phenotypes: Tuple[str, ...]
    counterfactual: CounterfactualConfig
    supervisor: SupervisorConfig
    actuator: ActuatorConfig
    loss_weights: LossWeightsConfig
    evaluation: EvaluationConfig

    def __post_init__(self) -> None:
        for s_field in ("protocol_id", "protocol_version", "protocol_namespace", "freeze_status", "claim_tier"):
            val = getattr(self, s_field)
            if not isinstance(val, str) or not val.strip():
                raise ConfigurationError(f"{s_field} must be a non-empty string.")
        if self.claim_tier != "SIMULATION_ONLY":
            raise ConfigurationError("Only claim_tier='SIMULATION_ONLY' is permitted in software experiments.")
        if self.engine_mode not in ALLOWED_ENGINE_MODES:
            raise ConfigurationError(f"Unsupported engine_mode: {self.engine_mode!r}")
        if self.actuator_mode not in ALLOWED_ACTUATOR_MODES:
            raise ConfigurationError(f"Unsupported actuator_mode: {self.actuator_mode!r}")
        if self.isolation_mode not in ALLOWED_ISOLATION_MODES:
            raise ConfigurationError(f"Unsupported isolation_mode: {self.isolation_mode!r}")
        if self.frequency_response_mode not in ALLOWED_FREQ_MODES:
            raise ConfigurationError(f"Unsupported frequency_response_mode: {self.frequency_response_mode!r}")
        if not self.phenotypes:
            raise ConfigurationError("phenotypes list cannot be empty.")
        for p in self.phenotypes:
            if p not in ALLOWED_PHENOTYPES:
                raise ConfigurationError(f"Unknown phenotype: {p!r}")

    def to_dict(self) -> Dict[str, Any]:
        raw = asdict(self)
        raw["phenotypes"] = list(self.phenotypes)
        raw["counterfactual"]["audit_steps"] = list(self.counterfactual.audit_steps)
        raw["counterfactual"]["horizons_steps"] = list(self.counterfactual.horizons_steps)
        return raw

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)

    def config_sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ProtocolConfig:
        _validate_exact_keys(
            data,
            (
                "protocol_id",
                "protocol_version",
                "protocol_namespace",
                "freeze_status",
                "claim_tier",
                "engine_mode",
                "actuator_mode",
                "isolation_mode",
                "frequency_response_mode",
                "timing",
                "seeds",
                "phenotypes",
                "counterfactual",
                "supervisor",
                "actuator",
                "loss_weights",
                "evaluation",
            ),
            "root",
        )
        t_raw = data["timing"]
        _validate_exact_keys(
            t_raw,
            (
                "macro_step_dt_sec",
                "fast_tick_ms",
                "episode_steps",
                "calibration_steps",
                "report_delay_steps",
                "recovery_tail_steps",
                "rearm_required_clean_steps",
            ),
            "timing",
        )
        s_raw = data["seeds"]
        _validate_exact_keys(s_raw, ("master_seed", "episodes_per_phenotype", "scenario_offset"), "seeds")

        cf_raw = data["counterfactual"]
        _validate_exact_keys(
            cf_raw,
            ("audit_steps", "horizons_steps", "num_noise_replicates", "discount_gamma"),
            "counterfactual",
        )
        sup_raw = data["supervisor"]
        _validate_exact_keys(
            sup_raw,
            ("max_safe_impedance_ohm", "max_intensity_under_fault", "latch_on_fault"),
            "supervisor",
        )
        act_raw = data["actuator"]
        _validate_exact_keys(
            act_raw,
            ("max_current_ma", "compliance_voltage_v", "nominal_impedance_ohm", "toy_resistive_ohm"),
            "actuator",
        )
        lw_raw = data["loss_weights"]
        _validate_exact_keys(
            lw_raw,
            (
                "w_latent_pain",
                "w_functional_impairment",
                "w_stimulation_effort",
                "w_query_burden_base",
                "w_proposal_violation",
                "w_fault_stimulation",
                "w_worsening_escalation",
            ),
            "loss_weights",
        )
        ev_raw = data["evaluation"]
        _validate_exact_keys(
            ev_raw,
            (
                "cvar_alpha",
                "exploratory_relative_benefit_pct",
                "nonresponder_cvar_abs_margin",
                "worsening_cvar_abs_margin",
            ),
            "evaluation",
        )

        if not isinstance(data["phenotypes"], list):
            raise ConfigurationError("'phenotypes' must be a list of strings.")
        if not isinstance(cf_raw["audit_steps"], list) or not isinstance(cf_raw["horizons_steps"], list):
            raise ConfigurationError("'audit_steps' and 'horizons_steps' must be lists of integers.")

        try:
            return cls(
                protocol_id=data["protocol_id"],
                protocol_version=data["protocol_version"],
                protocol_namespace=data["protocol_namespace"],
                freeze_status=data["freeze_status"],
                claim_tier=data["claim_tier"],
                engine_mode=data["engine_mode"],
                actuator_mode=data["actuator_mode"],
                isolation_mode=data["isolation_mode"],
                frequency_response_mode=data["frequency_response_mode"],
                timing=TimingConfig(
                    macro_step_dt_sec=require_finite(t_raw["macro_step_dt_sec"], "macro_step_dt_sec"),
                    fast_tick_ms=require_int_non_negative(t_raw["fast_tick_ms"], "fast_tick_ms"),
                    episode_steps=require_int_non_negative(t_raw["episode_steps"], "episode_steps"),
                    calibration_steps=require_int_non_negative(t_raw["calibration_steps"], "calibration_steps"),
                    report_delay_steps=require_int_non_negative(t_raw["report_delay_steps"], "report_delay_steps"),
                    recovery_tail_steps=require_int_non_negative(t_raw["recovery_tail_steps"], "recovery_tail_steps"),
                    rearm_required_clean_steps=require_int_non_negative(
                        t_raw["rearm_required_clean_steps"], "rearm_required_clean_steps"
                    ),
                ),
                seeds=SeedConfig(
                    master_seed=require_int_non_negative(s_raw["master_seed"], "master_seed"),
                    episodes_per_phenotype=require_int_non_negative(
                        s_raw["episodes_per_phenotype"], "episodes_per_phenotype"
                    ),
                    scenario_offset=require_int_non_negative(s_raw["scenario_offset"], "scenario_offset"),
                ),
                phenotypes=tuple(str(p) for p in data["phenotypes"]),
                counterfactual=CounterfactualConfig(
                    audit_steps=tuple(require_int_non_negative(x, "audit_step") for x in cf_raw["audit_steps"]),
                    horizons_steps=tuple(
                        require_int_non_negative(x, "horizon_step") for x in cf_raw["horizons_steps"]
                    ),
                    num_noise_replicates=require_int_non_negative(
                        cf_raw["num_noise_replicates"], "num_noise_replicates"
                    ),
                    discount_gamma=require_finite(cf_raw["discount_gamma"], "discount_gamma"),
                ),
                supervisor=SupervisorConfig(
                    max_safe_impedance_ohm=require_finite(
                        sup_raw["max_safe_impedance_ohm"], "max_safe_impedance_ohm"
                    ),
                    max_intensity_under_fault=require_finite(
                        sup_raw["max_intensity_under_fault"], "max_intensity_under_fault"
                    ),
                    latch_on_fault=sup_raw["latch_on_fault"],
                ),
                actuator=ActuatorConfig(
                    max_current_ma=require_finite(act_raw["max_current_ma"], "max_current_ma"),
                    compliance_voltage_v=require_finite(act_raw["compliance_voltage_v"], "compliance_voltage_v"),
                    nominal_impedance_ohm=require_finite(act_raw["nominal_impedance_ohm"], "nominal_impedance_ohm"),
                    toy_resistive_ohm=require_finite(act_raw["toy_resistive_ohm"], "toy_resistive_ohm"),
                ),
                loss_weights=LossWeightsConfig(
                    w_latent_pain=require_finite(lw_raw["w_latent_pain"], "w_latent_pain"),
                    w_functional_impairment=require_finite(
                        lw_raw["w_functional_impairment"], "w_functional_impairment"
                    ),
                    w_stimulation_effort=require_finite(lw_raw["w_stimulation_effort"], "w_stimulation_effort"),
                    w_query_burden_base=require_finite(lw_raw["w_query_burden_base"], "w_query_burden_base"),
                    w_proposal_violation=require_finite(lw_raw["w_proposal_violation"], "w_proposal_violation"),
                    w_fault_stimulation=require_finite(lw_raw["w_fault_stimulation"], "w_fault_stimulation"),
                    w_worsening_escalation=require_finite(
                        lw_raw["w_worsening_escalation"], "w_worsening_escalation"
                    ),
                ),
                evaluation=EvaluationConfig(
                    cvar_alpha=require_finite(ev_raw["cvar_alpha"], "cvar_alpha"),
                    exploratory_relative_benefit_pct=require_finite(
                        ev_raw["exploratory_relative_benefit_pct"], "exploratory_relative_benefit_pct"
                    ),
                    nonresponder_cvar_abs_margin=require_finite(
                        ev_raw["nonresponder_cvar_abs_margin"], "nonresponder_cvar_abs_margin"
                    ),
                    worsening_cvar_abs_margin=require_finite(
                        ev_raw["worsening_cvar_abs_margin"], "worsening_cvar_abs_margin"
                    ),
                ),
            )
        except Exception as exc:
            if isinstance(exc, ConfigurationError):
                raise
            raise ConfigurationError(str(exc)) from exc

    @classmethod
    def load_file(cls, path: str | Path) -> ProtocolConfig:
        p = Path(path)
        if not p.exists():
            raise ConfigurationError(f"Configuration file not found: {p}")
        text = p.read_text(encoding="utf-8")
        return cls.loads(text)

    @classmethod
    def loads(cls, text: str) -> ProtocolConfig:
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_strict_object_pairs_hook,
                parse_constant=_reject_non_finite_constant,
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise ConfigurationError(f"Failed to parse protocol configuration: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ConfigurationError("Protocol root must be a JSON/YAML object.")
        return cls.from_mapping(parsed)


def _detect_git_provenance(repo_dir: Path) -> Tuple[str, str]:
    try:
        commit = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir, stderr=subprocess.DEVNULL)
            .decode("utf-8")
            .strip()
        )
        diff = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo_dir, stderr=subprocess.DEVNULL)
        dirty_hash = hashlib.sha256(diff).hexdigest()[:16] if diff.strip() else "clean"
        return commit, dirty_hash
    except Exception:
        return "no_git_repo", "untracked"


@dataclass(frozen=True)
class RunManifest:
    """
    Complete provenance manifest preserving resolved configuration, program catalog,
    equation registry hash, and platform metadata.
    """
    manifest_version: str
    config_sha256: str
    resolved_config: ProtocolConfig
    program_catalog: Dict[str, Any]
    equation_registry_sha256: str
    git_commit: str
    git_dirty_hash: str
    python_version: str
    platform_str: str
    rng_schema_version: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "config_sha256": self.config_sha256,
            "resolved_config": self.resolved_config.to_dict(),
            "program_catalog": self.program_catalog,
            "equation_registry_sha256": self.equation_registry_sha256,
            "git_commit": self.git_commit,
            "git_dirty_hash": self.git_dirty_hash,
            "python_version": self.python_version,
            "platform_str": self.platform_str,
            "rng_schema_version": self.rng_schema_version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, allow_nan=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RunManifest:
        cfg = ProtocolConfig.from_mapping(data["resolved_config"])
        if cfg.config_sha256() != data["config_sha256"]:
            raise ConfigurationError("Manifest config_sha256 mismatch against resolved_config.")
        return cls(
            manifest_version=str(data["manifest_version"]),
            config_sha256=str(data["config_sha256"]),
            resolved_config=cfg,
            program_catalog=dict(data["program_catalog"]),
            equation_registry_sha256=str(data["equation_registry_sha256"]),
            git_commit=str(data["git_commit"]),
            git_dirty_hash=str(data["git_dirty_hash"]),
            python_version=str(data["python_version"]),
            platform_str=str(data["platform_str"]),
            rng_schema_version=str(data["rng_schema_version"]),
        )

    @classmethod
    def build(
        cls,
        config: ProtocolConfig,
        program_catalog: Mapping[str, Any],
        repo_root: Optional[Path] = None,
    ) -> RunManifest:
        root = repo_root or Path(__file__).resolve().parents[3]
        eq_path = root / "models" / "assumptions" / "equation_registry.json"
        if eq_path.exists():
            eq_hash = hashlib.sha256(eq_path.read_bytes()).hexdigest()
        else:
            eq_hash = "missing_equation_registry"
        commit, dirty = _detect_git_provenance(root)
        cat_dict: Dict[str, Any] = {}
        for pid, spec in sorted(program_catalog.items()):
            cat_dict[pid] = asdict(spec)
        return cls(
            manifest_version="0.4.0",
            config_sha256=config.config_sha256(),
            resolved_config=config,
            program_catalog=cat_dict,
            equation_registry_sha256=eq_hash,
            git_commit=commit,
            git_dirty_hash=dirty,
            python_version=sys.version.split()[0],
            platform_str=platform.platform(),
            rng_schema_version="sha256_semantic_v1",
        )
