import os
import streamlit as st
import pandas as pd
from recon.rules import reconcile
from recon.llm import classify_break

st.set_page_config(page_title="Dividend Reconciliation", layout="wide")
st.title("🏦 Dividend Reconciliation – Rules + LLM (Demo)")

st.markdown("Upload **NBIM** and **Custodian** CSV files (semicolon `;` separated).")

col1, col2 = st.columns(2)
with col1:
    nbim_file = st.file_uploader("NBIM CSV", type=["csv"], key="nbim")
with col2:
    cust_file = st.file_uploader("Custodian CSV", type=["csv"], key="cust")

use_llm = st.checkbox("Classify breaks with LLM", value=True)
llm_max_calls = st.number_input("Max LLM calls (budget cap)", min_value=1, max_value=1000, value=100)

run = st.button("Reconcile")
if run:
    if not nbim_file or not cust_file:
        st.error("Please upload both files.")
        st.stop()

    nbim_df = pd.read_csv(nbim_file, sep=";")
    cust_df = pd.read_csv(cust_file, sep=";")

    report = reconcile(nbim_df, cust_df)

    if use_llm:
        # Track LLM calls for budget control
        call_counter = {"count": 0}
        
        def classify_guarded(row: dict):
            # Skip MATCHED rows and respect budget cap
            if row.get("RECON_STATUS") == "MATCHED" or call_counter["count"] >= llm_max_calls:
                return {}
            call_counter["count"] += 1
            out = classify_break(row).model_dump()
            out["llm_source"] = "live" if os.getenv("OPENAI_API_KEY") else "fallback"
            return out

        llm_cols = report.apply(
            lambda r: classify_guarded(r.to_dict()), 
            axis=1, 
            result_type="expand"
        )
        report = pd.concat([report, llm_cols], axis=1)
        
        st.info(f"💰 LLM API calls made: {call_counter['count']} / {llm_max_calls}")

    st.success(f"✅ Reconciled {len(report)} rows.")
    
    # Show summary metrics
    col1, col2, col3 = st.columns(3)
    breaks = (report["RECON_STATUS"] != "MATCHED").sum() if "RECON_STATUS" in report.columns else 0
    matched = (report["RECON_STATUS"] == "MATCHED").sum() if "RECON_STATUS" in report.columns else 0
    needs_human = report["needs_human"].sum() if "needs_human" in report.columns else 0
    
    col1.metric("Total Rows", len(report))
    col2.metric("Breaks Detected", breaks, delta=f"{matched} matched", delta_color="inverse")
    col3.metric("Needs Human Review", needs_human)
    
    # Display report
    st.dataframe(report, use_container_width=True)

    # Download button
    csv = report.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download Report CSV", 
        data=csv, 
        file_name="dividend_recon_report.csv", 
        mime="text/csv"
    )