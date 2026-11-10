"""Generate a synthetic general-ledger extract (journal entries) for fiscal year 2025.

The data is made up. It uses SAP-style field names (as in table BSEG/BKPF) and
contains deliberately planted anomalies, so every audit check has something to
find and the tests can prove that it finds it.

    python data/generate_sample.py      -> data/journal_entries_sample.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd

ACCOUNTS = {  # G/L account -> description
    "400000": "Materialaufwand",
    "410000": "Bürobedarf",
    "420000": "Reisekosten",
    "430000": "Beratungskosten",
    "440000": "IT-Dienstleistungen",
    "450000": "Mietaufwand",
    "460000": "Werbekosten",
    "470000": "Instandhaltung",
}
VENDORS = [f"V{n:05d}" for n in range(10001, 10041)]
USERS = ["SCHMIDT_A", "WEBER_K", "FISCHER_L", "BECKER_M", "HOFFMANN_S", "KOCH_J"]
MANAGER = "SCHULZ_T"  # head of finance: approves, but normally doesn't post entries herself
APPROVERS = ["MEYER_R", "WAGNER_P", "BAUER_C"]
APPROVAL_LIMIT = 5000.0  # postings at or above this need a second approval level
OUT = Path(__file__).with_name("journal_entries_sample.csv")


def working_days(year: int) -> pd.DatetimeIndex:
    days = pd.bdate_range(f"{year}-01-01", f"{year}-12-31")
    import holidays
    bw = holidays.Germany(subdiv="BW", years=year)
    return days[~days.isin(pd.to_datetime(list(bw.keys())))]


def generate(n: int = 4000, seed: int = 42) -> tuple[pd.DataFrame, dict]:
    """Return (journal entries, planted anomalies) - the second part is the answer key."""
    rng = np.random.default_rng(seed)
    days = working_days(2025)
    accounts = list(ACCOUNTS)

    # Log-normal amounts spread over several orders of magnitude follow Benford's law closely.
    amounts = np.round(np.exp(rng.normal(6.2, 1.6, n)), 2).clip(1.0, 250_000)
    df = pd.DataFrame({
        "BELNR": np.arange(5100000001, 5100000001 + n),
        "BUKRS": "1000",
        "GJAHR": 2025,
        "BUDAT": rng.choice(days, n),
        "HKONT": rng.choice(accounts, n),
        "DMBTR": amounts,
        "SHKZG": "S",
        "LIFNR": rng.choice(VENDORS, n),
        "USNAM": rng.choice(USERS, n),
        "FREIGABE": rng.choice(APPROVERS, n),
    })
    df["BKTXT"] = "Rechnung " + df["LIFNR"] + " " + df["BUDAT"].dt.strftime("%m/%Y")
    planted: dict[str, list] = {}

    # 1. Duplicate postings: same vendor, account, amount, date and text, new document number.
    src = rng.choice(n, 12, replace=False)
    dups = df.iloc[src].copy()
    df = pd.concat([df, dups], ignore_index=True)
    df.loc[df.index[-12:], "BELNR"] = np.arange(df["BELNR"].max() + 1, df["BELNR"].max() + 13)
    planted["duplicates"] = sorted(df.loc[df.index[-12:], "BELNR"].tolist())

    # 2. Gaps in the document number sequence (deleted or never-posted documents).
    gaps = sorted(rng.choice(df["BELNR"].iloc[100:-100], 5, replace=False).tolist())
    df = df[~df["BELNR"].isin(gaps)].reset_index(drop=True)
    planted["number_gaps"] = gaps

    # From here on, each anomaly gets its own fresh documents so they don't overlap.
    protected = set(planted["duplicates"]) | set(df.loc[src, "BELNR"]) | {g - 1 for g in gaps} | {g + 1 for g in gaps}
    pool = [b for b in df["BELNR"] if b not in protected]
    rng.shuffle(pool)

    def take(k: int) -> pd.Series:
        chosen = [pool.pop() for _ in range(k)]
        return df["BELNR"].isin(chosen)

    # 3. Postings on weekends and public holidays.
    rows = take(25)
    odd_days = pd.to_datetime(["2025-01-01", "2025-04-18", "2025-05-01", "2025-12-25", "2025-12-26"]
                              + [d.strftime("%Y-%m-%d") for d in pd.date_range("2025-03-02", "2025-11-30", freq="W-SUN")[:20]])
    df.loc[rows, "BUDAT"] = odd_days
    planted["weekend_holiday"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 4. Suspiciously round amounts.
    rows = take(30)
    df.loc[rows, "DMBTR"] = rng.choice([2000, 5000, 10000, 15000, 20000, 50000], 30).astype(float)
    planted["round_amounts"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 5. Segregation of duties: the person who entered the posting also approved it.
    rows = take(8)
    df.loc[rows, "FREIGABE"] = df.loc[rows, "USNAM"]
    planted["segregation_of_duties"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 6. One user splits invoices to stay just below the approval limit -
    #    this also bends the first-digit distribution (too many 4s) for the Benford test.
    rows = take(60)
    df.loc[rows, "DMBTR"] = np.round(rng.uniform(4500, APPROVAL_LIMIT - 0.01, 60), 2)
    df.loc[rows, "USNAM"] = "KOCH_J"
    df.loc[rows, "HKONT"] = "430000"
    planted["below_limit"] = sorted(df.loc[rows, "BELNR"].tolist())

    # Entry date and time (CPUDT/CPUTM, as in table BKPF): normally the posting day, office hours.
    # A second generator keeps every anomaly above exactly as it was before these fields existed.
    extra = np.random.default_rng(seed + 1)
    df["CPUDT"] = df["BUDAT"]
    df["CPUTM"] = [f"{h:02d}:{m:02d}:{s:02d}" for h, m, s in
                   zip(extra.integers(7, 18, len(df)), extra.integers(0, 60, len(df)), extra.integers(0, 60, len(df)))]

    # 7. Post-closing entries: entered in January 2026 but dated into December 2025.
    rows = take(10)
    df.loc[rows, "BUDAT"] = pd.to_datetime(extra.choice(["2025-12-29", "2025-12-30", "2025-12-31"], 10))
    df.loc[rows, "CPUDT"] = pd.to_datetime("2026-01-05") + pd.to_timedelta(extra.integers(0, 14, 10), unit="D")
    planted["post_closing"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 8. Entries made late at night.
    rows = take(15)
    df.loc[rows, "CPUTM"] = [f"{h:02d}:{m:02d}:00" for h, m in
                             zip(extra.choice([22, 23, 0, 1, 2, 3], 15), extra.integers(0, 60, 15))]
    planted["after_hours"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 9. Entries without a description.
    rows = take(12)
    df.loc[rows, "BKTXT"] = ""
    planted["missing_description"] = sorted(df.loc[rows, "BELNR"].tolist())

    # 10. Management override (ISA 240): the head of finance, who rarely posts, books round amounts
    #     after closing, late at night and without a description. Several tests hit the same entries.
    rows = take(3)
    df.loc[rows, ["USNAM", "BUDAT", "CPUTM", "BKTXT", "DMBTR", "HKONT"]] = \
        [MANAGER, pd.Timestamp("2025-12-31"), "23:41:00", "", 25000.0, "430000"]
    df.loc[rows, "CPUDT"] = pd.Timestamp("2026-01-09")
    planted["override"] = sorted(df.loc[rows, "BELNR"].tolist())
    rows = take(6)  # her other postings: normal, but she is still a rare poster
    df.loc[rows, "USNAM"] = MANAGER
    planted["rare_users"] = sorted(df.loc[rows, "BELNR"].tolist() + planted["override"])

    df["KONTO_TEXT"] = df["HKONT"].map(ACCOUNTS)
    df = df.sort_values("BELNR").reset_index(drop=True)
    cols = ["BELNR", "BUKRS", "GJAHR", "BUDAT", "HKONT", "KONTO_TEXT", "DMBTR", "SHKZG",
            "LIFNR", "BKTXT", "USNAM", "FREIGABE", "CPUDT", "CPUTM"]
    return df[cols], planted


if __name__ == "__main__":
    data, answer_key = generate()
    data.to_csv(OUT, index=False, date_format="%Y-%m-%d")
    print(f"Wrote {len(data)} journal entries to {OUT.name}")
    for check, belnrs in answer_key.items():
        print(f"  planted {len(belnrs):>3} x {check}")
