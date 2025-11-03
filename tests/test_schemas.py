# tests/test_schemas.py
"""
Minimal critical tests for Pydantic schemas.
Tests: validation, type safety, enum constraints.
"""
import pytest
from pydantic import ValidationError
from recon.schemas import LLMResult


def test_valid_llm_result():
    """Critical: Valid data creates LLMResult successfully"""
    result = LLMResult(
        break_code="GROSS_MISMATCH",
        confidence=0.85,
        explanation_one_liner="Gross amount differs by $5",
        proposed_action="Recalculate gross from DPS × position",
        needs_human=True
    )
    
    assert result.break_code == "GROSS_MISMATCH"
    assert result.confidence == 0.85
    assert result.needs_human is True


def test_confidence_bounds():
    """Critical: Confidence must be between 0 and 1"""
    # Valid bounds
    LLMResult(
        break_code="MATCHED",
        confidence=0.0,
        explanation_one_liner="test",
        proposed_action="test",
        needs_human=False
    )
    
    LLMResult(
        break_code="MATCHED",
        confidence=1.0,
        explanation_one_liner="test",
        proposed_action="test",
        needs_human=False
    )
    
    # Invalid: too high
    with pytest.raises(ValidationError):
        LLMResult(
            break_code="MATCHED",
            confidence=1.5,
            explanation_one_liner="test",
            proposed_action="test",
            needs_human=False
        )
    
    # Invalid: negative
    with pytest.raises(ValidationError):
        LLMResult(
            break_code="MATCHED",
            confidence=-0.1,
            explanation_one_liner="test",
            proposed_action="test",
            needs_human=False
        )


def test_break_code_enum_validation():
    """Critical: Only valid break codes are accepted"""
    # Valid break codes
    valid_codes = [
        "MATCHED", "MISSING_IN_NBIM", "MISSING_AT_CUSTODIAN",
        "DATE_MISMATCH", "GROSS_MISMATCH", "NET_MISMATCH",
        "TAX_MISMATCH", "FX_VARIANCE", "ADR_FEE_HANDLING",
        "POSITION_MISMATCH", "IDENTIFIER_MISMATCH", "OTHER"
    ]
    
    for code in valid_codes:
        result = LLMResult(
            break_code=code,
            confidence=0.9,
            explanation_one_liner="test",
            proposed_action="test",
            needs_human=True
        )
        assert result.break_code == code
    
    # Invalid break code
    with pytest.raises(ValidationError):
        LLMResult(
            break_code="INVALID_CODE_XYZ",
            confidence=0.9,
            explanation_one_liner="test",
            proposed_action="test",
            needs_human=True
        )


def test_required_fields():
    """Critical: All required fields must be provided"""
    # Missing required fields
    with pytest.raises(ValidationError):
        LLMResult(
            break_code="MATCHED",
            confidence=0.9
            # Missing explanation_one_liner and proposed_action
        )