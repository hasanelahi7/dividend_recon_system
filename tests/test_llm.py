# tests/test_llm.py
"""
Minimal critical tests for LLM classification module.
Tests: fallback behavior, matched skipping, valid outputs.
"""
import pytest
from recon.llm import classify_break
from recon.schemas import LLMResult


def test_matched_rows_skip_llm():
    """Critical: MATCHED rows don't need LLM (cost savings)"""
    row = {"RECON_STATUS": "MATCHED"}
    
    result = classify_break(row)
    
    assert result.break_code == "MATCHED"
    assert result.confidence == 1.0
    assert result.needs_human is False


def test_fallback_without_api_key(monkeypatch):
    """Critical: System works without API key (graceful degradation)"""
    # Remove API key
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    
    row = {"RECON_STATUS": "GROSS_MISMATCH"}
    
    result = classify_break(row)
    
    # Should return valid fallback classification
    assert result.break_code == "GROSS_MISMATCH"
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.explanation_one_liner, str)
    assert len(result.explanation_one_liner) > 0
    assert isinstance(result.needs_human, bool)


def test_returns_valid_pydantic_model():
    """Critical: LLM output is always valid LLMResult"""
    row = {"RECON_STATUS": "NET_MISMATCH"}
    
    result = classify_break(row)
    
    # Should be valid Pydantic model
    assert isinstance(result, LLMResult)
    assert hasattr(result, "break_code")
    assert hasattr(result, "confidence")
    assert hasattr(result, "explanation_one_liner")
    assert hasattr(result, "proposed_action")
    assert hasattr(result, "needs_human")


def test_confidence_in_valid_range():
    """Critical: Confidence is always 0-1"""
    row = {"RECON_STATUS": "TAX_MISMATCH"}
    
    result = classify_break(row)
    
    assert 0.0 <= result.confidence <= 1.0


def test_handles_unknown_break_types():
    """Critical: Unknown breaks get OTHER classification"""
    row = {"RECON_STATUS": "WEIRD_UNKNOWN_ERROR_XYZ"}
    
    result = classify_break(row)
    
    assert result.break_code == "OTHER"
    assert result.needs_human is True
    assert len(result.proposed_action) > 0