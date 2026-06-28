import uuid
from langgraph.types import Command
from app.graph import build_graph

# Sample rules and logs that reproduce the core demo scenario:
# - uptime breaches (in logs)
# - delivery_time missing (tool must fetch it)
_SAMPLE_RULES = [
    {"metric_name": "uptime",        "operator": ">=", "threshold": 99.9,  "unit": "percent", "penalty_amount": 500.0,  "penalty_unit": "per_hour"},
    {"metric_name": "response_time", "operator": "<=", "threshold": 2.0,   "unit": "hours",   "penalty_amount": 250.0,  "penalty_unit": "per_incident"},
    {"metric_name": "delivery_time", "operator": "<=", "threshold": 48.0,  "unit": "hours",   "penalty_amount": 100.0,  "penalty_unit": "per_hour"},
]

_SAMPLE_LOGS = [
    {"metric": "uptime",        "value": 99.2, "unit": "percent", "period": "2026-05"},
    {"metric": "response_time", "value": 4.5,  "unit": "hours",   "period": "2026-05"},
    # delivery_time deliberately absent — agent must fetch via tool
]

_INIT_STATE = {
    "contract_rules":  _SAMPLE_RULES,
    "operational_logs": _SAMPLE_LOGS,
    "gathered_info":   [],
    "violations":      [],
    "needs_more_data": False,
    "gather_attempts": 0,
    "dispute_letter":  None,
    "human_decision":  None,
    "status":          "init",
}


def test_graph_pauses_at_interrupt():
    """Graph must pause at human_approval with violations detected."""
    graph  = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = graph.invoke(_INIT_STATE, config)

    assert "__interrupt__" in result, "Graph should pause at interrupt()"
    payload = result["__interrupt__"][0].value
    assert payload["action"] == "approve_dispute"
    assert len(payload["violations"]) > 0, "Should detect at least one violation"
    assert payload["dispute_letter"] is not None, "Dispute letter should be drafted"


def test_graph_resumes_on_approve():
    """Graph must complete with status=approved after resume."""
    graph  = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph.invoke(_INIT_STATE, config)
    final = graph.invoke(Command(resume={"decision": "approve"}), config)

    assert final["status"] == "approved"
    assert final["human_decision"] == "approve"


def test_graph_resumes_on_reject():
    """Graph must complete with status=rejected after reject."""
    graph  = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    graph.invoke(_INIT_STATE, config)
    final = graph.invoke(Command(resume={"decision": "reject"}), config)

    assert final["status"] == "rejected"
    assert final["human_decision"] == "reject"


def test_graph_fetches_missing_metric():
    """Info-gatherer must autonomously fetch delivery_time when absent from logs."""
    graph  = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    result = graph.invoke(_INIT_STATE, config)

    # delivery_time should have been gathered by the tool
    gathered_metrics = [g["metric"] for g in result.get("gathered_info", [])]
    assert "delivery_time" in gathered_metrics, "Agent should have fetched delivery_time via tool"


def test_graph_no_violations_completes_without_pause():
    """Compliant logs produce no violations and no interrupt."""
    graph  = build_graph()
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}

    compliant_state = {**_INIT_STATE, "operational_logs": [
        {"metric": "uptime",        "value": 99.95, "unit": "percent", "period": "2026-04"},
        {"metric": "response_time", "value": 1.2,   "unit": "hours",   "period": "2026-04"},
        {"metric": "delivery_time", "value": 36.0,  "unit": "hours",   "period": "2026-04"},
    ]}

    result = graph.invoke(compliant_state, config)

    assert "__interrupt__" not in result, "Compliant logs should not trigger human approval"
    assert result["status"] == "no_violations"
    assert len(result["violations"]) == 0
