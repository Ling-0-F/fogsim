"""D03: feasible first; no failure ranking or successful-subset selection."""
import math
import statistics
from fogsim.errors import InputError


class EvaluationContractError(RuntimeError):
    classification = "RESULT_CONTRACT_ERROR"


class PlanCoverageError(EvaluationContractError, InputError):
    classification = "INPUT_OR_PLAN_ERROR"


def classify(result):
    if result["status"] == "SUCCEEDED":
        value = result.get("makespan")
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise EvaluationContractError("successful B08 result lacks finite nonnegative makespan")
        return "SUCCESS"
    if result["status"] != "FAILED":
        raise EvaluationContractError("unexpected B08 result status")
    code = result.get("reason_code")
    if code in ("REPLAY_INPUT_EXHAUSTED", "REPLAY_INPUT_DIVERGENCE"):
        raise PlanCoverageError(f"plan input coverage error: {code}")
    if code is None and result.get("reason") != "event limit exceeded":
        raise EvaluationContractError("unclassified B08 failure")
    return "EVENT_BUDGET_EXHAUSTED" if code == "MAX_EVENTS_EXCEEDED" or result.get("reason") == "event limit exceeded" else "DOMAIN_FAILURE"


def summarize(records, planned, complete):
    success = [r["makespan"] for r in records if r["classification"] == "SUCCESS"]
    failed = sum(r["classification"] in ("DOMAIN_FAILURE", "EVENT_BUDGET_EXHAUSTED") for r in records)
    completed = len(success) + failed
    feasible = complete and completed == planned == len(success)
    return dict(status=("FEASIBLE" if feasible else "INFEASIBLE") if complete else "INCOMPLETE",
        fitness=statistics.mean(success) if feasible else None, planned_runs=planned,
        completed_runs=completed, succeeded_runs=len(success), failed_runs=failed, not_run=planned-completed,
        diagnostic_mean_over_successes=statistics.mean(success) if success else None,
        diagnostic_sample_stddev_over_successes=statistics.stdev(success) if len(success) >= 2 else None,
        diagnostic_stddev_denominator=len(success)-1 if len(success) >= 2 else None,
        failure_rate=failed/completed if completed else None, failure_rate_denominator=completed,
        not_run_fraction=(planned-completed)/planned)


def compare(left, right):
    a, b = left.to_dict() if hasattr(left, "to_dict") else left, right.to_dict() if hasattr(right, "to_dict") else right
    if "INCOMPLETE" in (a["status"], b["status"]):
        raise EvaluationContractError("incomplete evaluations cannot participate in selection")
    if a["plan_id"] != b["plan_id"]:
        raise EvaluationContractError("cannot compare scores from different plans")
    if a["status"] != b["status"]:
        return -1 if a["status"] == "FEASIBLE" else 1
    if a["status"] == "INFEASIBLE":
        return 0
    return (a["fitness"] > b["fitness"]) - (a["fitness"] < b["fitness"])
