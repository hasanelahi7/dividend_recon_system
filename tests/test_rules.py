from __future__ import annotations
import pandas as pd

DATE_TOLERANCE_DAYS = 1  # ±1 day
FX_TOLERANCE = 0.01      # 1%
AMOUNT_TOLERANCE = 0.01  # Small rounding tolerance

def to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, dayfirst=True, errors="coerce")

def normalize(nbim: pd.DataFrame, cust: pd.DataFrame):
    nbim = nbim.copy()
    cust = cust.copy()

    # Align column names for joining
    nbim = nbim.rename(columns={
        'WTHTAX_COST_QUOTATION': 'WITHHOLDING_TAX_AMOUNT_QUOTATION',
        'WTHTAX_COST_SETTLEMENT': 'WITHHOLDING_TAX_AMOUNT_SETTLEMENT',
    })
    
    cust = cust.rename(columns={
        'CUSTODY': 'BANK_ACCOUNT',
    })

    # Normalize dates
    for col in ["EXDATE", "PAYMENT_DATE"]:
        if col in nbim.columns:
            nbim[col] = to_date(nbim[col])

    for col in ["EVENT_EX_DATE", "EVENT_PAYMENT_DATE", "RECORD_DATE", "PAY_DATE", "EX_DATE"]:
        if col in cust.columns:
            cust[col] = to_date(cust[col])

    return nbim, cust

def _classify_row(row) -> str:
    if row["_merge"] == "left_only":
        return "MISSING_IN_NBIM"
    if row["_merge"] == "right_only":
        return "MISSING_AT_CUSTODIAN"

    issues = []

    # Date checks
    if pd.notnull(row.get("EVENT_PAYMENT_DATE")) and pd.notnull(row.get("PAYMENT_DATE")):
        if abs((row["EVENT_PAYMENT_DATE"] - row["PAYMENT_DATE"]).days) > DATE_TOLERANCE_DAYS:
            issues.append("DATE_MISMATCH")
    
    if pd.notnull(row.get("EVENT_EX_DATE")) and pd.notnull(row.get("EXDATE")):
        if abs((row["EVENT_EX_DATE"] - row["EXDATE"]).days) > DATE_TOLERANCE_DAYS:
            if "DATE_MISMATCH" not in issues:
                issues.append("DATE_MISMATCH")

    # Gross amount check (same currency only)
    gross_cust = row.get("GROSS_AMOUNT")
    gross_nbim = row.get("GROSS_AMOUNT_QUOTATION")
    if pd.notnull(gross_cust) and pd.notnull(gross_nbim):
        # Only compare if settlement currencies match
        if row.get("SETTLED_CURRENCY") == row.get("QUOTATION_CURRENCY"):
            if abs(gross_cust - gross_nbim) > AMOUNT_TOLERANCE:
                issues.append("GROSS_MISMATCH")

    # Net amount check (settlement currency)
    net_cust = row.get("NET_AMOUNT_SC")
    net_nbim = row.get("NET_AMOUNT_SETTLEMENT")
    if pd.notnull(net_cust) and pd.notnull(net_nbim):
        if abs(net_cust - net_nbim) > AMOUNT_TOLERANCE:
            issues.append("NET_MISMATCH")

    # Tax check (needs currency alignment)
    tax_cust = row.get("TAX")
    tax_nbim = row.get("WITHHOLDING_TAX_AMOUNT_SETTLEMENT")
    if pd.notnull(tax_cust) and pd.notnull(tax_nbim):
        # If custody tax is in different currency, convert it
        if row.get("SETTLED_CURRENCY") != row.get("QUOTATION_CURRENCY"):
            # For cross-currency, custody TAX might be in quotation currency
            fx = row.get("FX_RATE", 1)
            if fx > 1:  # Likely KRW or similar
                tax_cust_converted = tax_cust / fx
            else:
                tax_cust_converted = tax_cust * fx
            if abs(tax_cust_converted - tax_nbim) > AMOUNT_TOLERANCE:
                issues.append("TAX_MISMATCH")
        else:
            if abs(tax_cust - tax_nbim) > AMOUNT_TOLERANCE:
                issues.append("TAX_MISMATCH")

    # FX variance check - ONLY for cross-currency settlements
    if row.get("SETTLED_CURRENCY") != row.get("QUOTATION_CURRENCY"):
        fx_cust = row.get("FX_RATE")
        fx_nbim = row.get("AVG_FX_RATE_QUOTATION_TO_PORTFOLIO")
        if pd.notnull(fx_cust) and pd.notnull(fx_nbim):
            # For KRW/USD, custody uses 1307.25, NBIM uses 0.008234 (inverse)
            # Need to check if they're inverses or same direction
            if fx_cust > 1 and fx_nbim < 1:
                # One is KRW/USD (1307), other is USD/KRW (0.008)
                fx_nbim_equiv = 1 / fx_nbim if fx_nbim != 0 else 0
            else:
                fx_nbim_equiv = fx_nbim
            
            base = max(abs(fx_cust), 1e-9)
            if abs(fx_cust - fx_nbim_equiv) / base > FX_TOLERANCE:
                issues.append("FX_VARIANCE")

    # ADR fee handling
    adr_fee = row.get("ADR_FEE", 0)
    if pd.notnull(adr_fee) and adr_fee != 0:
        # Check if ADR fee is properly reflected in net amount
        if pd.notnull(net_cust) and pd.notnull(net_nbim):
            # Net should be Gross - Tax - ADR Fee
            if abs((net_cust + adr_fee) - net_nbim) > AMOUNT_TOLERANCE:
                issues.append("ADR_FEE_HANDLING")

    # Position basis check (warning for data quality)
    if pd.notnull(row.get("NOMINAL_BASIS")) and pd.notnull(row.get("HOLDING_QUANTITY")):
        if abs(row["NOMINAL_BASIS"] - row["HOLDING_QUANTITY"]) > AMOUNT_TOLERANCE:
            issues.append("POSITION_MISMATCH")

    return "MATCHED" if not issues else " | ".join(sorted(set(issues)))

