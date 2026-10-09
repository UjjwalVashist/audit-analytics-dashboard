"""Audit Analytics Dashboard - journal-entry testing in the browser.

    streamlit run app.py
"""

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from audit_checks import checks

SAMPLE = Path(__file__).parent / "data" / "journal_entries_sample.csv"

st.set_page_config(page_title="Audit Analytics Dashboard", page_icon="🔎", layout="wide")
st.title("Audit Analytics Dashboard")
st.caption("Journal-entry tests on general-ledger data (Buchungsdaten): duplicates, document-number gaps, "
           "weekend postings, round amounts, approval-limit splitting, segregation of duties and Benford's law.")

with st.sidebar:
    st.header("Data")
    upload = st.file_uploader("Journal entries (CSV)", type="csv",
                              help="Needs columns " + ", ".join(checks.REQUIRED))
    st.caption("Without an upload, a synthetic sample ledger for fiscal year 2025 is used "
               "(made-up data with planted anomalies).")
    limit = st.number_input("Approval limit (EUR)", min_value=100.0, value=5000.0, step=500.0)

try:
    df = checks.load_entries(upload if upload is not None else SAMPLE)
except ValueError as e:
    st.error(str(e))
    st.stop()

results = checks.run_all(df, limit)
flagged_docs = {b for r in results if "BELNR" in r.flagged for b in r.flagged["BELNR"]}

c1, c2, c3, c4 = st.columns(4)
c1.metric("Postings", f"{len(df):,}")
c2.metric("Total amount", f"{df['DMBTR'].sum():,.0f} €")
c3.metric("Postings flagged", f"{len(flagged_docs):,}", f"{len(flagged_docs) / len(df):.1%} of all",
          delta_color="off")
c4.metric("Period", f"{df['BUDAT'].min():%d.%m.%Y} – {df['BUDAT'].max():%d.%m.%Y}")

st.download_button("Download exception list (Excel)", checks.exception_list(results),
                   "exception_list.xlsx", type="primary")

st.subheader("Findings")
for r in results:
    with st.expander(f"{r.title} — {len(r.flagged)} finding(s)", expanded=False):
        st.write(r.why)
        if r.key == "below_limit" and len(r.flagged):
            st.bar_chart(r.flagged.groupby("USNAM").size().sort_values(ascending=False),
                         x_label="User", y_label="Postings just below the limit")
        st.dataframe(r.flagged, hide_index=True, use_container_width=True)

st.subheader("Benford's law – first digits of all amounts")
table, mad, conformity = checks.benford(df)
fig = go.Figure()
fig.add_bar(x=table["digit"], y=table["observed"], name="Observed", marker_color="#2a78d6")
fig.add_scatter(x=table["digit"], y=table["expected"], name="Benford", mode="lines+markers",
                line=dict(color="#eb6834", width=2))
fig.update_layout(height=340, margin=dict(t=10, b=10), yaxis_tickformat=".0%",
                  xaxis=dict(dtick=1, title="First digit"), legend=dict(orientation="h", y=1.1))
st.plotly_chart(fig, use_container_width=True)
st.write(f"Mean absolute deviation (MAD): **{mad:.4f}** → {conformity} (Nigrini thresholds).")

st.markdown("**By user** – a ledger can conform overall while one person's postings don't:")
st.dataframe(checks.benford_by_user(df), hide_index=True, use_container_width=True)
