"""
Clean subprocess worker entry point for `SubprocessControllerWrapper` (`release_subprocess` mode).
Contains ZERO plant, supervisor, or evaluator objects in its process memory space.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict

from neuroloop.contracts import PublicObservation
from neuroloop.controllers import (
    AbstractController,
    CalibratedFixedController,
    ConservativeRulesController,
    FixedProgramController,
    HeuristicThreeHypothesisController,
    OffController,
)
from neuroloop.controllers.bayesian import SequentialBayesianController
from neuroloop.controllers.recurrent import RecurrentEIController


def build_controller_from_spec(spec: str) -> AbstractController:
    mapping: Dict[str, Any] = {
        "C0_Off": OffController,
        "C1_Fixed": FixedProgramController,
        "C2_CalibratedFixed": CalibratedFixedController,
        "C3_ConservativeRules": ConservativeRulesController,
        "C4_HeuristicFilter": HeuristicThreeHypothesisController,
        "C5_SequentialBayesian": SequentialBayesianController,
        "C6_SparseRecurrentEI": RecurrentEIController,
    }
    if spec not in mapping:
        raise ValueError(f"Unknown controller factory spec: {spec!r}")
    return mapping[spec]()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python -m neuroloop.orchestrator.worker_main <controller_spec>")
    ctrl = build_controller_from_spec(sys.argv[1])
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        cmd = req.get("cmd")
        if cmd == "exit":
            break
        elif cmd == "reset":
            obs = PublicObservation.from_dict(req["obs"])
            ctrl.reset(obs)
            sys.stdout.write(json.dumps({"status": "ok", "snapshot": ctrl.snapshot()}) + "\n")
            sys.stdout.flush()
        elif cmd == "act":
            obs = PublicObservation.from_dict(req["obs"])
            act = ctrl.act(obs)
            sys.stdout.write(
                json.dumps(
                    {
                        "status": "ok",
                        "action": {
                            "stimulation": act.stimulation.value,
                            "feedback": act.feedback.value,
                            "target_program_id": act.target_program_id,
                            "prompt_id": act.prompt_id,
                            "observation_sequence": act.observation_sequence,
                        },
                        "snapshot": ctrl.snapshot(),
                    }
                )
                + "\n"
            )
            sys.stdout.flush()
        elif cmd == "snapshot":
            sys.stdout.write(json.dumps({"status": "ok", "snapshot": ctrl.snapshot()}) + "\n")
            sys.stdout.flush()
        elif cmd == "restore":
            ctrl.restore(req["state"])
            sys.stdout.write(json.dumps({"status": "ok"}) + "\n")
            sys.stdout.flush()
        else:
            raise ValueError(f"Unknown worker command: {cmd!r}")


if __name__ == "__main__":
    main()
