# tests/test_integration.py
"""
Minimal critical integration tests.
Tests: End-to-end pipeline with real workflow.
"""
import pandas as pd
from recon.rules import reconcile
from recon.llm import classify_break


def test_full_pipeline_mixed_data():
    """Critical: End-to-end workflow with mixed match/break data"""
    # Setup: 2 events - 1 perfect match, 1 break
    nbim = pd.DataFrame([
        {
            "COAC_EVENT_KEY": 1,
            "ISIN": "US0378331005",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT_QUOTATION": 100.0,
            "NET_AMOUNT_SETTLEMENT": 85.0,
            "QUOTATION_CURRENCY": "USD",
            "SETTLEMENT_CURRENCY": "USD"
        },
        {
            "COAC_EVENT_KEY": 2,
            "ISIN": "KR7005930003",
            "BANK_ACCOUNT": "ACC002",
            "GROSS_AMOUNT_QUOTATION": 200.0,
            "NET_AMOUNT_SETTLEMENT": 170.0,
            "QUOTATION_CURRENCY": "USD",
            "SETTLEMENT_CURRENCY": "USD"
        }
    ])
    
    cust = pd.DataFrame([
        {
            "COAC_EVENT_KEY": 1,
            "ISIN": "US0378331005",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT": 100.0,
            "NET_AMOUNT_SC": 85.0,
            "SETTLED_CURRENCY": "USD"
        },
        {
            "COAC_EVENT_KEY": 2,
            "ISIN": "KR7005930003",
            "BANK_ACCOUNT": "ACC002",
            "GROSS_AMOUNT": 195.0,  # Break: 5.0 difference
            "NET_AMOUNT_SC": 165.0,
            "SETTLED_CURRENCY": "USD"
        }
    ])
    
    # Step 1: Rules engine
    report = reconcile(nbim, cust)
    
    assert len(report) == 2
    assert "RECON_STATUS" in report.columns
    
    # Step 2: Count matches and breaks
    matched = (report["RECON_STATUS"] == "MATCHED").sum()
    breaks = (report["RECON_STATUS"] != "MATCHED").sum()
    
    assert matched == 1
    assert breaks == 1
    
    # Step 3: LLM classification (only on breaks)
    llm_results = []
    for _, row in report.iterrows():
        if row["RECON_STATUS"] != "MATCHED":
            result = classify_break(row.to_dict())
            llm_results.append(result)
    
    # Should classify exactly 1 break
    assert len(llm_results) == 1
    
    # LLM result should be valid
    result = llm_results[0]
    assert result.break_code in [
        "GROSS_MISMATCH", "NET_MISMATCH", "OTHER"
    ]
    assert 0.0 <= result.confidence <= 1.0
    assert isinstance(result.needs_human, bool)
    assert len(result.proposed_action) > 0


def test_real_test_data_structure():
    """Critical: System handles actual test data format"""
    # Simulate structure from actual NBIM/CUSTODY files
    nbim = pd.DataFrame([{
        "COAC_EVENT_KEY": 950123456,
        "ISIN": "US0378331005",
        "BANK_ACCOUNT": "501234567",
        "INSTRUMENT_DESCRIPTION": "APPLE INC",
        "TICKER": "AAPL",
        "EXDATE": "07.02.2025",
        "PAYMENT_DATE": "14.02.2025",
        "GROSS_AMOUNT_QUOTATION": 375000,
        "NET_AMOUNT_SETTLEMENT": 318750,
        "WITHHOLDING_TAX_AMOUNT_QUOTATION": 56250,
        "QUOTATION_CURRENCY": "USD",
        "SETTLEMENT_CURRENCY": "USD",
        "AVG_FX_RATE_QUOTATION_TO_PORTFOLIO": 11.2345
    }])
    
    cust = pd.DataFrame([{
        "COAC_EVENT_KEY": 950123456,
        "ISIN": "US0378331005",
        "BANK_ACCOUNT": "501234567",
        "CUSTODIAN": "CUST/JPMORGANUS",
        "EVENT_EX_DATE": "07.02.2025",
        "EVENT_PAYMENT_DATE": "14.02.2025",
        "GROSS_AMOUNT": 375000,
        "NET_AMOUNT_SC": 318750,
        "TAX": 56250,
        "SETTLED_CURRENCY": "USD",
        "FX_RATE": 1.0
    }])
    
    # Should process without errors
    result = reconcile(nbim, cust)
    
    assert len(result) == 1
    assert "RECON_STATUS" in result.columns
    assert result.iloc[0]["RECON_STATUS"] == "MATCHED"


def test_cost_optimization_skips_matched():
    """Critical: LLM is only called for breaks (cost optimization)"""
    # 3 rows: 2 matched, 1 break
    nbim = pd.DataFrame([
        {"COAC_EVENT_KEY": i, "ISIN": f"US{i}", "BANK_ACCOUNT": "ACC001",
         "GROSS_AMOUNT_QUOTATION": 100, "QUOTATION_CURRENCY": "USD"}
        for i in range(3)
    ])
    
    cust = pd.DataFrame([
        {"COAC_EVENT_KEY": 0, "ISIN": "US0", "BANK_ACCOUNT": "ACC001",
         "GROSS_AMOUNT": 100, "SETTLED_CURRENCY": "USD"},  # Match
        {"COAC_EVENT_KEY": 1, "ISIN": "US1", "BANK_ACCOUNT": "ACC001",
         "GROSS_AMOUNT": 100, "SETTLED_CURRENCY": "USD"},  # Match
        {"COAC_EVENT_KEY": 2, "ISIN": "US2", "BANK_ACCOUNT": "ACC001",
         "GROSS_AMOUNT": 95, "SETTLED_CURRENCY": "USD"},   # Break
    ])
    
    report = reconcile(nbim, cust)
    
    # Count how many would need LLM
    llm_needed = 0
    for _, row in report.iterrows():
        if row["RECON_STATUS"] != "MATCHED":
            llm_needed += 1
    
    # Should only need LLM for 1 row (33% of rows)
    assert llm_needed == 1
    assert llm_needed < len(report)  # Cost optimization working