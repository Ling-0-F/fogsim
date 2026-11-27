"""B04 delivery preflight and durable independent-evaluation interruption facts."""
from copy import deepcopy
from pathlib import Path
import json
import os
import random
import subprocess
import sys
import pytest
from fogsim.training.config import load_training_config, parse_training_config
from fogsim.training.plans import build_training_plans
from fogsim.training.protocols import read_json, write_json
from fogsim.training.preflight import preflight_report
from fogsim.training.evaluation import evaluate_rule_pair
from fogsim.rules.factory import prepare_rules
from fogsim.rules.specs import RuleSpec

ROOT = Path(__file__).resolve().parents[2]


def pair():
    return prepare_rules(RuleSpec("routing", "gp", expression="PT"), RuleSpec("sequencing", "fcfs"))


@pytest.mark.parametrize("name", ["single", "dual"])
def test_large_template_preflight_without_simulation_or_rng(name, monkeypatch, tmp_path):
    import fogsim.training.runtime as runtime
    def forbidden(*args, **kwargs):
        raise AssertionError("preflight must not simulate")
    monkeypatch.setattr(runtime, "run_entry", forbidden)
    state = random.getstate()
    cfg = load_training_config(ROOT / f"configs/training/large-{name}-template.json")
    plans = build_training_plans(cfg)
    report = preflight_report(cfg, plans)
    assert random.getstate() == state
    assert report["closed_loop_budget"] == dict(trials=5, training_per_trial=10000,
        validation_upper_bound_per_trial=100, test_per_trial=2, total_upper_bound=50510)
    assert report["processed_event_upper_bound"] == 101020000
    assert report["retention"] == dict(trace="none", save_run_results=True, save_input_archives=True)
    assert report["simulations_executed"] == 0
    assert report["versions"]["dependencies"]["deap"] == "1.4.4"
    write_json(tmp_path / "preflight.json", report)


@pytest.mark.parametrize("mode", ["single_routing", "dual_tree"])
def test_launcher_defaults_to_preflight_then_explicit_small_execution(mode, tmp_path):
    raw = load_training_config(ROOT / "configs/training/smoke-dual.json").to_dict()
    raw.pop("resolution_root")
    raw.update(mode=mode, trials=dict(evolution_seeds=[71301]))
    raw["evolution"].update(population_size=2, generations=1, elite_count=1)
    raw["output"]["trace"] = "none"
    config = tmp_path / "small.json"
    write_json(config, raw)
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"))
    command = [sys.executable, str(ROOT / "tools/run_s9_training.py"), "--config", str(config)]
    pre = subprocess.run(command + ["--output", str(tmp_path / "preflight")], env=env, capture_output=True, text=True)
    assert pre.returncode == 0, pre.stderr
    assert read_json(tmp_path / "preflight/preflight.json")["simulations_executed"] == 0
    assert not list((tmp_path / "preflight").rglob("evaluation.json"))
    run = subprocess.run(command + ["--output", str(tmp_path / "actual"), "--execute"], env=env, capture_output=True, text=True)
    (tmp_path / "execution.stdout.txt").write_text(run.stdout)
    (tmp_path / "execution.stderr.txt").write_text(run.stderr)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.splitlines()[0])["closed_loop_budget"]["total_upper_bound"] == 8
    result = read_json(tmp_path / "actual/training-result.json")
    assert result["status"] == "COMPLETED"
    evaluations = list((tmp_path / "actual").rglob("evaluation.json"))
    assert sum(read_json(p)["completed_runs"] for p in evaluations) == 8
    assert all(read_json(p)["status"] == "FEASIBLE" for p in evaluations)
    for p in (tmp_path / "actual").rglob("result.json"):
        assert read_json(p)["events"] == []
        assert read_json(p)["decisions"] == []
    protected = subprocess.run(command + ["--output", str(tmp_path / "actual"), "--execute"], env=env, capture_output=True, text=True)
    assert protected.returncode == 2 and "absent or empty" in protected.stderr


class EofConnection:
    def poll(self, *args): return True
    def recv(self): raise EOFError
    def close(self): pass


class ReapedProcess:
    pid = None
    exitcode = None
    def start(self): self.pid = 42
    def is_alive(self): return False
    def join(self, **kwargs): self.exitcode = 42


class ExitContext:
    def Pipe(self): return EofConnection(), EofConnection()
    def Process(self, **kwargs): return ReapedProcess()


def test_evaluation_eof_before_join_records_final_exitcode(monkeypatch, tmp_path):
    import fogsim.training.evaluation as evaluation
    cfg = load_training_config(ROOT / "configs/training/smoke-dual.json")
    plan = build_training_plans(cfg).test
    monkeypatch.setattr(evaluation.multiprocessing, "get_context", lambda name: ExitContext())
    result = evaluate_rule_pair(pair(), plan, tmp_path).to_dict()
    assert result["status"] == "INCOMPLETE" and result["fitness"] is None
    assert result["interruption"] == dict(classification="WORKER_EXIT", exitcode=42)
    assert read_json(tmp_path / "failures/interruption.json") == result["interruption"]
    assert read_json(tmp_path / "evaluation.json")["interruption"] == result["interruption"]


def abrupt_exit_worker(*args):
    os._exit(42)


def test_evaluation_actual_worker_abrupt_exit(monkeypatch, tmp_path):
    import fogsim.training.evaluation as evaluation
    plan = build_training_plans(load_training_config(ROOT / "configs/training/smoke-dual.json")).test
    monkeypatch.setattr(evaluation, "evaluation_worker", abrupt_exit_worker)
    result = evaluate_rule_pair(pair(), plan, tmp_path).to_dict()
    assert result["status"] == "INCOMPLETE"
    assert result["interruption"]["classification"] == "WORKER_EXIT"
    assert result["interruption"]["exitcode"] == 42
    assert result["completed_runs"] == 0
