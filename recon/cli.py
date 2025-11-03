# recon/cli.py
import os
from typing import Optional
import pandas as pd
import typer
from pathlib import Path
from .rules import reconcile as run_reconcile
from .llm import classify_break

app = typer.Typer(
    add_completion=False,
    help=(
        "Runs reconciliation and writes a CSV report.\n"
        "- Reads semicolon-separated CSVs.\n"
        "- Applies deterministic rules to flag breaks.\n"
        "- Optionally calls the LLM ONLY for break rows, up to llm_max_calls (budget cap)."
    ),
)

@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    nbim: Optional[Path] = typer.Option(None, exists=True, readable=True, help="NBIM CSV (;)"),
    cust: Optional[Path] = typer.Option(None, exists=True, readable=True, help="Custodian CSV (;)"),
    out: Path = typer.Option("recon_out.csv", help="Output CSV"),
    use_llm: bool = typer.Option(False, help="Add LLM classification columns"),
    fx_tolerance_bp: int = typer.Option(100, help="FX variance tolerance in basis points (display only)"),
    llm_max_calls: int = typer.Option(100, help="Max rows to send to LLM (budget cap)"),
):
    """
    Root usage:
      recon --nbim NBIM.csv --cust CUSTODY.csv --out recon_out.csv --use-llm --llm-max-calls 50
    """
    # Show help if required files are missing
    if nbim is None or cust is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)

    # Load CSVs
    nbim_df = pd.read_csv(nbim, sep=";")
    cust_df = pd.read_csv(cust, sep=";")

    # Rules engine
    report = run_reconcile(nbim_df, cust_df)

    # Optional LLM (only for breaks) with hard cap
    if use_llm:
        calls = 0
        def classify_guarded(row: dict):
            nonlocal calls
            if row.get("RECON_STATUS") == "MATCHED" or calls >= llm_max_calls:
                return {}
            calls += 1
            out = classify_break(row).model_dump()
            out["llm_source"] = "live" if os.getenv("OPENAI_API_KEY") else "fallback"
            return out

        llm_cols = report.apply(lambda r: classify_guarded(r.to_dict()), axis=1, result_type="expand")
        report = pd.concat([report, llm_cols], axis=1)

    report.to_csv(out, index=False)
    typer.echo(f"Wrote {out}")

if __name__ == "__main__":
    app()
