# recon/llm.py
import os, json
from typing import Dict, Any
from pydantic import ValidationError
from openai import OpenAI
from .schemas import LLMResult

# Use a small, cheap model. You can override with env var LLM_MODEL if needed.
_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Deterministic fallback if no key / error, so app never breaks
_FALLBACK = {
    "DATE_MISMATCH": ("DATE_MISMATCH", 0.85, "Payment/Ex-date mismatch beyond tolerance.",
                      "Confirm issuer timetable; adjust event dates; re-run accrual.", True),
    "GROSS_MISMATCH": ("GROSS_MISMATCH", 0.80, "Gross differs in same currency; likely rounding or stale figure.",
                       "Recalc gross from DPS × position; align currency; request cust statement.", True),
    "NET_MISMATCH": ("NET_MISMATCH", 0.80, "Net settlement differs.",
                     "Rebuild net: gross - tax - ADR fee; confirm fees applied.", True),
    "TAX_MISMATCH": ("TAX_MISMATCH", 0.90, "Tax amounts diverge.",
                     "Verify withholding vs treaty; open tax-reclaim if needed.", True),
    "FX_VARIANCE": ("FX_VARIANCE", 0.75, "FX variance over policy threshold.",
                    "Align FX source & timestamp; adjust to reference rate.", True),
    "ADR_FEE_HANDLING": ("ADR_FEE_HANDLING", 0.80, "ADR fee treatment inconsistent.",
                         "Post ADR fee as expense; adjust net settlement.", True),
    "POSITION_MISMATCH": ("POSITION_MISMATCH", 0.85, "Nominal basis differs between systems.",
                          "Verify position file; reconcile corporate actions; align holdings.", True),
}

# Only send essentials to keep tokens low (cheap)
_KEYS_TO_SEND = [
    "COAC_EVENT_KEY","ISIN","BANK_ACCOUNT",
    "INSTRUMENT_DESCRIPTION","TICKER",
    "EVENT_EX_DATE","EXDATE","EVENT_PAYMENT_DATE","PAYMENT_DATE",
    "SETTLED_CURRENCY","QUOTATION_CURRENCY","SETTLEMENT_CURRENCY",
    "GROSS_AMOUNT","GROSS_AMOUNT_QUOTATION",
    "NET_AMOUNT_SC","NET_AMOUNT_SETTLEMENT",
    "TAX","WITHHOLDING_TAX_AMOUNT_QUOTATION","WITHHOLDING_TAX_AMOUNT_SETTLEMENT",
    "FX_RATE","AVG_FX_RATE_QUOTATION_TO_PORTFOLIO",
    "ADR_FEE","TAX_RATE",
    "NOMINAL_BASIS","HOLDING_QUANTITY",
    "RECON_STATUS"
]

_SYSTEM = (
    "You are a financial-ops analyst for equity dividend reconciliation. "
    "Return ONLY valid JSON with keys: break_code, confidence, explanation_one_liner, proposed_action, needs_human. "
    "break_code ∈ [MATCHED,MISSING_IN_NBIM,MISSING_AT_CUSTODIAN,DATE_MISMATCH,GROSS_MISMATCH,NET_MISMATCH,"
    "TAX_MISMATCH,FX_VARIANCE,ADR_FEE_HANDLING,POSITION_MISMATCH,IDENTIFIER_MISMATCH,OTHER]. "
    "confidence ∈ [0,1]. "
    "explanation_one_liner: concise root cause. "
    "proposed_action: one specific next step. "
    "needs_human: true if requires manual review, false if auto-fixable."
)

def _fb(status: str) -> LLMResult:
    """Fallback classification when LLM is unavailable"""
    if status == "MATCHED":
        return LLMResult(break_code="MATCHED", confidence=1.0,
                         explanation_one_liner="No discrepancies.",
                         proposed_action="None", needs_human=False)
    
    # Find first matching break type in status
    for k, v in _FALLBACK.items():
        if k in status:
            code, conf, expl, action, need = v
            return LLMResult(break_code=code, confidence=conf,
                             explanation_one_liner=expl, proposed_action=action, needs_human=need)
    
    return LLMResult(break_code="OTHER", confidence=0.6,
                     explanation_one_liner="Unclear break; needs review.",
                     proposed_action="Escalate to ops with evidence.", needs_human=True)

def classify_break(row: Dict[str, Any]) -> LLMResult:
    """
    Classify a reconciliation break using LLM.
    Falls back to deterministic rules if API key is missing or call fails.
    """
    status = row.get("RECON_STATUS", "MATCHED")
    if status == "MATCHED":
        return _fb("MATCHED")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _fb(status)

    # Prepare minimal data for LLM
    slim = {k: row.get(k) for k in _KEYS_TO_SEND if k in row}
    prompt_user = (
        "Classify this reconciliation break and propose one next action.\n"
        "Focus on the most critical issue if multiple breaks exist.\n"
        "Data:\n" + json.dumps(slim, default=str, indent=2)
    )

    try:
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": prompt_user}
            ],
            temperature=0.1,
            max_tokens=200,  # Slightly increased for better explanations
        )
        text = resp.choices[0].message.content.strip()
        
        # Handle markdown code blocks
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
        
        data = json.loads(text)
        
        # Validate and construct result
        try:
            return LLMResult(**data)
        except ValidationError:
            # Map fields manually if validation fails
            mapped = {
                "break_code": data.get("break_code", "OTHER"),
                "confidence": float(data.get("confidence", 0.6)),
                "explanation_one_liner": data.get("explanation_one_liner", "Unclear break; needs review."),
                "proposed_action": data.get("proposed_action", "Escalate to ops with evidence."),
                "needs_human": bool(data.get("needs_human", True)),
            }
            return LLMResult(**mapped)
    
    except Exception as e:
        # Log error in production; for now, fallback silently
        # print(f"LLM call failed: {e}")
        return _fb(status)