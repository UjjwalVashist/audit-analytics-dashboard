"""Build the static demo app (docs/index.html) from the sample ledger, for GitHub Pages.

    python build_report.py [github-owner]

One HTML file that works like an audit-analytics product: a sidebar with views
(Overview, Risk ranking, Tests, Benford, Data quality, Method), charts, and a detail
panel that opens when you click a posting or a test. The data is embedded as JSON.
"""

import json
from pathlib import Path

from audit_checks import checks

ROOT = Path(__file__).parent
REPO = "https://github.com/{owner}/audit-analytics-dashboard"
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def day(value) -> str:
    return value.strftime("%d.%m.%Y") if hasattr(value, "strftime") else ""


def payload(df, results, scores) -> dict:
    """Everything the page shows, as plain JSON."""
    pop = checks.completeness(df)
    table, mad, conformity = checks.benford(df)
    by_user = checks.benford_by_user(df)
    info = df.set_index("BELNR")
    rows = []
    for i, r in enumerate(scores.itertuples()):
        e = info.loc[r.BELNR]
        rows.append({"rank": i + 1, "doc": str(r.BELNR), "date": day(e.BUDAT), "entered": day(e.get("CPUDT")),
                     "time": str(e.get("CPUTM", "")), "user": e.USNAM, "approver": e.FREIGABE,
                     "account": f"{e.HKONT} {e.get('KONTO_TEXT', '')}".strip(), "vendor": e.LIFNR,
                     "amount": round(float(e.DMBTR), 2), "text": e.BKTXT, "score": int(r.score),
                     "level": r.level, "keys": r.keys})
    tests = [{"key": r.key, "title": r.title, "why": r.why, "weight": r.weight, "basis": r.basis,
              "rule": rule_of(r.key), "count": len(r.flagged),
              "docs": [str(b) for b in r.flagged["BELNR"].head(200)] if "BELNR" in r.flagged else [],
              "gaps": r.flagged.astype(str).to_dict("records") if r.key == "number_gaps" else []}
             for r in results]
    month_level = scores.assign(m=scores["BUDAT"].dt.month).groupby(["m", "level"]).size()
    users = sorted(df["USNAM"].unique())
    return {
        "pop": {**{k: (v if isinstance(v, (int, float, str)) else day(v)) for k, v in pop.items()},
                "per_month": [int((df["BUDAT"].dt.month == m).sum()) for m in range(1, 13)]},
        "rows": rows, "tests": tests, "months": MONTHS,
        "monthly": {lvl: [int(month_level.get((m, lvl), 0)) for m in range(1, 13)] for lvl in ("High", "Medium", "Low")},
        "heat": {"users": users, "tests": [t["title"].split(" (")[0] for t in tests if t["weight"]],
                 "z": [[int((r.flagged["USNAM"] == u).sum()) for u in users] for r in results if r.weight]},
        "benford": {"expected": [round(float(x), 4) for x in table["expected"]],
                    "observed": [round(float(x), 4) for x in table["observed"]], "mad": round(mad, 4), "conformity": conformity,
                    "users": {u: [round(float(x), 4) for x in checks.benford(part)[0]["observed"]]
                              for u, part in df.groupby("USNAM") if (part["DMBTR"] >= 10).sum() >= 100},
                    "by_user": by_user.to_dict("records")},
    }


def rule_of(key: str) -> str:
    fn = getattr(checks, key, None)
    return (fn.__doc__ or "").strip().split("\n")[0] if fn else ""


ICONS = {  # 24px stroke icons (Lucide-style paths)
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
    "ranking": '<path d="M3 6h18M3 12h12M3 18h6"/>',
    "tests": '<path d="M9 3h6M10 3v6L4 19a1 1 0 0 0 .9 1.5h14.2A1 1 0 0 0 20 19l-6-10V3"/>',
    "benford": '<path d="M3 3v18h18"/><rect x="7" y="8" width="3" height="10"/><rect x="12" y="11" width="3" height="7"/><rect x="17" y="14" width="3" height="4"/>',
    "quality": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "method": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/><path d="M4 19.5V21h16"/>',
    "github": '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.9a3.4 3.4 0 0 0-.9-2.6c3.1-.4 6.4-1.6 6.4-7A5.4 5.4 0 0 0 20 4.8 5 5 0 0 0 19.9 1S18.7.6 16 2.5a13.4 13.4 0 0 0-7 0C6.3.6 5.1 1 5.1 1A5 5 0 0 0 5 4.8a5.4 5.4 0 0 0-1.5 3.7c0 5.4 3.3 6.6 6.4 7A3.4 3.4 0 0 0 9 18.1V22"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
}


