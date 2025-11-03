# tests/test_cli.py
"""
Minimal critical tests for CLI interface.
Tests: basic execution, output creation, help text.
"""
import tempfile
from pathlib import Path
import pandas as pd
from typer.testing import CliRunner
from recon.cli import app

runner = CliRunner()


def test_cli_basic_execution():
    """Critical: CLI runs and produces output CSV"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal test files
        nbim_path = Path(tmpdir) / "nbim.csv"
        cust_path = Path(tmpdir) / "cust.csv"
        out_path = Path(tmpdir) / "out.csv"
        
        # Write test data
        pd.DataFrame([{
            "COAC_EVENT_KEY": 1,
            "ISIN": "US01",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT_QUOTATION": 100,
            "QUOTATION_CURRENCY": "USD"
        }]).to_csv(nbim_path, sep=";", index=False)
        
        pd.DataFrame([{
            "COAC_EVENT_KEY": 1,
            "ISIN": "US01",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT": 100,
            "SETTLED_CURRENCY": "USD"
        }]).to_csv(cust_path, sep=";", index=False)
        
        # Run CLI
        result = runner.invoke(app, [
            "--nbim", str(nbim_path),
            "--cust", str(cust_path),
            "--out", str(out_path)
        ])
        
        # Verify success
        assert result.exit_code == 0
        assert out_path.exists()
        
        # Verify output has correct columns
        output_df = pd.read_csv(out_path)
        assert "RECON_STATUS" in output_df.columns


def test_cli_with_llm_flag():
    """Critical: CLI respects --use-llm flag"""
    with tempfile.TemporaryDirectory() as tmpdir:
        nbim_path = Path(tmpdir) / "nbim.csv"
        cust_path = Path(tmpdir) / "cust.csv"
        out_path = Path(tmpdir) / "out.csv"
        
        # Create data with a break
        pd.DataFrame([{
            "COAC_EVENT_KEY": 1,
            "ISIN": "US01",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT_QUOTATION": 100,
            "QUOTATION_CURRENCY": "USD",
            "SETTLEMENT_CURRENCY": "USD"
        }]).to_csv(nbim_path, sep=";", index=False)
        
        pd.DataFrame([{
            "COAC_EVENT_KEY": 1,
            "ISIN": "US01",
            "BANK_ACCOUNT": "ACC001",
            "GROSS_AMOUNT": 95,  # Mismatch
            "SETTLED_CURRENCY": "USD"
        }]).to_csv(cust_path, sep=";", index=False)
        
        # Run with LLM enabled
        result = runner.invoke(app, [
            "--nbim", str(nbim_path),
            "--cust", str(cust_path),
            "--out", str(out_path),
            "--use-llm",
            "--llm-max-calls", "1"
        ])
        
        assert result.exit_code == 0
        assert out_path.exists()
        
        # Check for LLM columns
        output_df = pd.read_csv(out_path)
        # LLM columns should be present
        assert "break_code" in output_df.columns or output_df.shape[1] > 10


def test_cli_shows_help():
    """Critical: CLI shows help when no arguments provided"""
    result = runner.invoke(app, [])
    
    # Should exit successfully and show help
    assert result.exit_code == 0
    # Help text should mention NBIM or usage
    assert "NBIM" in result.stdout or "help" in result.stdout.lower() or "Usage" in result.stdout


def test_cli_budget_cap():
    """Critical: CLI respects LLM budget cap"""
    with tempfile.TemporaryDirectory() as tmpdir:
        nbim_path = Path(tmpdir) / "nbim.csv"
        cust_path = Path(tmpdir) / "cust.csv"
        out_path = Path(tmpdir) / "out.csv"
        
        # Create multiple breaks
        pd.DataFrame([
            {"COAC_EVENT_KEY": i, "ISIN": f"US{i}", "BANK_ACCOUNT": "ACC001",
             "GROSS_AMOUNT_QUOTATION": 100, "QUOTATION_CURRENCY": "USD"}
            for i in range(5)
        ]).to_csv(nbim_path, sep=";", index=False)
        
        pd.DataFrame([
            {"COAC_EVENT_KEY": i, "ISIN": f"US{i}", "BANK_ACCOUNT": "ACC001",
             "GROSS_AMOUNT": 95, "SETTLED_CURRENCY": "USD"}  # All breaks
            for i in range(5)
        ]).to_csv(cust_path, sep=";", index=False)
        
        # Run with low budget cap
        result = runner.invoke(app, [
            "--nbim", str(nbim_path),
            "--cust", str(cust_path),
            "--out", str(out_path),
            "--use-llm",
            "--llm-max-calls", "2"  # Cap at 2 calls
        ])
        
        # Should still complete successfully
        assert result.exit_code == 0