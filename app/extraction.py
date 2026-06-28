import os
from dotenv import load_dotenv
from app.models import ContractRules

load_dotenv()

# Set USE_MOCK_LLM=false in .env to switch to the real Gemini LLM.
_USE_MOCK = os.getenv("USE_MOCK_LLM", "true").lower() != "false"

_EXTRACTION_PROMPT = """You extract enforceable obligations from service contracts.

Think step by step INTERNALLY before answering:
1. Find every clause that states a measurable target (a number + unit).
2. Determine whether the actual value must be >=, <=, >, <, or == the target to comply.
3. Capture any monetary penalty and the unit it applies to.

Only extract clauses with a concrete numeric threshold. Ignore vague language.
Do NOT invent thresholds or penalties that are not explicitly stated.

EXAMPLE
Clause: "Uptime must be at least 99.95% monthly; downtime is penalized $1000/hour."
Extracted: metric_name="uptime", operator=">=", threshold=99.95, unit="percent",
           penalty_amount=1000, penalty_unit="per_hour"

EXAMPLE
Clause: "Tickets must be answered within 4 hours."
Extracted: metric_name="response_time", operator="<=", threshold=4, unit="hours",
           penalty_amount=null, penalty_unit=null
"""

# Hardcoded rules matching sample_contract.txt — used when USE_MOCK_LLM=true
_MOCK_RULES = [
    {
        "metric_name": "uptime",
        "operator": ">=",
        "threshold": 99.9,
        "unit": "percent",
        "penalty_amount": 500.0,
        "penalty_unit": "per_hour",
    },
    {
        "metric_name": "response_time",
        "operator": "<=",
        "threshold": 2.0,
        "unit": "hours",
        "penalty_amount": 250.0,
        "penalty_unit": "per_incident",
    },
    {
        "metric_name": "delivery_time",
        "operator": "<=",
        "threshold": 48.0,
        "unit": "hours",
        "penalty_amount": 100.0,
        "penalty_unit": "per_hour",
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


def extract_rules(contract_text: str) -> list[dict]:
    """Returns a list of rule dicts. Uses mock by default; set USE_MOCK_LLM=false for real LLM."""
    if _USE_MOCK:
        print("[extraction] Using mock rules (set USE_MOCK_LLM=false to use real LLM)")
        return _MOCK_RULES
    return _real_extract(contract_text)


def extract_text_from_upload(filename: str, raw: bytes) -> str:
    """Accept .txt or .pdf contracts."""
    if filename.lower().endswith(".pdf"):
        from io import BytesIO
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    return raw.decode("utf-8")
