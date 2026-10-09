"""Journal-entry tests as used in financial-statement audits.

Each check takes the journal entries and returns the flagged rows with a reason.
Most checks are plain SQL on an in-memory SQLite table, the way they'd be written
against an ERP extract; the date and Benford tests use pandas.
"""

import io
import sqlite3
from dataclasses import dataclass

import holidays
import numpy as np
import pandas as pd

REQUIRED = ["BELNR", "BUDAT", "HKONT", "DMBTR", "LIFNR", "USNAM", "FREIGABE"]


@dataclass
class CheckResult:
    key: str
    title: str
    why: str          # why an auditor cares
    flagged: pd.DataFrame


def load_entries(source) -> pd.DataFrame:
    """Read a CSV of journal entries (path or uploaded file) and validate the columns."""
    df = pd.read_csv(source, dtype={"HKONT": str, "LIFNR": str, "BUKRS": str})
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {', '.join(missing)}")
    df["BUDAT"] = pd.to_datetime(df["BUDAT"])
    df["DMBTR"] = pd.to_numeric(df["DMBTR"])
    return df


def to_sqlite(df: pd.DataFrame) -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    out = df.copy()
    out["BUDAT"] = out["BUDAT"].dt.strftime("%Y-%m-%d")
    out.to_sql("je", con, index=False)
    return con


def duplicates(con) -> pd.DataFrame:
    """Same vendor, account, amount, date and text posted more than once."""
    return pd.read_sql("""
        SELECT je.*, d.n AS copies
        FROM je
        JOIN (SELECT LIFNR, HKONT, DMBTR, BUDAT, BKTXT, COUNT(*) AS n
              FROM je GROUP BY LIFNR, HKONT, DMBTR, BUDAT, BKTXT HAVING COUNT(*) > 1) d
          USING (LIFNR, HKONT, DMBTR, BUDAT, BKTXT)
        ORDER BY LIFNR, DMBTR, BELNR""", con)


def number_gaps(con) -> pd.DataFrame:
    """Missing document numbers in an otherwise continuous sequence."""
    return pd.read_sql("""
        SELECT prev + 1 AS first_missing, BELNR - 1 AS last_missing, BELNR - prev - 1 AS missing
        FROM (SELECT BELNR, LAG(BELNR) OVER (ORDER BY BELNR) AS prev FROM je)
        WHERE BELNR - prev > 1
        ORDER BY prev""", con)


def weekend_holiday(df: pd.DataFrame, subdiv: str = "BW") -> pd.DataFrame:
    """Postings dated on a Saturday, Sunday or public holiday."""
    years = sorted(df["BUDAT"].dt.year.unique().tolist())
    hol = holidays.Germany(subdiv=subdiv, years=years)
    is_weekend = df["BUDAT"].dt.weekday >= 5
    is_holiday = df["BUDAT"].dt.date.isin(hol)
    out = df[is_weekend | is_holiday].copy()
    out["reason"] = np.where(out["BUDAT"].dt.date.isin(hol),
                             out["BUDAT"].dt.date.map(lambda d: hol.get(d) or ""),
                             out["BUDAT"].dt.day_name())
    return out


def round_amounts(con, unit: int = 1000) -> pd.DataFrame:
    """Whole multiples of 1,000 - typical for estimates, manual entries or made-up amounts."""
    return pd.read_sql(f"""
        SELECT * FROM je
        WHERE DMBTR >= {unit} AND DMBTR = CAST(DMBTR AS INTEGER)
          AND CAST(DMBTR AS INTEGER) % {unit} = 0
        ORDER BY DMBTR DESC""", con)


def below_limit(con, limit: float = 5000.0, band: float = 0.10) -> pd.DataFrame:
    """Amounts just under the approval limit, with how often each user does it."""
    low = limit * (1 - band)
    return pd.read_sql(f"""
        SELECT je.*, u.n AS user_count_in_band
        FROM je
        JOIN (SELECT USNAM, COUNT(*) AS n FROM je
              WHERE DMBTR >= {low} AND DMBTR < {limit} GROUP BY USNAM) u USING (USNAM)
        WHERE DMBTR >= {low} AND DMBTR < {limit}
        ORDER BY u.n DESC, DMBTR DESC""", con)


