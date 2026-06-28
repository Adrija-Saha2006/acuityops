import os
from dotenv import load_dotenv
from app.models import ContractRules

load_dotenv()

# Auto-use real LLM if GROQ_API_KEY is present, unless explicitly overridden.
_explicit = os.getenv("USE_MOCK_LLM")
if _explicit is not None:
    _USE_MOCK = _explicit.lower() != "false"
else:
    _USE_MOCK = not bool(os.getenv("GROQ_API_KEY"))

_EXTRACTION_PROMPT = """You extract every enforceable performance obligation from service contracts.

Think step by step INTERNALLY before answering:
1. Read the entire contract and find EVERY clause that states a measurable target with a concrete number and unit.
2. Determine the compliance direction: must the actual value be >=, <=, >, <, or == the target?
3. Capture the penalty exactly as written. Map it to penalty_amount and penalty_unit.

Supported contract types include (but are not limited to):
- Cloud / hosting SLAs (uptime %, response time)
- Telecom SLAs (packet loss %, latency ms, throughput Mbps)
- Delivery / logistics SLAs (delivery time hours, pickup time hours)
- Support SLAs (first response time hours, resolution time hours)
- Software / SaaS SLAs (API availability %, error rate %, data retention days)
- Manufacturing / supply chain SLAs (lead time days, defect rate %)

Penalty mapping rules:
- "$500 per hour" → penalty_amount=500, penalty_unit="per_hour"
- "$250 per incident" → penalty_amount=250, penalty_unit="per_incident"
- "10% of monthly bill" → penalty_amount=10, penalty_unit="percent_monthly_bill"
- "flat fee of $1000" → penalty_amount=1000, penalty_unit="flat"
- No penalty stated → penalty_amount=null, penalty_unit=null

Only extract clauses with a concrete numeric threshold. Skip vague language like "reasonable" or "timely".
Do NOT invent numbers. Do NOT combine clauses. Extract each obligation as a separate rule.

EXAMPLE 1 — cloud uptime with dollar penalty:
Clause: "System uptime must be at least 99.9% monthly. Downtime below guarantee incurs $500/hour."
→ metric_name="uptime", operator=">=", threshold=99.9, unit="percent", penalty_amount=500, penalty_unit="per_hour"

EXAMPLE 2 — support response time:
Clause: "All support tickets must receive a first response within 2 hours. Each breach is penalized $250 per incident."
→ metric_name="response_time", operator="<=", threshold=2, unit="hours", penalty_amount=250, penalty_unit="per_incident"

EXAMPLE 3 — delivery time:
Clause: "Hardware deliveries must complete within 48 hours of order confirmation. Late deliveries are penalized $100/hour."
→ metric_name="delivery_time", operator="<=", threshold=48, unit="hours", penalty_amount=100, penalty_unit="per_hour"

EXAMPLE 4 — telecom packet loss:
Clause: "Monthly packet loss shall not exceed 0.1% averaged across all links."
→ metric_name="packet_loss", operator="<=", threshold=0.1, unit="percent", penalty_amount=null, penalty_unit=null

EXAMPLE 5 — cloud uptime with percentage credit:
Clause: "Monthly Uptime of at least 99.99%. If below 99.99% but >= 99.0%, Service Credit of 10% of monthly bill."
→ metric_name="region_uptime", operator=">=", threshold=99.99, unit="percent", penalty_amount=10, penalty_unit="percent_monthly_bill"

EXAMPLE 6 — API error rate:
Clause: "API error rate must remain below 0.5% per month. Breach incurs a $2000 flat credit."
→ metric_name="api_error_rate", operator="<=", threshold=0.5, unit="percent", penalty_amount=2000, penalty_unit="flat"

EXAMPLE 7 — resolution time:
Clause: "Critical issues must be resolved within 4 hours of being reported."
→ metric_name="resolution_time", operator="<=", threshold=4, unit="hours", penalty_amount=null, penalty_unit=null
"""


def _real_extract(contract_text: str) -> list[dict]:
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=groq_key)
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            google_api_key=os.environ["GEMINI_API_KEY"],
        )
    structured_llm = llm.with_structured_output(ContractRules)
    result: ContractRules = structured_llm.invoke(
        [
            {"role": "system", "content": _EXTRACTION_PROMPT},
            {"role": "user", "content": f"Contract text:\n\n{contract_text}"},
        ]
    )
    return [r.model_dump() for r in result.rules]


def _deduplicate_rules(rules: list[dict]) -> list[dict]:
    """Keep only the strictest rule per metric.

    Tiered SLAs (e.g. AWS 10%/30%/100% credit table) produce multiple rows for the same
    metric. We keep the primary compliance threshold only — the auditor recomputes the
    correct penalty tier from the actual value.
    """
    by_metric: dict[str, list[dict]] = {}
    for rule in rules:
        by_metric.setdefault(rule["metric_name"], []).append(rule)

    result = []
    for metric_rules in by_metric.values():
        ge_rules = [r for r in metric_rules if r["operator"] in (">=", ">")]
        le_rules = [r for r in metric_rules if r["operator"] in ("<=", "<")]
        if ge_rules:
            result.append(max(ge_rules, key=lambda r: r["threshold"]))
        elif le_rules:
            result.append(min(le_rules, key=lambda r: r["threshold"]))
    return result


def extract_rules(contract_text: str) -> list[dict]:
    """Extract enforceable rules from contract text.

    Uses the real LLM when GROQ_API_KEY is set (handles any contract type).
    Falls back to mock only when no API key is available.
    """
    if _USE_MOCK:
        raise RuntimeError(
            "No GROQ_API_KEY found. Set GROQ_API_KEY in your .env file or environment "
            "to enable real contract extraction. Get a free key at console.groq.com."
        )
    rules = _real_extract(contract_text)
    return _deduplicate_rules(rules)


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    """Accept .txt or .pdf contracts."""
    if filename.lower().endswith(".pdf"):
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8")
