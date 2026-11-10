"""Audit Analytics Dashboard - journal-entry testing in the browser.

    streamlit run app.py
"""

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from audit_checks import checks

SAMPLE = Path(__file__).parent / "data" / "journal_entries_sample.csv"
LEVEL_COLORS = {"High": "#c2410c", "Medium": "#d97706", "Low": "#94a3b8"}

st.set_page_config(page_title="Audit Analytics Dashboard", page_icon="🔎", layout="wide")
st.title("Audit Analytics Dashboard")
st.caption("Journal-entry tests on general-ledger data (Buchungsdaten), with risk points per posting: "
           "nine selection criteria from audit practice (ISA 240) plus Benford's law.")

with st.sidebar:
    st.header("Data")
    upload = st.file_uploader("Journal entries (CSV)", type="csv",
                              help="Needs columns " + ", ".join(checks.REQUIRED)
                              + ". Optional: " + ", ".join(checks.OPTIONAL))
    st.caption("Without an upload, a synthetic sample ledger for fiscal year 2025 is used "
               "(made-up data with planted anomalies).")
    limit = st.number_input("Approval limit (EUR)", min_value=100.0, value=5000.0, step=500.0)

try:
    df = checks.load_entries(upload if upload is not None else SAMPLE)
except ValueError as e:
    st.error(str(e))
    st.stop()

results = checks.run_all(df, limit)
scores = checks.risk_scores(df, results)
levels = scores["level"].value_counts()

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Postings tested", f"{len(df):,}")
c2.metric("Total amount", f"{df['DMBTR'].sum() / 1e6:,.2f} M€")
c3.metric("Postings flagged", f"{len(scores):,}", f"{len(scores) / len(df):.1%} of all", delta_color="off")
c4.metric("High risk", f"{levels.get('High', 0):,}")
c5.metric("Period", f"{df['BUDAT'].min():%m/%y} – {df['BUDAT'].max():%m/%y}")

st.download_button("Download exception list (Excel)", checks.exception_list(results),
                   "exception_list.xlsx", type="primary")

ranking, findings, benford, population = st.tabs(["Risk ranking", "Findings by test", "Benford's law", "Population check"])

with ranking:
    st.write("Every flagged posting gets the points of each test it fails: **High** = 3 or more, "
             "**Medium** = 2, **Low** = 1. Start the follow-up at the top.")
    f1, f2 = st.columns([2, 1])
    picked = f1.multiselect("Risk level", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    users = f2.multiselect("User", sorted(scores["USNAM"].dropna().unique()))
    shown = scores[scores["level"].isin(picked) & (scores["USNAM"].isin(users) if users else True)]
    cols = ["BELNR", "level", "score", "hit"] + [c for c in shown.columns if c not in ("BELNR", "level", "score", "hit", "keys", "tests")]
    st.dataframe(shown[cols], hide_index=True, use_container_width=True,
                 column_config={"score": st.column_config.ProgressColumn("Points", min_value=0, max_value=int(scores["score"].max() or 1), format="%d"),
                                "DMBTR": st.column_config.NumberColumn("Amount €", format="%.2f"),
                                "hit": "Failed tests"})
    sample = st.slider("Risk-based sample: how many postings?", 5, max(5, len(shown)), min(25, max(5, len(shown))))
    st.download_button("Download this sample (CSV)", shown.head(sample).drop(columns=["keys"]).to_csv(index=False),
                       "risk_based_sample.csv")

with findings:
    for r in results:
        with st.expander(f"{r.title} — {len(r.flagged)} finding(s) · {r.weight} point(s)", expanded=False):
            st.write(r.why)
            st.caption(f"Basis: {r.basis}")
            if r.key == "below_limit" and len(r.flagged):
                st.bar_chart(r.flagged.groupby("USNAM").size().sort_values(ascending=False),
                             x_label="User", y_label="Postings just below the limit")
            st.dataframe(r.flagged, hide_index=True, use_container_width=True)

with benford:
    table, mad, conformity = checks.benford(df)
    fig = go.Figure()
    fig.add_bar(x=table["digit"], y=table["observed"], name="Observed", marker_color="#1d4ed8")
    fig.add_scatter(x=table["digit"], y=table["expected"], name="Benford", mode="lines+markers",
                    line=dict(color="#c2410c", width=2))
    fig.update_layout(height=340, margin=dict(t=10, b=10), yaxis_tickformat=".0%",
                      xaxis=dict(dtick=1, title="First digit"), legend=dict(orientation="h", y=1.1))
    st.plotly_chart(fig, use_container_width=True)
    st.write(f"Mean absolute deviation (MAD): **{mad:.4f}** → {conformity} (Nigrini thresholds).")
    st.markdown("**By user** – a ledger can conform overall while one person's postings don't:")
    st.dataframe(checks.benford_by_user(df), hide_index=True, use_container_width=True)

with population:
    pop = checks.completeness(df)
    st.write("Before testing, reconcile the extract with the trial balance: is every posting there?")
    st.table({"Check": ["Postings", "Total amount", "Document numbers", "Missing document numbers",
                        "Duplicate document keys", "Posting dates", "Users", "G/L accounts"],
              "Result": [f"{pop['postings']:,}", f"{pop['total']:,.2f} €", f"{pop['first_document']} – {pop['last_document']}",
                         pop["missing_numbers"], pop["duplicate_keys"],
                         f"{pop['first_date']:%d.%m.%Y} – {pop['last_date']:%d.%m.%Y} ({pop['months_covered']} months)",
                         pop["users"], pop["accounts"]]})
