import os
from dotenv import load_dotenv
from app.models import ContractRules

load_dotenv()

# Set USE_MOCK_LLM=false in .env to switch to the real Gemini LLM.
_USE_MOCK = os.getenv("USE_MOCK_LLM", "true").lower() != "false"

_EXTRACTION_PROMPT = """You extract enforceable obligations from service contracts.

Think step by step INTERNALLY before answering:
1. Find every clause that states a measurable uptime or performance target (a number + unit).
2. Determine whether the actual value must be >=, <=, >, <, or == the target to comply.
3. Capture the penalty. For percentage-based service credits (e.g. "10% of monthly bill"),
   set penalty_amount to that percentage (e.g. 10) and penalty_unit to "percent_monthly_bill".
   For fixed dollar penalties, set penalty_unit to "per_hour" or "per_incident".

Only extract clauses with a concrete numeric threshold. Ignore vague language.
Do NOT invent thresholds or penalties that are not explicitly stated.

EXAMPLE — fixed dollar penalty:
Clause: "Uptime must be at least 99.95% monthly; downtime is penalized $1000/hour."
Extracted: metric_name="uptime", operator=">=", threshold=99.95, unit="percent",
           penalty_amount=1000, penalty_unit="per_hour"

EXAMPLE — percentage service credit (AWS-style):
Clause: "Monthly Uptime Percentage of at least 99.99%. If below 99.99% but >= 99.0%,
         Service Credit of 10% of monthly bill."
Extracted: metric_name="region_uptime", operator=">=", threshold=99.99, unit="percent",
           penalty_amount=10, penalty_unit="percent_monthly_bill"

EXAMPLE — second tier of same SLA:
Clause: "Instance-Level Uptime Percentage of at least 99.5%. If below 99.5% but >= 99.0%,
         Service Credit of 10% of monthly bill."
Extracted: metric_name="instance_uptime", operator=">=", threshold=99.5, unit="percent",
           penalty_amount=10, penalty_unit="percent_monthly_bill"
"""

# Hardcoded rules matching aws_ec2_sla.txt — used when USE_MOCK_LLM=true
_MOCK_RULES = [
    {
        "metric_name": "region_uptime",
        "operator": ">=",
        "threshold": 99.99,
        "unit": "percent",
        "penalty_amount": 10.0,
        "penalty_unit": "percent_monthly_bill",
    },
    {
        "metric_name": "instance_uptime",
        "operator": ">=",
        "threshold": 99.5,
        "unit": "percent",
        "penalty_amount": 10.0,
        "penalty_unit": "percent_monthly_bill",
    },
]


def _real_extract(contract_text: str) -> list[dict]:
    # Groq is used when available (free tier, no card needed).
    # Falls back to Gemini if GROQ_API_KEY is not set.
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        from langchain_groq import ChatGroq
        llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0, api_key=groq_key)
    else:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
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
    """Keep only the primary compliance threshold per metric.

    AWS-style SLAs define tiered credit tables (10%/30%/100%) for the same metric.
    The LLM often extracts each tier row as a separate rule. We collapse them:
    - Keep the strictest >= rule per metric (highest threshold = the SLA commitment)
    - Keep the strictest <= rule per metric (lowest threshold)
    - Discard the tier rows (< 99.0, < 95.0 etc.) since the auditor recomputes the
      correct tier from the actual value at violation time.
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
    """Returns a list of rule dicts. Uses mock by default; set USE_MOCK_LLM=false for real LLM."""
    if _USE_MOCK:
        print("[extraction] Using mock rules (set USE_MOCK_LLM=false to use real LLM)")
        return _MOCK_RULES
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