def icon(name: str, size: int = 18) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
            f'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def build(owner: str = "") -> Path:
    df = checks.load_entries(ROOT / "data" / "journal_entries_sample.csv")
    results = checks.run_all(df)
    scores = checks.risk_scores(df, results)
    data = payload(df, results, scores)
    repo = REPO.format(owner=owner) if owner else "#"
    high = sum(r["level"] == "High" for r in data["rows"])
    nav = [("overview", "Overview", ""), ("ranking", "Risk ranking", str(high)), ("tests", "Tests", str(sum(1 for t in data["tests"] if t["weight"]))),
           ("benford", "Benford's law", ""), ("quality", "Data quality", ""), ("method", "Method", "")]
    nav_html = "".join(f'<a href="#{k}" data-view="{k}">{icon(k)}<span>{label}</span>{f"<em>{n}</em>" if n else ""}</a>'
                       for k, label, n in nav)
    html = PAGE.replace("{{NAV}}", nav_html).replace("{{REPO}}", repo).replace("{{GITHUB}}", icon("github", 16)) \
        .replace("{{ALERT}}", icon("alert", 18)).replace("{{DATA}}", json.dumps(data, ensure_ascii=False, default=str))
    out = ROOT / "docs" / "index.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out


PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Audit Analytics – journal-entry testing</title>
<meta name="description" content="Journal-entry testing app: nine ISA 240 tests on every posting, risk scoring, Benford's law. Demo on synthetic SAP-style data.">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root { --bg:#f6f7f9; --panel:#fff; --fg:#0f172a; --muted:#64748b; --line:#e5e7eb; --soft:#f1f5f9; --side:#0b1220; --side-fg:#cbd5e1;
  --accent:#2563eb; --high:#dc2626; --med:#f59e0b; --low:#94a3b8; --good:#16a34a; }
* { box-sizing:border-box; }
html, body { height:100%; }
body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 Geist,-apple-system,"Segoe UI",sans-serif; display:flex; }
a { color:var(--accent); text-decoration:none; }
.mono { font-family:"Geist Mono",ui-monospace,monospace; }
aside { width:240px; flex:none; background:var(--side); color:var(--side-fg); display:flex; flex-direction:column; padding:18px 14px; position:sticky; top:0; height:100vh; }
.brand { display:flex; align-items:center; gap:10px; color:#fff; font-weight:600; font-size:15px; padding:2px 8px 18px; }
.logo { width:30px; height:30px; border-radius:8px; background:linear-gradient(135deg,#3b82f6,#8b5cf6); display:grid; place-items:center; font:600 12px "Geist Mono",monospace; color:#fff; }
.eng { background:#111a2e; border:1px solid #1e293b; border-radius:10px; padding:10px 12px; margin-bottom:16px; font-size:12px; }
.eng b { color:#fff; font-size:13px; display:block; } .eng span { color:#94a3b8; }
.eng .pill { display:inline-block; margin-top:6px; background:#422006; color:#fbbf24; border-radius:999px; padding:1px 8px; font-size:11px; }
aside nav { display:flex; flex-direction:column; gap:2px; }
aside nav a { display:flex; align-items:center; gap:10px; color:var(--side-fg); padding:8px 10px; border-radius:8px; font-size:13.5px; }
aside nav a:hover { background:#111a2e; color:#fff; }
aside nav a.on { background:#1e293b; color:#fff; }
aside nav em { margin-left:auto; font-style:normal; font-size:11px; background:#7f1d1d; color:#fecaca; border-radius:999px; padding:0 7px; }
aside nav a[data-view=tests] em { background:#1e293b; color:#cbd5e1; }
.side-foot { margin-top:auto; font-size:12px; color:#64748b; padding:0 8px; }
.side-foot a { color:#cbd5e1; display:flex; gap:8px; align-items:center; margin-bottom:10px; }
.app { flex:1; min-width:0; display:flex; flex-direction:column; }
.topbar { height:58px; flex:none; background:var(--panel); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:14px; padding:0 24px; position:sticky; top:0; z-index:5; }
.crumbs { color:var(--muted); font-size:13px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; } .crumbs b { color:var(--fg); font-weight:500; }
.topbar .sp { flex:1; }
.status { display:flex; align-items:center; gap:6px; font-size:12.5px; color:var(--muted); white-space:nowrap; }
.status i { width:8px; height:8px; border-radius:50%; background:var(--good); }
.btn { border:1px solid var(--line); background:var(--panel); color:var(--fg); border-radius:8px; padding:7px 12px; font:inherit; font-size:13px; cursor:pointer; display:inline-flex; gap:8px; align-items:center; white-space:nowrap; }
.btn.primary { background:var(--fg); color:#fff; border-color:var(--fg); }
main { padding:24px; max-width:1360px; width:100%; }
.view { display:none; } .view.on { display:block; animation:fade .18s ease; }
@keyframes fade { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
.vh { display:flex; align-items:end; justify-content:space-between; gap:16px; margin-bottom:18px; flex-wrap:wrap; }
.vh h1 { font-size:22px; letter-spacing:-.02em; margin:0; } .vh p { margin:2px 0 0; color:var(--muted); font-size:13px; }
.grid { display:grid; gap:16px; }
.k4 { grid-template-columns:repeat(4,minmax(0,1fr)); } .c21 { grid-template-columns:minmax(0,2fr) minmax(0,1fr); }
.c12 { grid-template-columns:minmax(0,1fr) minmax(0,2fr); } .c11 { grid-template-columns:repeat(2,minmax(0,1fr)); }
.c3 { grid-template-columns:repeat(3,minmax(0,1fr)); }
.card { background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:16px 18px; min-width:0; }
.card h3 { margin:0; font-size:13.5px; font-weight:600; } .card .ch { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; gap:8px; }
.card .ch small { color:var(--muted); font-size:12px; }
.kpi .l { color:var(--muted); font-size:12.5px; display:flex; justify-content:space-between; }
.kpi .v { font-size:28px; font-weight:600; letter-spacing:-.02em; margin:6px 0 8px; }
.kpi .meter { height:6px; border-radius:3px; background:var(--soft); overflow:hidden; } .kpi .meter span { display:block; height:100%; }
.kpi .f { font-size:12px; color:var(--muted); margin-top:8px; }
.alert { display:flex; gap:12px; align-items:center; background:#fef2f2; border:1px solid #fecaca; color:#7f1d1d; border-radius:12px; padding:12px 16px; margin-bottom:16px; }
.alert svg { flex:none; color:var(--high); } .alert .sp { flex:1; } .alert b { font-weight:600; }
.chart { position:relative; height:240px; } .chart.tall { height:300px; } .chart.small { height:210px; }
.donut { display:grid; grid-template-columns:150px 1fr; gap:14px; align-items:center; }
.legend div { display:flex; align-items:center; gap:8px; padding:6px 0; border-bottom:1px solid var(--soft); font-size:13px; }
.legend div:last-child { border:0; } .legend b { margin-left:auto; } .dot { width:9px; height:9px; border-radius:3px; flex:none; }
.top li { display:grid; grid-template-columns:auto 1fr auto; gap:12px; align-items:center; padding:9px 0; border-bottom:1px solid var(--soft); cursor:pointer; }
.top li:hover .who { color:var(--accent); } ul.top { list-style:none; margin:0; padding:0; } .top li:last-child { border:0; }
.who { font-weight:500; } .sub { color:var(--muted); font-size:12px; }
.score { min-width:34px; height:26px; border-radius:7px; display:grid; place-items:center; font-weight:600; font-size:13px; }
.High { background:#fee2e2; color:#b91c1c; } .Medium { background:#fef3c7; color:#b45309; } .Low { background:#f1f5f9; color:#475569; }
.badge { display:inline-block; border-radius:6px; padding:2px 8px; font-size:12px; font-weight:500; }
.heat { display:grid; gap:3px; font-size:11.5px; }
.heat .c { border-radius:5px; height:30px; display:grid; place-items:center; font-variant-numeric:tabular-nums; }
.heat .h { color:var(--muted); display:flex; align-items:center; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.heat .u { color:var(--muted); text-align:center; font-size:11px; padding-top:4px; overflow:hidden; text-overflow:ellipsis; }
.toolbar { display:flex; gap:10px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
.seg { display:inline-flex; background:var(--soft); border-radius:9px; padding:3px; flex-wrap:wrap; }
.seg button { border:0; background:none; font:inherit; font-size:13px; padding:5px 12px; border-radius:7px; cursor:pointer; color:var(--muted); }
.seg button.on { background:var(--panel); color:var(--fg); box-shadow:0 1px 2px rgb(0 0 0 / .08); }
.toolbar select, .toolbar input { font:inherit; font-size:13px; border:1px solid var(--line); border-radius:8px; padding:7px 10px; background:var(--panel); }
.toolbar input { min-width:240px; flex:1; }
.tbl { overflow:auto; max-height:calc(100vh - 230px); border:1px solid var(--line); border-radius:12px; background:var(--panel); }
table { border-collapse:collapse; width:100%; font-size:13px; }
th { position:sticky; top:0; background:#f8fafc; text-align:left; font-weight:500; color:var(--muted); font-size:11.5px; text-transform:uppercase; letter-spacing:.04em; padding:10px 12px; border-bottom:1px solid var(--line); white-space:nowrap; }
td { padding:10px 12px; border-bottom:1px solid var(--soft); white-space:nowrap; }
tbody tr { cursor:pointer; } tbody tr:hover { background:#f8fafc; }
td.n, th.n { text-align:right; font-variant-numeric:tabular-nums; }
.tags span { display:inline-block; background:var(--soft); border-radius:5px; padding:1px 7px; margin-right:4px; font-size:11.5px; color:#334155; }
.foot { color:var(--muted); font-size:12.5px; margin-top:10px; }
.tcard { cursor:pointer; transition:border-color .15s, box-shadow .15s; display:flex; flex-direction:column; gap:10px; }
.tcard:hover { border-color:#93c5fd; box-shadow:0 4px 16px rgb(37 99 235 / .08); }
.tcard .row { display:flex; justify-content:space-between; align-items:center; }
.tcard .n { font-size:26px; font-weight:600; letter-spacing:-.02em; }
.pts { font-size:11.5px; border-radius:6px; padding:2px 8px; }
.pts.w3 { background:#fee2e2; color:#b91c1c; } .pts.w2 { background:#fef3c7; color:#b45309; } .pts.w1, .pts.w0 { background:var(--soft); color:#475569; }
.bar { height:5px; background:var(--soft); border-radius:3px; overflow:hidden; } .bar span { display:block; height:100%; background:var(--accent); }
.tcard .basis { font-size:12px; color:var(--muted); }
.checks li { display:grid; grid-template-columns:24px 1fr auto; gap:10px; align-items:center; padding:11px 0; border-bottom:1px solid var(--soft); }
ul.checks { list-style:none; margin:0; padding:0; } .checks li:last-child { border:0; }
.ok { width:22px; height:22px; border-radius:50%; display:grid; place-items:center; font-size:12px; font-weight:700; background:#dcfce7; color:var(--good); }
.ok.w { background:#ffedd5; color:#c2410c; }
.steps { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:16px; }
.steps .card b { display:block; margin:8px 0 4px; } .steps .card p { margin:0; color:var(--muted); font-size:13px; }
.num { font:500 11.5px "Geist Mono",monospace; color:var(--accent); background:#eff6ff; border-radius:6px; padding:2px 7px; }
.drawer-bg { position:fixed; inset:0; background:rgb(15 23 42 / .35); opacity:0; pointer-events:none; transition:opacity .2s; z-index:20; }
.drawer { position:fixed; top:0; right:0; height:100vh; width:min(460px,100vw); background:var(--panel); z-index:21; transform:translateX(100%); transition:transform .22s ease; display:flex; flex-direction:column; box-shadow:-12px 0 32px rgb(0 0 0 / .12); }
body.open .drawer { transform:none; } body.open .drawer-bg { opacity:1; pointer-events:auto; }
.dh { padding:18px 22px; border-bottom:1px solid var(--line); display:flex; justify-content:space-between; gap:12px; align-items:start; }
.dh h2 { margin:4px 0 0; font-size:18px; } .x { border:0; background:var(--soft); width:30px; height:30px; border-radius:8px; cursor:pointer; font-size:16px; }
.db { padding:18px 22px; overflow:auto; }
dl { display:grid; grid-template-columns:120px 1fr; gap:8px 12px; margin:0 0 18px; font-size:13px; } dt { color:var(--muted); } dd { margin:0; }
.hit { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-bottom:8px; }
.hit .row { display:flex; justify-content:space-between; align-items:center; gap:10px; } .hit p { margin:4px 0 0; color:var(--muted); font-size:12.5px; }
.list li { padding:7px 0; border-bottom:1px solid var(--soft); display:flex; justify-content:space-between; gap:8px; font-size:13px; cursor:pointer; }
ul.list { list-style:none; padding:0; margin:0; } .list li:hover { color:var(--accent); }
.empty { color:var(--muted); padding:30px; text-align:center; }
@media (max-width:1100px) { .k4 { grid-template-columns:repeat(2,minmax(0,1fr)); } .c21, .c12, .c11, .c3, .steps { grid-template-columns:minmax(0,1fr); } }
@media (max-width:760px) { body { display:block; } aside { position:static; width:auto; height:auto; padding:12px; }
  aside nav { flex-direction:row; overflow-x:auto; } aside nav a span { white-space:nowrap; } .eng, .side-foot { display:none; } .brand { padding-bottom:10px; }
  .topbar { padding:0 14px; } .status { display:none; } main { padding:16px; } .toolbar input { min-width:0; } .donut { grid-template-columns:1fr; } }
</style></head><body>
<aside><div class="brand"><span class="logo">JE</span>Audit Analytics</div>
<div class="eng"><b>Demo Manufacturing GmbH</b><span>Company code 1000 · FY 2025</span><br><span class="pill">Synthetic demo data</span></div>
<nav>{{NAV}}</nav>
<div class="side-foot"><a href="{{REPO}}">{{GITHUB}} Source code &amp; Streamlit app</a>Python · SQL · pandas · pytest</div></aside>
<div class="app">
<div class="topbar"><div class="crumbs">Engagements / Demo Manufacturing GmbH / <b id="crumb">Overview</b></div><span class="sp"></span>
<span class="status"><i></i><span id="statusText"></span></span><a class="btn primary" href="{{REPO}}">Open repository</a></div>
<main>

<section class="view" id="v-overview">
 <div class="vh"><div><h1>Journal-entry testing</h1><p>All postings of FY 2025 tested against nine ISA 240 criteria</p></div></div>
 <div class="alert" id="topAlert">{{ALERT}}<div class="sp" id="topAlertText"></div><button class="btn" id="topAlertBtn">Review</button></div>
 <div class="grid k4" id="kpis"></div>
 <div class="grid c21" style="margin-top:16px">
  <div class="card"><div class="ch"><h3>Flagged postings per month</h3><small>by risk level</small></div><div class="chart"><canvas id="cMonthly"></canvas></div></div>
  <div class="card"><div class="ch"><h3>Risk mix</h3><small id="mixTotal"></small></div><div class="donut"><div class="chart small"><canvas id="cDonut"></canvas></div><div class="legend" id="mixLegend"></div></div></div>
 </div>
 <div class="grid c21" style="margin-top:16px">
  <div class="card"><div class="ch"><h3>Who triggers which test</h3><small>flagged postings per user</small></div><div class="heat" id="heat"></div></div>
  <div class="card"><div class="ch"><h3>Highest risk</h3><a href="#ranking">View all →</a></div><ul class="top" id="topList"></ul></div>
 </div>
</section>

<section class="view" id="v-ranking">
 <div class="vh"><div><h1>Risk ranking</h1><p>Points from every failed test · High ≥ 3 · Medium 2 · Low 1</p></div>
 <button class="btn" id="csv">Download sample (CSV)</button></div>
 <div class="toolbar"><div class="seg" id="lvl"><button class="on" data-l="">All</button><button data-l="High">High</button><button data-l="Medium">Medium</button><button data-l="Low">Low</button></div>
  <select id="user"><option value="">All users</option></select><select id="test"><option value="">All tests</option></select>
  <input id="q" type="search" placeholder="Search document, account, vendor, text…"></div>
 <div class="tbl"><table><thead><tr><th class="n">#</th><th>Level</th><th>Document</th><th>Posting date</th><th>User</th><th>Account</th><th class="n">Amount €</th><th>Failed tests</th></tr></thead><tbody id="rows"></tbody></table></div>
 <div class="foot" id="count"></div>
</section>

<section class="view" id="v-tests">
 <div class="vh"><div><h1>Tests</h1><p>Selection criteria from audit practice · click a test for its postings</p></div></div>
 <div class="grid c3" id="testCards"></div>
</section>

<section class="view" id="v-benford">
 <div class="vh"><div><h1>Benford's law</h1><p>First digits of all amounts vs. the expected distribution</p></div>
 <div class="seg" id="bUser"></div></div>
 <div class="grid c21">
  <div class="card"><div class="ch"><h3 id="bTitle">Whole ledger</h3><small id="bMad"></small></div><div class="chart tall"><canvas id="cBenford"></canvas></div></div>
  <div class="card"><div class="ch"><h3>Conformity per user</h3><small>Nigrini MAD</small></div><ul class="checks" id="bUsers"></ul></div>
 </div>
</section>

<section class="view" id="v-quality">
 <div class="vh"><div><h1>Data quality</h1><p>Is the extract complete? Reconcile before testing (ISA 240 Revised)</p></div></div>
 <div class="grid c12">
  <div class="card"><div class="ch"><h3>Population checks</h3></div><ul class="checks" id="popChecks"></ul></div>
  <div class="card"><div class="ch"><h3>Postings per month</h3><small id="popTotal"></small></div><div class="chart tall"><canvas id="cPop"></canvas></div></div>
 </div>
</section>

<section class="view" id="v-method">
 <div class="vh"><div><h1>Method</h1><p>How a posting gets its risk score – the documentation an audit file needs</p></div></div>
 <div class="steps">
  <div class="card"><span class="num">01</span><b>Load &amp; reconcile</b><p>Read the SAP-style extract and check the population is complete.</p></div>
  <div class="card"><span class="num">02</span><b>Run 9 tests</b><p>SQL (SQLite) and pandas on 100% of postings – no sampling.</p></div>
  <div class="card"><span class="num">03</span><b>Score</b><p>Add the points of every failed test. High ≥ 3, Medium 2, Low 1.</p></div>
  <div class="card"><span class="num">04</span><b>Follow up</b><p>Export exceptions and a risk-based sample to Excel / CSV.</p></div>
 </div>
 <div class="tbl" style="margin-top:16px;max-height:none"><table><thead><tr><th>Test</th><th>Rule</th><th class="n">Points</th><th>Basis</th></tr></thead><tbody id="rules"></tbody></table></div>
</section>
</main></div>

<div class="drawer-bg" id="bg"></div>
<div class="drawer" role="dialog" aria-modal="true" aria-labelledby="dTitle"><div class="dh"><div><span id="dKicker" class="sub"></span><h2 id="dTitle"></h2></div>
<button class="x" id="dClose" aria-label="Close">✕</button></div><div class="db" id="dBody"></div></div>

<script>
const D = {{DATA}};
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"})[c]);
const eur = new Intl.NumberFormat("de-DE", {minimumFractionDigits:2, maximumFractionDigits:2});
const int = new Intl.NumberFormat("en-US");
const C = {High:"#dc2626", Medium:"#f59e0b", Low:"#cbd5e1", accent:"#2563eb"};
const TEST = Object.fromEntries(D.tests.map(t => [t.key, t]));
const short = t => t.title.split(" (")[0];
Chart.defaults.font.family = "Geist, -apple-system, sans-serif"; Chart.defaults.color = "#64748b";
Chart.defaults.plugins.legend.display = false;
const charts = {};
const P = D.pop, rows = D.rows, levels = {High:0, Medium:0, Low:0};
rows.forEach(r => levels[r.level]++);

$("#statusText").textContent = `${int.format(P.postings)} postings · ${P.first_date} – ${P.last_date}`;

// ---------- overview ----------
const atRisk = rows.filter(r => r.level === "High").reduce((s, r) => s + r.amount, 0);
const kpi = (l, v, f, pct, color) => `<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div>
  <div class="meter"><span style="width:${Math.min(100, pct)}%;background:${color}"></span></div><div class="f">${f}</div></div>`;
$("#kpis").innerHTML = kpi("Postings tested", int.format(P.postings), `${int.format(Math.round(P.total))} € · 100% of population`, 100, C.accent)
  + kpi("Flagged", int.format(rows.length), `${(100 * rows.length / P.postings).toFixed(1)}% of postings`, 100 * rows.length / P.postings * 5, "#64748b")
  + kpi("High risk", levels.High, `${(100 * levels.High / rows.length).toFixed(0)}% of flagged postings`, 100 * levels.High / rows.length, C.High)
  + kpi("Amount at high risk", `${(atRisk / 1000).toFixed(0)} k€`, `${(100 * atRisk / P.total).toFixed(1)}% of total amount`, 100 * atRisk / P.total * 5, C.High);

const lead = rows[0];
if (lead && lead.keys.length >= 3) {
  $("#topAlertText").innerHTML = `<b>Possible management override:</b> document ${lead.doc} by ${esc(lead.user)} fails ${lead.keys.length} tests – ${lead.keys.map(k => short(TEST[k]).toLowerCase()).join(", ")}.`;
  $("#topAlertBtn").onclick = () => openRow(lead);
} else $("#topAlert").remove();

$("#mixTotal").textContent = `${rows.length} flagged`;
$("#mixLegend").innerHTML = Object.entries(levels).map(([l, n]) => `<div><i class="dot" style="background:${C[l]}"></i>${l}<b>${n}</b></div>`).join("");
$("#topList").innerHTML = rows.slice(0, 6).map((r, i) => `<li data-i="${i}"><span class="score ${r.level}">${r.score}</span>
  <div><div class="who mono">${r.doc}</div><div class="sub">${esc(r.user)} · ${r.date} · ${r.keys.length} tests</div></div><b>${eur.format(r.amount)} €</b></li>`).join("");
document.querySelectorAll("#topList li").forEach(li => li.onclick = () => openRow(rows[+li.dataset.i]));

const H = D.heat, peak = Math.max(1, ...H.z.flat());
$("#heat").style.gridTemplateColumns = `minmax(110px,170px) repeat(${H.users.length}, minmax(0,1fr))`;
$("#heat").innerHTML = H.z.map((row, i) => `<div class="h" title="${esc(H.tests[i])}">${esc(H.tests[i])}</div>` + row.map((n, j) => {
    const a = n ? 0.12 + 0.88 * n / peak : 0;
    return `<div class="c" title="${esc(H.users[j])}: ${n}" style="background:${n ? `rgba(220,38,38,${a.toFixed(2)})` : "#f8fafc"};color:${a > .5 ? "#fff" : "#334155"}">${n || ""}</div>`;
  }).join("")).join("") + `<div></div>` + H.users.map(u => `<div class="u">${esc(u)}</div>`).join("");

function drawOverview() {
  charts.m ??= new Chart($("#cMonthly"), {type:"bar", data:{labels:D.months, datasets:["Low","Medium","High"].map(l => ({label:l, data:D.monthly[l], backgroundColor:C[l], borderRadius:4, stack:"s"}))},
    options:{maintainAspectRatio:false, plugins:{legend:{display:true, position:"top", align:"end", labels:{boxWidth:10, boxHeight:10}}}, scales:{x:{grid:{display:false}}, y:{grid:{color:"#f1f5f9"}, ticks:{precision:0}}}}});
  charts.d ??= new Chart($("#cDonut"), {type:"doughnut", data:{labels:Object.keys(levels), datasets:[{data:Object.values(levels), backgroundColor:Object.keys(levels).map(l => C[l]), borderWidth:0}]},
    options:{maintainAspectRatio:false, cutout:"70%"}});
}

// ---------- ranking ----------
let lvl = "";
const users = [...new Set(rows.map(r => r.user))].sort();
$("#user").innerHTML += users.map(u => `<option>${esc(u)}</option>`).join("");
$("#test").innerHTML += D.tests.filter(t => t.weight).map(t => `<option value="${t.key}">${esc(short(t))}</option>`).join("");
let shown = rows;
function drawRows() {
  const q = $("#q").value.trim().toLowerCase(), u = $("#user").value, t = $("#test").value;
  shown = rows.filter(r => (!lvl || r.level === lvl) && (!u || r.user === u) && (!t || r.keys.includes(t)) &&
    (!q || [r.doc, r.account, r.vendor, r.text, r.keys.map(k => short(TEST[k])).join(" ")].join(" ").toLowerCase().includes(q)));
  $("#rows").innerHTML = shown.map((r, i) => `<tr data-i="${i}"><td class="n sub">${r.rank}</td><td><span class="badge ${r.level}">${r.level} · ${r.score}</span></td>
    <td class="mono">${r.doc}</td><td>${r.date}</td><td>${esc(r.user)}</td><td>${esc(r.account)}</td><td class="n">${eur.format(r.amount)}</td>
    <td class="tags">${r.keys.map(k => `<span>${esc(short(TEST[k]))}</span>`).join("")}</td></tr>`).join("") || `<tr><td colspan="8" class="empty">No postings match.</td></tr>`;
  document.querySelectorAll("#rows tr[data-i]").forEach(tr => tr.onclick = () => openRow(shown[+tr.dataset.i]));
  $("#count").textContent = `${shown.length} of ${rows.length} flagged postings`;
}
document.querySelectorAll("#lvl button").forEach(b => b.onclick = () => { lvl = b.dataset.l; document.querySelectorAll("#lvl button").forEach(x => x.classList.toggle("on", x === b)); drawRows(); });
["#q", "#user", "#test"].forEach(s => $(s).addEventListener("input", drawRows));
$("#csv").onclick = () => {
  const head = "rank,level,points,document,posting_date,entered,time,user,approver,account,vendor,amount,failed_tests\n";
  const body = shown.map(r => [r.rank, r.level, r.score, r.doc, r.date, r.entered, r.time, r.user, r.approver, r.account, r.vendor, r.amount, r.keys.map(k => short(TEST[k])).join("; ")]
    .map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\n");
  const a = Object.assign(document.createElement("a"), {href:URL.createObjectURL(new Blob([head + body], {type:"text/csv"})), download:"risk_based_sample.csv"});
  a.click();
};

// ---------- tests ----------
const maxCount = Math.max(...D.tests.map(t => t.count));
$("#testCards").innerHTML = D.tests.map(t => `<div class="card tcard" data-k="${t.key}"><div class="row"><span class="pts w${t.weight}">${t.weight ? t.weight + " pt" + (t.weight > 1 ? "s" : "") : "completeness"}</span>
  <span class="n">${t.count}</span></div><h3>${esc(t.title)}</h3><div class="bar"><span style="width:${100 * t.count / maxCount}%"></span></div><div class="basis">${esc(t.basis)}</div></div>`).join("");
document.querySelectorAll(".tcard").forEach(c => c.onclick = () => openTest(TEST[c.dataset.k]));

// ---------- benford ----------
const B = D.benford, bOpts = ["Whole ledger", ...Object.keys(B.users)];
$("#bUser").innerHTML = bOpts.map((u, i) => `<button class="${i ? "" : "on"}" data-u="${esc(u)}">${esc(u === "Whole ledger" ? "All" : u)}</button>`).join("");
const byUser = Object.fromEntries(B.by_user.map(u => [u.USNAM, u]));
$("#bUsers").innerHTML = B.by_user.map(u => `<li><span class="ok ${u.conformity === "nonconformity" ? "w" : ""}">${u.conformity === "nonconformity" ? "!" : "✓"}</span>
  <div><b>${esc(u.USNAM)}</b><div class="sub">${esc(u.conformity)} · digit ${u.most_overrepresented_digit} ${u.excess_share > 0 ? "+" : ""}${(100 * u.excess_share).toFixed(1)} pp</div></div><span class="mono sub">${u.MAD.toFixed(4)}</span></li>`).join("");
function drawBenford(u) {
  const obs = u === "Whole ledger" ? B.observed : B.users[u];
  const info = u === "Whole ledger" ? {MAD:B.mad, conformity:B.conformity} : byUser[u];
  $("#bTitle").textContent = u; $("#bMad").textContent = `MAD ${info.MAD.toFixed(4)} · ${info.conformity}`;
  const colors = obs.map((o, i) => o - B.expected[i] > 0.02 ? C.High : C.accent);
  if (charts.b) { charts.b.data.datasets[0].data = obs; charts.b.data.datasets[0].backgroundColor = colors; charts.b.update(); return; }
  charts.b = new Chart($("#cBenford"), {data:{labels:[1,2,3,4,5,6,7,8,9], datasets:[
    {type:"bar", label:"Observed", data:obs, backgroundColor:colors, borderRadius:5, order:2},
    {type:"line", label:"Benford's law", data:B.expected, borderColor:"#0f172a", borderWidth:2, pointRadius:3, pointBackgroundColor:"#0f172a", tension:.3, order:1}]},
    options:{maintainAspectRatio:false, plugins:{legend:{display:true, position:"top", align:"end", labels:{boxWidth:10, boxHeight:10}},
      tooltip:{callbacks:{label:c => `${c.dataset.label}: ${(100 * c.raw).toFixed(1)}%`}}},
      scales:{x:{grid:{display:false}, title:{display:true, text:"First digit"}}, y:{grid:{color:"#f1f5f9"}, ticks:{callback:v => `${Math.round(v * 100)}%`}}}}});
}
document.querySelectorAll("#bUser button").forEach(b => b.onclick = () => { document.querySelectorAll("#bUser button").forEach(x => x.classList.toggle("on", x === b)); drawBenford(b.dataset.u); });

// ---------- data quality ----------
const chk = (good, label, value) => `<li><span class="ok ${good ? "" : "w"}">${good ? "✓" : "!"}</span><span>${label}</span><b class="mono">${value}</b></li>`;
$("#popChecks").innerHTML = chk(true, "Postings in extract", int.format(P.postings)) + chk(true, "Total amount", eur.format(P.total) + " €")
  + chk(true, "Document range", `${P.first_document} – ${P.last_document}`) + chk(P.missing_numbers === 0, "Missing document numbers", P.missing_numbers)
  + chk(P.duplicate_keys === 0, "Duplicate document keys", P.duplicate_keys) + chk(P.months_covered === 12, "Months covered", `${P.months_covered} / 12`)
  + chk(true, "Users · G/L accounts", `${P.users} · ${P.accounts}`);
$("#popTotal").textContent = `${int.format(P.postings)} postings`;
function drawPop() {
  charts.p ??= new Chart($("#cPop"), {type:"bar", data:{labels:D.months, datasets:[{data:P.per_month, backgroundColor:C.accent, borderRadius:5}]},
    options:{maintainAspectRatio:false, scales:{x:{grid:{display:false}}, y:{grid:{color:"#f1f5f9"}}}}});
}

// ---------- method ----------
$("#rules").innerHTML = D.tests.map(t => `<tr style="cursor:default"><td><b>${esc(t.title)}</b></td><td style="white-space:normal">${esc(t.rule)}</td>
  <td class="n"><span class="pts w${t.weight}">${t.weight}</span></td><td style="white-space:normal">${esc(t.basis)}</td></tr>`).join("");

// ---------- detail drawer ----------
function drawer(kicker, title, body) {
  $("#dKicker").textContent = kicker; $("#dTitle").textContent = title; $("#dBody").innerHTML = body;
  document.body.classList.add("open"); $("#dClose").focus();
}
const closeDrawer = () => document.body.classList.remove("open");
$("#dClose").onclick = closeDrawer; $("#bg").onclick = closeDrawer;
document.addEventListener("keydown", e => e.key === "Escape" && closeDrawer());
function openRow(r) {
  drawer(`Posting · rank ${r.rank} of ${rows.length}`, `Document ${r.doc}`,
    `<div style="display:flex;gap:10px;align-items:center;margin-bottom:16px"><span class="score ${r.level}" style="width:44px;height:36px;font-size:16px">${r.score}</span>
     <div><b>${r.level} risk</b><div class="sub">${r.keys.length} failed test${r.keys.length > 1 ? "s" : ""}</div></div><b style="margin-left:auto;font-size:18px">${eur.format(r.amount)} €</b></div>
     <dl><dt>Posting date</dt><dd>${r.date}</dd><dt>Entered</dt><dd>${r.entered || "–"} ${r.time ? "at " + esc(r.time) : ""}</dd>
     <dt>Entered by</dt><dd>${esc(r.user)}</dd><dt>Approved by</dt><dd>${esc(r.approver)}</dd><dt>G/L account</dt><dd>${esc(r.account)}</dd>
     <dt>Vendor</dt><dd>${esc(r.vendor)}</dd><dt>Text</dt><dd>${r.text ? esc(r.text) : '<span class="sub">— no description —</span>'}</dd></dl>
     <h3 style="font-size:13px;margin:0 0 8px">Why it was flagged</h3>` +
    r.keys.map(k => TEST[k]).sort((a, b) => b.weight - a.weight).map(t => `<div class="hit"><div class="row"><b>${esc(t.title)}</b><span class="pts w${t.weight}">+${t.weight}</span></div>
     <p>${esc(t.why)}</p><p style="color:#94a3b8">${esc(t.basis)}</p></div>`).join(""));
}
function openTest(t) {
  const byDoc = Object.fromEntries(rows.map(r => [r.doc, r]));
  const list = t.key === "number_gaps"
    ? `<ul class="list">${t.gaps.map(g => `<li style="cursor:default"><span class="mono">${g.first_missing}${g.first_missing !== g.last_missing ? " – " + g.last_missing : ""}</span><span class="sub">${g.missing} missing</span></li>`).join("")}</ul>`
    : `<ul class="list">${t.docs.map(d => byDoc[d]).filter(Boolean).map(r => `<li data-doc="${r.doc}"><span class="mono">${r.doc}</span><span class="sub">${esc(r.user)} · ${r.date}</span><b>${eur.format(r.amount)} €</b></li>`).join("")}</ul>`;
  drawer(`Test · ${t.weight ? t.weight + " risk point" + (t.weight > 1 ? "s" : "") : "completeness"}`, t.title,
    `<p style="margin-top:0">${esc(t.why)}</p><dl><dt>Rule</dt><dd>${esc(t.rule)}</dd><dt>Basis</dt><dd>${esc(t.basis)}</dd><dt>Findings</dt><dd><b>${t.count}</b></dd></dl>` + list);
  document.querySelectorAll("#dBody li[data-doc]").forEach(li => li.onclick = () => openRow(byDoc[li.dataset.doc]));
}

// ---------- views ----------
const titles = {overview:"Overview", ranking:"Risk ranking", tests:"Tests", benford:"Benford's law", quality:"Data quality", method:"Method"};
function show() {
  const v = titles[location.hash.slice(1)] ? location.hash.slice(1) : "overview";
  document.querySelectorAll(".view").forEach(s => s.classList.toggle("on", s.id === "v-" + v));
  document.querySelectorAll("aside nav a").forEach(a => a.classList.toggle("on", a.dataset.view === v));
  $("#crumb").textContent = titles[v]; closeDrawer(); window.scrollTo(0, 0);
  if (v === "overview") drawOverview();
  if (v === "ranking") drawRows();
  if (v === "benford" && !charts.b) drawBenford("Whole ledger");
  if (v === "quality") drawPop();
}
window.addEventListener("hashchange", show); show();
</script>
</body></html>"""


if __name__ == "__main__":
    import sys
    print("Wrote", build(sys.argv[1] if len(sys.argv) > 1 else ""))
