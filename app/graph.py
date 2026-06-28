from typing import Optional, TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

from app.tools import lookup_vendor_metric

MAX_GATHER_ATTEMPTS = 2


# ---- 1. Shared state -------------------------------------------------------

class AuditState(TypedDict):
    contract_rules: list[dict]
    operational_logs: list[dict]
    gathered_info: list[dict]
    violations: list[dict]
    needs_more_data: bool
    gather_attempts: int
    dispute_letter: Optional[str]
    human_decision: Optional[str]
    status: str


# ---- helpers ---------------------------------------------------------------

_OPS = {
    ">=": lambda a, t: a >= t,
    "<=": lambda a, t: a <= t,
    ">":  lambda a, t: a > t,
    "<":  lambda a, t: a < t,
    "==": lambda a, t: a == t,
}


def _all_readings(state: AuditState) -> dict[str, dict]:
    merged = {r["metric"]: r for r in state["operational_logs"]}
    for g in state.get("gathered_info", []):
        if not g.get("not_found"):
            merged[g["metric"]] = g
    return merged


# ---- 2. Nodes --------------------------------------------------------------

def auditor_node(state: AuditState) -> dict:
    """Compare each rule against available data. Flag violations and missing data."""
    readings = _all_readings(state)
    violations, missing = [], []

    for rule in state["contract_rules"]:
        name = rule["metric_name"]
        reading = readings.get(name)
        if reading is None:
            missing.append(name)
            continue

        actual = reading["value"]
        compliant = _OPS[rule["operator"]](actual, rule["threshold"])
        if not compliant:
            magnitude = abs(actual - rule["threshold"])
            penalty = (rule["penalty_amount"] or 0) * magnitude if rule.get("penalty_amount") else None
            violations.append({
                "metric_name": name,
                "expected": f"{rule['operator']} {rule['threshold']} {rule['unit']}",
                "actual": actual,
                "unit": rule["unit"],
                "breach_magnitude": round(magnitude, 2),
                "estimated_penalty": round(penalty, 2) if penalty else None,
            })

    attempts = state.get("gather_attempts", 0)
    needs_more = len(missing) > 0 and attempts < MAX_GATHER_ATTEMPTS
    return {
        "violations": violations,
        "needs_more_data": needs_more,
        "status": "auditing",
    }


def info_gatherer_node(state: AuditState) -> dict:
    """Autonomously fetch any contract-required metric missing from the logs."""
    readings = _all_readings(state)
    required = {r["metric_name"] for r in state["contract_rules"]}
    missing = required - set(readings.keys())

    newly_gathered = []
    for metric in missing:
        result = lookup_vendor_metric.invoke({"metric": metric})
        newly_gathered.append(result)

    return {
        "gathered_info": state.get("gathered_info", []) + newly_gathered,
        "gather_attempts": state.get("gather_attempts", 0) + 1,
        "status": "gathering",
    }


def generate_dispute_node(state: AuditState) -> dict:
    """Draft a formal dispute letter from the violations."""
    if not state["violations"]:
        return {"dispute_letter": None, "status": "no_violations"}

    lines = ["FORMAL CONTRACT DISPUTE NOTICE", "=" * 40, ""]
    for v in state["violations"]:
        penalty_str = f"  Estimated penalty: ${v['estimated_penalty']}" if v.get("estimated_penalty") else ""
        lines += [
            f"Breach: {v['metric_name'].upper()}",
            f"  Contractual requirement: {v['expected']}",
            f"  Measured value:          {v['actual']} {v['unit']}",
            f"  Deviation:               {v['breach_magnitude']} {v['unit']}",
            penalty_str,
            "",
        ]
    lines.append("We request immediate remediation and compensation per the SLA terms.")
    letter = "\n".join(lines)
    return {"dispute_letter": letter, "status": "dispute_drafted"}


def human_approval_node(state: AuditState) -> dict:
    """HITL guardrail: pause and wait for a manager's decision before finalising."""
    decision = interrupt({
        "action": "approve_dispute",
        "dispute_letter": state["dispute_letter"],
        "violations": state["violations"],
        "message": "Approve sending this dispute? Resume with {'decision': 'approve'|'reject'}",
    })
    verdict = decision.get("decision") if isinstance(decision, dict) else decision
    return {
        "human_decision": verdict,
        "status": "approved" if verdict == "approve" else "rejected",
    }


# ---- 3. Routing ------------------------------------------------------------

def route_after_audit(state: AuditState) -> str:
    if state["needs_more_data"]:
        return "info_gatherer"
    return "generate_dispute"


# ---- 4. Wire the graph -----------------------------------------------------

def build_graph():
    b = StateGraph(AuditState)
    b.add_node("auditor", auditor_node)
    b.add_node("info_gatherer", info_gatherer_node)
    b.add_node("generate_dispute", generate_dispute_node)
    b.add_node("human_approval", human_approval_node)

    b.add_edge(START, "auditor")
    b.add_conditional_edges("auditor", route_after_audit, {
        "info_gatherer": "info_gatherer",
        "generate_dispute": "generate_dispute",
    })
    b.add_edge("info_gatherer", "auditor")        # THE CYCLE
    b.add_edge("generate_dispute", "human_approval")
    b.add_edge("human_approval", END)

    return b.compile(checkpointer=InMemorySaver())
