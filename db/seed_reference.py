"""Seed reference tables: source authorities, CICTT categories, the
CADORS-to-CICTT mapping, and the date dimension.

Key-stable and idempotent: existing authorities, categories and dates keep
their surrogate keys; only missing rows are added. map_source_category is
rebuilt from db/map_source_category.csv on every run.

Usage:  python db/seed_reference.py
"""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "etl"))
from db import get_connection  # noqa: E402
from sqlbulk import bulk_insert, literal  # noqa: E402

AUTHORITIES = [
    ("Transport Canada", "CA",
     "CADORS occurrences involving Canadian-registered aircraft, Canadian airports, "
     "and airspace under Canadian responsibility.",
     "Preliminary reports; subject to change. Structured fields only, no narrative text."),
    ("NTSB", "US",
     "US civil aviation accidents and selected incidents investigated by the NTSB.",
     "Investigations take 1-2 years; recent records often lack a probable cause."),
    ("BTS", "US",
     "On-time performance for US domestic flights by reporting carriers.",
     "Carriers above 0.5% of domestic passenger revenue; ~3 month publication lag; "
     "delayed means 15+ minutes."),
]

# CICTT v4.8 has one category CADORS does not use. Seeded so NTSB records
# can be classified into it.
EXTRA_CICTT = [("LOLI", "Loss of lifting conditions en route")]


def rows(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def main():
    conn = get_connection()
    cur = conn.cursor()

    # ---------- authorities ----------
    for name, country, cov, notes in AUTHORITIES:
        cur.execute(f"""
            IF NOT EXISTS (SELECT 1 FROM dim_source_authority WHERE name = {literal(name)})
            INSERT INTO dim_source_authority (name, country, coverage_description, reporting_threshold_notes)
            VALUES ({literal(name)}, {literal(country)}, {literal(cov)}, {literal(notes)})""")
    conn.commit()
    auth = dict((n, k) for k, n in rows(cur, "SELECT authority_key, name FROM dim_source_authority"))
    print(f"authorities: {auth}")

    # ---------- CICTT categories ----------
    m = pd.read_csv(os.path.join(HERE, "map_source_category.csv"))
    cats = m[["cictt_code", "cictt_label"]].drop_duplicates("cictt_code")
    cats = pd.concat([cats, pd.DataFrame(EXTRA_CICTT, columns=["cictt_code", "cictt_label"])],
                     ignore_index=True).drop_duplicates("cictt_code")
    for code, label in cats.itertuples(index=False):
        excl = 1 if code == "OTHR" else 0
        cur.execute(f"""
            IF NOT EXISTS (SELECT 1 FROM dim_category WHERE cictt_code = {literal(code)})
            INSERT INTO dim_category (cictt_code, cictt_label, exclude_from_charts)
            VALUES ({literal(code)}, {literal(label)}, {excl})""")
    conn.commit()
    cat = dict((c, k) for k, c in rows(cur, "SELECT category_key, cictt_code FROM dim_category"))
    print(f"categories: {len(cat)}")

    # ---------- mapping (rebuilt each run) ----------
    m["authority_key"] = m["authority_name"].map(auth)
    m["category_key"] = m["cictt_code"].map(cat)
    missing = m[m["authority_key"].isna() | m["category_key"].isna()]
    assert missing.empty, f"unresolved mapping rows:\n{missing}"
    cur.execute("TRUNCATE TABLE map_source_category")
    conn.commit()
    bulk_insert(conn, "map_source_category",
                ["authority_key", "source_category_label", "category_key", "mapping_confidence", "mapping_notes"],
                m, label="map_source_category")

    # ---------- dim_date, 2014 (corpus start) to 2027 ----------
    have = {r[0] for r in rows(cur, "SELECT date_key FROM dim_date")}
    d = pd.DataFrame({"full_date": pd.date_range("2014-01-01", "2027-12-31", freq="D")})
    d["date_key"] = d["full_date"].dt.strftime("%Y%m%d").astype(int)
    d = d[~d["date_key"].isin(have)]
    if len(d):
        d["year"] = d["full_date"].dt.year
        d["quarter"] = d["full_date"].dt.quarter
        d["month"] = d["full_date"].dt.month
        d["month_name"] = d["full_date"].dt.month_name()
        d["day_of_week"] = d["full_date"].dt.dayofweek + 1          # 1 = Monday
        d["season"] = d["month"].map({12: "Winter", 1: "Winter", 2: "Winter", 3: "Spring", 4: "Spring",
                                      5: "Spring", 6: "Summer", 7: "Summer", 8: "Summer", 9: "Fall",
                                      10: "Fall", 11: "Fall"})
        d["full_date"] = d["full_date"].dt.date
        bulk_insert(conn, "dim_date",
                    ["date_key", "full_date", "year", "quarter", "month", "month_name", "day_of_week", "season"],
                    d, label="dim_date")
    print(f"dim_date: {len(have) + len(d):,} days")

    for t in ["dim_source_authority", "dim_category", "map_source_category", "dim_date"]:
        print(f"  {t}: {rows(cur, f'SELECT COUNT(*) FROM {t}')[0][0]:,}")
    conn.close()


if __name__ == "__main__":
    main()
