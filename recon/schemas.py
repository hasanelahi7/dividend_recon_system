from typing import Literal
from pydantic import BaseModel, Field

BreakCode = Literal[
    "MATCHED",
    "MISSING_IN_NBIM",
    "MISSING_AT_CUSTODIAN",
    "DATE_MISMATCH",
    "GROSS_MISMATCH",
    "NET_MISMATCH",
    "TAX_MISMATCH",
    "FX_VARIANCE",
    "ADR_FEE_HANDLING",
    "POSITION_MISMATCH",
    "IDENTIFIER_MISMATCH",
    "OTHER"
]

class LLMResult(BaseModel):
    """
    Result from LLM classification of a reconciliation break.
    
    Fields:
    - break_code: Primary classification of the break type
    - confidence: LLM's confidence in the classification (0.0 to 1.0)
    - explanation_one_liner: Concise explanation of the root cause
    - proposed_action: Specific next step to resolve the break
    - needs_human: Whether manual review is required (vs auto-fixable)
    """
    break_code: BreakCode
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    explanation_one_liner: str = Field(min_length=1, description="Concise root cause explanation")
    proposed_action: str = Field(min_length=1, description="Specific remediation step")
    needs_human: bool = Field(default=True, description="Requires human review if True")