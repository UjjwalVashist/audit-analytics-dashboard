"""Build a static results page (docs/index.html) from the sample ledger, for GitHub Pages.

    python build_report.py
"""

from html import escape
from pathlib import Path

import plotly.graph_objects as go

from audit_checks import checks

ROOT = Path(__file__).parent
REPO = "https://github.com/{owner}/audit-analytics-dashboard"


def table_html(df, rows=10):
    shown = df.head(rows).copy()
    for col in shown.columns:
        if str(shown[col].dtype).startswith("datetime"):
            shown[col] = shown[col].dt.strftime("%Y-%m-%d")
    more = f'<p class="more">… and {len(df) - rows} more in the app\'s Excel export.</p>' if len(df) > rows else ""
    return shown.to_html(index=False, border=0, classes="t", float_format=lambda x: f"{x:,.2f}") + more


def build(owner: str = "") -> Path:
    df = checks.load_entries(ROOT / "data" / "journal_entries_sample.csv")
    results = checks.run_all(df)
    flagged = {b for r in results if "BELNR" in r.flagged for b in r.flagged["BELNR"]}
    table, mad, conformity = checks.benford(df)
    by_user = checks.benford_by_user(df)

    fig = go.Figure()
    fig.add_bar(x=table["digit"], y=table["observed"], name="Observed", marker_color="#2a78d6")
    fig.add_scatter(x=table["digit"], y=table["expected"], name="Benford's law", mode="lines+markers",
                    line=dict(color="#eb6834", width=2))
    fig.update_layout(height=320, margin=dict(t=10, b=40, l=40, r=10), yaxis_tickformat=".0%",
                      xaxis=dict(dtick=1, title="First digit"), legend=dict(orientation="h", y=1.12),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    chart = fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})

    sections = "".join(
        f'<details><summary><b>{escape(r.title)}</b> <span class="n">{len(r.flagged)}</span></summary>'
        f'<p>{escape(r.why)}</p>{table_html(r.flagged)}</details>' for r in results)
    repo = REPO.format(owner=owner) if owner else ""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Analytics Dashboard</title>
<style>
 :root {{ color-scheme: light dark; --bg:#fcfcfb; --fg:#0b0b0b; --muted:#52514e; --line:#e2e0da; --card:#f5f4f1; --accent:#2a78d6; }}
 @media (prefers-color-scheme: dark) {{ :root {{ --bg:#1a1a19; --fg:#fff; --muted:#c3c2b7; --line:#33332f; --card:#232321; --accent:#3987e5; }} }}
 body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }}
 main {{ max-width:960px; margin:0 auto; padding:32px 16px 64px; }}
 h1 {{ margin:0 0 4px; font-size:28px; }} h2 {{ margin:36px 0 8px; font-size:19px; }}
 .muted, .more {{ color:var(--muted); }} a {{ color:var(--accent); }}
 .tiles {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:20px 0; }}
 .tile {{ background:var(--card); border-radius:10px; padding:14px 16px; }}
 .tile b {{ display:block; font-size:26px; }}
 details {{ border:1px solid var(--line); border-radius:10px; padding:10px 14px; margin:8px 0; }}
 summary {{ cursor:pointer; }} .n {{ float:right; color:var(--muted); }}
 .wrap {{ overflow-x:auto; }} table.t {{ border-collapse:collapse; font-size:13px; width:100%; }}
 .t th, .t td {{ text-align:left; padding:4px 8px; border-bottom:1px solid var(--line); white-space:nowrap; }}
 code {{ background:var(--card); padding:2px 5px; border-radius:4px; }}
</style></head><body><main>
<h1>Audit Analytics Dashboard</h1>
<p class="muted">Journal-entry testing on general-ledger data, as done in financial-statement audits. Results below are for a
<b>synthetic</b> sample ledger (fiscal year 2025, SAP-style fields) with deliberately planted anomalies.
{f'Code and interactive app: <a href="{repo}">{repo.removeprefix("https://")}</a>' if repo else ""}</p>
<div class="tiles">
 <div class="tile"><b>{len(df):,}</b>postings</div>
 <div class="tile"><b>{df['DMBTR'].sum():,.0f} €</b>total amount</div>
 <div class="tile"><b>{len(flagged):,}</b>postings flagged ({len(flagged) / len(df):.1%})</div>
 <div class="tile"><b>{len(results)}</b>audit checks + Benford</div>
</div>
<h2>Findings</h2>
<div class="wrap">{sections}</div>
<h2>Benford's law</h2>
<p class="muted">Share of first digits of all amounts versus Benford's law. MAD {mad:.4f} → <b>{conformity}</b>.</p>
{chart}
<p>The ledger as a whole conforms, but split by user one person stands out:</p>
<div class="wrap">{by_user.to_html(index=False, border=0, classes="t")}</div>
<p class="muted">{escape(by_user.iloc[0]['USNAM'])} has far too many amounts starting with {by_user.iloc[0]['most_overrepresented_digit']} –
the same user who posts many invoices just below the 5,000 € approval limit. In a real audit this would be followed up.</p>
<h2>Run it yourself</h2>
<p><code>pip install -r requirements.txt</code> then <code>streamlit run app.py</code>, and upload your own journal-entry CSV.</p>
</main></body></html>"""
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(page.replace("<table", '<table'), encoding="utf-8")
    return out


if __name__ == "__main__":
    import sys
    print("Wrote", build(sys.argv[1] if len(sys.argv) > 1 else ""))