def reconcile(nbim: pd.DataFrame, cust: pd.DataFrame) -> pd.DataFrame:
    nbim_norm, cust_norm = normalize(nbim, cust)
    
    # Ensure merge keys exist in empty dataframes
    merge_keys = ["COAC_EVENT_KEY", "ISIN", "BANK_ACCOUNT"]
    
    if cust_norm.empty:
        for col in merge_keys:
            cust_norm[col] = pd.Series(dtype='object')
    
    if nbim_norm.empty:
        for col in merge_keys:
            nbim_norm[col] = pd.Series(dtype='object')
    
    # Critical fix: Join on event + ISIN + bank account
    merged = cust_norm.merge(
        nbim_norm,
        on=merge_keys,
        how="outer",
        suffixes=("", "_NBIM"),
        indicator=True,
    )
    
    merged["RECON_STATUS"] = merged.apply(_classify_row, axis=1)

    # Report columns
    report_cols = [
        "COAC_EVENT_KEY", "ISIN", "BANK_ACCOUNT",
        "INSTRUMENT_DESCRIPTION", "TICKER",
        "CUSTODIAN",
        "EVENT_EX_DATE", "EXDATE",
        "EVENT_PAYMENT_DATE", "PAYMENT_DATE",
        "SETTLED_CURRENCY", "QUOTATION_CURRENCY", "SETTLEMENT_CURRENCY",
        "GROSS_AMOUNT", "GROSS_AMOUNT_QUOTATION",
        "NET_AMOUNT_SC", "NET_AMOUNT_SETTLEMENT",
        "TAX", "WITHHOLDING_TAX_AMOUNT_QUOTATION",
        "FX_RATE", "AVG_FX_RATE_QUOTATION_TO_PORTFOLIO",
        "ADR_FEE", "TAX_RATE",
        "NOMINAL_BASIS", "HOLDING_QUANTITY",
        "_merge", "RECON_STATUS",
    ]
    
    existing = [c for c in report_cols if c in merged.columns]
    return merged[existing].copy()