import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from langgraph.types import Command

from app.graph import build_graph
from app.extraction import extract_rules, extract_text_from_upload

app = FastAPI(
    title="AcuityOps",
    description="Autonomous vendor & contract compliance agent with human-in-the-loop approval.",
    version="1.0.0",
)

# Compile ONCE at startup. Same instance (and its checkpointer) serves every request.
GRAPH = build_graph()

# Simple in-memory stores (swap for a DB in real production).
CONTRACTS: dict[str, list[dict]] = {}
TASKS: dict[str, dict] = {}


# ---- Request / Response schemas --------------------------------------------

class AuditRequest(BaseModel):
    contract_id: str
    operational_logs: list[dict]


class ApprovalRequest(BaseModel):
    decision: str   # "approve" or "reject"


# ---- Endpoints -------------------------------------------------------------

@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "AcuityOps"}


@app.post("/upload-contract/", tags=["Contracts"])
async def upload_contract(file: UploadFile = File(...)):
    """Upload a .txt or .pdf contract. Returns a contract_id and the extracted rules."""
    try:
        raw = await file.read()
        text = extract_text_from_upload(file.filename, raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    if not text.strip():
        raise HTTPException(status_code=400, detail="Contract file is empty or unreadable.")

    rules = extract_rules(text)
    if not rules:
        raise HTTPException(status_code=422, detail="No enforceable rules found in contract.")

    contract_id = str(uuid.uuid4())
    CONTRACTS[contract_id] = rules
    return {
        "contract_id": contract_id,
        "rules_extracted": len(rules),
        "rules": rules,
    }


@app.post("/audit/", tags=["Audits"])
async def run_audit(req: AuditRequest):
    """Start an audit run. Returns immediately — either completed or paused for approval."""
    if req.contract_id not in CONTRACTS:
        raise HTTPException(status_code=404, detail="Unknown contract_id.")

    if not req.operational_logs:
        raise HTTPException(status_code=400, detail="operational_logs must not be empty.")

    task_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": task_id}}
    init_state = {
        "contract_rules": CONTRACTS[req.contract_id],
        "operational_logs": req.operational_logs,
        "gathered_info": [],
        "violations": [],
        "needs_more_data": False,
        "gather_attempts": 0,
        "dispute_letter": None,
        "human_decision": None,
        "status": "running",
    }

    result = await GRAPH.ainvoke(init_state, config)
    interrupts = result.get("__interrupt__")

    if interrupts:
        payload = interrupts[0].value
        TASKS[task_id] = {"status": "pending_approval", "contract_id": req.contract_id}
        return {
            "task_id": task_id,
            "status": "pending_approval",
            "violations": payload["violations"],
            "dispute_letter": payload["dispute_letter"],
        }

    # No violations — graph completed without pausing.
    # Surface any metrics the tool also couldn't find, for transparency.
    unverifiable = [
        g["metric"] for g in result.get("gathered_info", []) if g.get("not_found")
    ]
    TASKS[task_id] = {"status": result.get("status", "completed")}
    return {
        "task_id": task_id,
        "status": result.get("status"),
        "violations": result.get("violations", []),
        "unverifiable_metrics": unverifiable,
        "dispute_letter": None,
    }


@app.get("/tasks/pending-approval", tags=["Tasks"])
async def pending_tasks():
    """List all audit runs currently waiting for human approval."""
    return [
        {"task_id": tid, **info}
        for tid, info in TASKS.items()
        if info["status"] == "pending_approval"
    ]


@app.get("/tasks/{task_id}", tags=["Tasks"])
async def get_task(task_id: str):
    """Get the current status of any task."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Unknown task_id.")
    return {"task_id": task_id, **TASKS[task_id]}


@app.post("/tasks/{task_id}/approve", tags=["Tasks"])
async def approve_task(task_id: str, req: ApprovalRequest):
    """Resume a paused audit with a human decision ('approve' or 'reject')."""
    if task_id not in TASKS:
        raise HTTPException(status_code=404, detail="Unknown task_id.")

    if TASKS[task_id]["status"] != "pending_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Task is '{TASKS[task_id]['status']}', not pending_approval.",
        )

    if req.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'reject'.")

    config = {"configurable": {"thread_id": task_id}}
    final = await GRAPH.ainvoke(Command(resume={"decision": req.decision}), config)

    TASKS[task_id]["status"] = final.get("status", "completed")
    return {
        "task_id": task_id,
        "decision": req.decision,
        "final_status": final.get("status"),
        "human_decision": final.get("human_decision"),
    }
