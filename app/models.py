from typing import Literal, Optional
from pydantic import BaseModel, Field


class ContractRule(BaseModel):
    """One enforceable obligation extracted from the contract."""
    metric_name: str = Field(description="e.g. 'uptime', 'response_time', 'delivery_time'")
    operator: Literal[">=", "<=", ">", "<", "=="] = Field(
        description="Comparison the ACTUAL value must satisfy to be compliant"
    )
    threshold: float = Field(description="The numeric target, e.g. 99.9")
    unit: str = Field(description="Unit of the threshold, e.g. 'percent', 'hours', 'minutes'")
    penalty_amount: Optional[float] = Field(
        default=None, description="Monetary penalty per penalty_unit when violated"
    )
    penalty_unit: Optional[str] = Field(
        default=None, description="e.g. 'per_hour', 'per_incident', 'flat'"
    )


class ContractRules(BaseModel):
    """Wrapper so the LLM returns a list in one structured call."""
    rules: list[ContractRule]


class MetricReading(BaseModel):
    """One measured value from the vendor's operational logs."""
    metric: str
    value: float
    unit: str
    period: Optional[str] = None        # e.g. "2026-05"


class Violation(BaseModel):
    metric_name: str
    expected: str                        # human-readable: ">= 99.9 percent"
    actual: float
    unit: str
    breach_magnitude: float              # how far off, for penalty math
    estimated_penalty: Optional[float] = None