def segregation_of_duties(con) -> pd.DataFrame:
    """The same user entered and approved the posting (four-eyes principle broken)."""
    return pd.read_sql("SELECT * FROM je WHERE USNAM = FREIGABE ORDER BY USNAM, BELNR", con)


BENFORD = np.log10(1 + 1 / np.arange(1, 10))  # expected share of first digits 1..9


def benford(df: pd.DataFrame) -> tuple[pd.DataFrame, float, str]:
    """First-digit test. Returns (table, MAD, conformity) using Nigrini's MAD thresholds."""
    amounts = df.loc[df["DMBTR"] >= 10, "DMBTR"]
    first = amounts.astype(str).str.lstrip("0.").str[0].astype(int)
    observed = first.value_counts(normalize=True).reindex(range(1, 10), fill_value=0)
    table = pd.DataFrame({"digit": range(1, 10), "observed": observed.values, "expected": BENFORD})
    table["difference"] = table["observed"] - table["expected"]
    mad = float(table["difference"].abs().mean())
    conformity = ("close conformity" if mad < 0.006 else "acceptable conformity" if mad < 0.012
                  else "marginally acceptable" if mad < 0.015 else "nonconformity")
    return table, mad, conformity


def benford_by_user(df: pd.DataFrame, min_postings: int = 100) -> pd.DataFrame:
    """Benford per user: a whole ledger can conform while one person's postings don't."""
    rows = []
    for user, part in df.groupby("USNAM"):
        if (part["DMBTR"] >= 10).sum() >= min_postings:
            table, mad, conformity = benford(part)
            top = table.loc[table["difference"].idxmax()]
            rows.append({"USNAM": user, "postings": len(part), "MAD": round(mad, 4),
                         "conformity": conformity,
                         "most_overrepresented_digit": int(top["digit"]),
                         "excess_share": round(float(top["difference"]), 3)})
    return pd.DataFrame(rows).sort_values("MAD", ascending=False, ignore_index=True)


def run_all(df: pd.DataFrame, limit: float = 5000.0) -> list[CheckResult]:
    con = to_sqlite(df)
    return [
        CheckResult("duplicates", "Duplicate postings",
                    "Paying the same invoice twice is a classic error - and a classic fraud.",
                    duplicates(con)),
        CheckResult("number_gaps", "Gaps in document numbers",
                    "Missing numbers can mean deleted postings; completeness must be explained.",
                    number_gaps(con)),
        CheckResult("weekend_holiday", "Weekend and holiday postings",
                    "Postings outside normal working days avoid the usual review and controls.",
                    weekend_holiday(df)),
        CheckResult("round_amounts", "Round amounts",
                    "Real invoices rarely come to exact thousands; round figures suggest estimates or manual entries.",
                    round_amounts(con)),
        CheckResult("below_limit", f"Just below the approval limit ({limit:,.0f} EUR)",
                    "Splitting invoices to stay under the limit avoids the second approval.",
                    below_limit(con, limit)),
        CheckResult("segregation_of_duties", "Segregation of duties",
                    "One person entering and approving the same posting breaks the four-eyes principle.",
                    segregation_of_duties(con)),
    ]


def exception_list(results: list[CheckResult]) -> bytes:
    """All flagged entries as an Excel workbook: a summary sheet plus one sheet per check."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xl:
        pd.DataFrame({"Check": [r.title for r in results],
                      "Findings": [len(r.flagged) for r in results],
                      "Why it matters": [r.why for r in results]}).to_excel(xl, sheet_name="Summary", index=False)
        for r in results:
            r.flagged.to_excel(xl, sheet_name=r.key[:31], index=False)
    return buf.getvalue()
