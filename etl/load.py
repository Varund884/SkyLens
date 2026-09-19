"""Load staged parquet into Azure SQL.

Resolves the natural identifiers written by the parsers (ICAO ident, CICTT
code, authority name, carrier code) to surrogate keys, then bulk-inserts.

Usage
  python etl/load.py --smoke          small sample of every table (~1 min).
                                      Run this first; it proves the whole path.
  python etl/load.py --skip-flights   everything except the 7M-row flight table
  python etl/load.py --flights-only   just the flight table. Re-run to resume:
                                      complete months are skipped, a partial
                                      month is deleted and reloaded.
  python etl/load.py --movements-only just fact_airport_movements (e.g. after
                                      adding a new movement source)
  python etl/load.py                  everything

Requires db/schema.sql, db/migrate_001.sql and db/seed_reference.py to have run.
"""
import argparse
import sys
import time

import pandas as pd

from common import AUTH_NTSB, AUTH_TC, STAGED, load_staged
from db import get_connection
from sqlbulk import bulk_insert, date_key

SMOKE_ROWS = 1000

AIRPORT_COLS = ["ident", "iata_code", "local_code", "name", "airport_type", "latitude", "longitude",
                "elevation_ft", "iso_country", "iso_region", "municipality", "runway_count",
                "longest_runway_ft", "is_closed"]
OCC_COLS = ["authority_key", "source_record_id", "date_key", "airport_key", "category_key",
            "occurrence_type", "phase_of_flight", "severity_tier", "fatalities", "injuries",
            "source_text", "findings", "findings_l1", "flight_number", "registration",
            "in_analysis_window", "occurrence_time_utc", "occurrence_country", "event_names",
            "aircraft_count", "operator_name", "damage"]
AIR_COLS = ["occurrence_key", "aircraft_seq", "flight_number", "registration", "operator_name",
            "phase_of_flight", "damage", "make", "model", "year_built"]
MOVE_COLS = ["airport_key", "date_key", "movement_count", "is_estimated", "source"]
FLIGHT_COLS = ["date_key", "operator_key", "flight_number", "tail_number", "origin_airport_key",
               "dest_airport_key", "sched_dep", "actual_dep", "dep_delay_min", "taxi_out_min",
               "wheels_off", "wheels_on", "taxi_in_min", "sched_arr", "actual_arr", "arr_delay_min",
               "air_time_min", "distance_mi", "cancelled", "cancellation_code", "diverted",
               "div_airport", "carrier_delay_min", "weather_delay_min", "nas_delay_min",
               "security_delay_min", "late_aircraft_delay_min"]
FLIGHT_INDEXES = ["ix_perf_flight", "ix_perf_date", "ix_perf_tail"]


def q(cur, sql):
    cur.execute(sql)
    return cur.fetchall()


def lookup(cur, sql):
    return {k: v for v, k in q(cur, sql)}


def truncate(conn, *tables):
    cur = conn.cursor()
    for t in tables:
        cur.execute(f"TRUNCATE TABLE {t}")
    conn.commit()
    print(f"truncated: {', '.join(tables)}")


def require_seed(cur):
    auth = lookup(cur, "SELECT authority_key, name FROM dim_source_authority")
    cats = lookup(cur, "SELECT category_key, cictt_code FROM dim_category")
    if not {AUTH_TC, AUTH_NTSB} <= set(auth) or len(cats) < 30:
        sys.exit("reference tables are empty: run  python db/seed_reference.py  first")
    return auth, cats


def map_or_fail(values: pd.Series, lut: dict, what: str) -> pd.Series:
    out = values.map(lut)
    missing = values[values.notna() & out.isna()]
    if len(missing):
        sys.exit(f"{len(missing)} {what} values have no key, e.g. {missing.unique()[:5].tolist()}")
    return out.astype("Int64")


# ---------------------------------------------------------------- dimensions
def load_dims(conn):
    ap = load_staged("dim_airport")
    bulk_insert(conn, "dim_airport", AIRPORT_COLS, ap)
    ops = load_staged("dim_operator")
    bulk_insert(conn, "dim_operator", ["name", "iata_code"], ops)


# ---------------------------------------------------------------- occurrences
def load_occurrences(conn, auth, cats, airports, smoke):
    cur = conn.cursor()
    occ = pd.concat([load_staged("cadors_occ"), load_staged("ntsb_occ")], ignore_index=True)
    cat = load_staged("cadors_cat")
    air = pd.concat([load_staged("cadors_air"), load_staged("ntsb_air")], ignore_index=True)
    if smoke:
        occ = pd.concat([occ[occ["authority_name"] == AUTH_TC].head(SMOKE_ROWS // 2),
                         occ[occ["authority_name"] == AUTH_NTSB].head(SMOKE_ROWS // 2)])
        keep = set(occ["source_record_id"])
        cat, air = cat[cat["source_record_id"].isin(keep)], air[air["source_record_id"].isin(keep)]

    occ["authority_key"] = map_or_fail(occ["authority_name"], auth, "authority")
    occ["date_key"] = date_key(occ["occ_date"])
    occ["airport_key"] = map_or_fail(occ["airport_ident"], airports, "airport")
    occ["category_key"] = map_or_fail(occ["primary_cictt"], cats, "CICTT")
    # Long NTSB text makes big statements; smaller batches keep them ~1 MB.
    bulk_insert(conn, "fact_occurrence", OCC_COLS, occ, batch=250)

    keys = pd.DataFrame(q(cur, "SELECT occurrence_key, authority_key, source_record_id FROM fact_occurrence"),
                        columns=["occurrence_key", "authority_key", "source_record_id"])
    tc_keys = keys[keys["authority_key"] == auth[AUTH_TC]].set_index("source_record_id")["occurrence_key"]
    all_keys = keys.set_index(["authority_key", "source_record_id"])["occurrence_key"]

    cat["occurrence_key"] = map_or_fail(cat["source_record_id"], tc_keys.to_dict(), "occurrence")
    cat["category_key"] = map_or_fail(cat["cictt_code"], cats, "CICTT")
    bulk_insert(conn, "bridge_occurrence_category", ["occurrence_key", "category_key"], cat)

    src_auth = occ.set_index("source_record_id")["authority_key"]
    air["authority_key"] = air["source_record_id"].map(src_auth)
    air["occurrence_key"] = pd.Series(
        [all_keys.get((a, s)) for a, s in zip(air["authority_key"], air["source_record_id"])],
        index=air.index, dtype="Int64")
    assert air["occurrence_key"].notna().all(), "aircraft rows without a parent occurrence"
    bulk_insert(conn, "fact_occurrence_aircraft", AIR_COLS, air)
    return len(occ), len(cat), len(air)


# ---------------------------------------------------------------- movements
def load_movements(conn, airports, smoke):
    m = load_staged("movements")
    if smoke:
        m = m.head(SMOKE_ROWS)
    m["airport_key"] = map_or_fail(m["airport_ident"], airports, "airport")
    m["date_key"] = date_key(m["movement_date"])
    bulk_insert(conn, "fact_airport_movements", MOVE_COLS, m)
    return len(m)


# ---------------------------------------------------------------- flights
def month_range(path):
    y, mo = map(int, path.stem.split("_"))
    start = y * 10000 + mo * 100 + 1
    return start, start + 30


def load_flights(conn, airports, operators, smoke, resume):
    cur = conn.cursor()
    files = sorted((STAGED / "bts").glob("*.parquet"))
    assert files, "no staged flights: run  python etl/bts.py"
    if not smoke:
        for ix in FLIGHT_INDEXES:   # disable secondary indexes during the bulk load
            cur.execute(f"IF EXISTS (SELECT 1 FROM sys.indexes WHERE name='{ix}') "
                        f"ALTER INDEX {ix} ON fact_flight_performance DISABLE")
        conn.commit()
    total, start = 0, time.time()
    for f in files:
        lo, hi = month_range(f)
        df = pd.read_parquet(f)
        if smoke:
            df = df.head(SMOKE_ROWS)
        if resume:
            have = q(cur, f"SELECT COUNT(*) FROM fact_flight_performance WHERE date_key BETWEEN {lo} AND {hi}")[0][0]
            if have == len(df):
                print(f"  {f.stem}: already loaded ({have:,}), skipping")
                continue
            if have:
                print(f"  {f.stem}: partial ({have:,} of {len(df):,}), deleting and reloading")
                cur.execute(f"DELETE FROM fact_flight_performance WHERE date_key BETWEEN {lo} AND {hi}")
                conn.commit()
        df["date_key"] = date_key(df["flight_date"])
        df["operator_key"] = map_or_fail(df["carrier_code"], operators, "carrier")
        df["origin_airport_key"] = map_or_fail(df["origin_ident"], airports, "airport")
        df["dest_airport_key"] = map_or_fail(df["dest_ident"], airports, "airport")
        total += bulk_insert(conn, "fact_flight_performance", FLIGHT_COLS, df, label=f"flights {f.stem}")
        if smoke:
            break
    if not smoke:
        print("  rebuilding flight indexes ...")
        cur.execute("ALTER INDEX ALL ON fact_flight_performance REBUILD")
        conn.commit()
    print(f"  flights: {total:,} rows in {(time.time() - start) / 60:,.1f} min")
    return total


# ---------------------------------------------------------------- verify
def verify(conn, expected):
    cur = conn.cursor()
    print("\nverification")
    ok = True
    for table, n in expected.items():
        got = q(cur, f"SELECT COUNT(*) FROM {table}")[0][0]
        flag = "ok" if got == n else "MISMATCH"
        ok &= got == n
        print(f"  {table:28s} expected {n:>10,}  got {got:>10,}  {flag}")
    rows = q(cur, "SELECT in_analysis_window, COUNT(*) FROM fact_occurrence GROUP BY in_analysis_window")
    print(f"  in_analysis_window split: {dict(rows)}")
    print(f"  guard view rows: {q(cur, 'SELECT COUNT(*) FROM v_occurrence_analysis')[0][0]:,}")
    return ok


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--skip-flights", action="store_true")
    p.add_argument("--flights-only", action="store_true")
    p.add_argument("--movements-only", action="store_true")
    a = p.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    auth, cats = require_seed(cur)
    expected = {}

    if a.movements_only:
        airports = lookup(cur, "SELECT airport_key, ident FROM dim_airport")
        if not airports:
            sys.exit("dim_airport is empty: run a full load first")
        truncate(conn, "fact_airport_movements")
        expected["fact_airport_movements"] = load_movements(conn, airports, smoke=False)
    elif a.flights_only:
        airports = lookup(cur, "SELECT airport_key, ident FROM dim_airport")
        operators = lookup(cur, "SELECT operator_key, iata_code FROM dim_operator")
        if not airports:
            sys.exit("dim_airport is empty: run a load without --flights-only first")
        expected["fact_flight_performance"] = sum(
            len(pd.read_parquet(f, columns=["carrier_code"])) for f in (STAGED / "bts").glob("*.parquet"))
        load_flights(conn, airports, operators, smoke=False, resume=True)
    else:
        truncate(conn, "fact_flight_performance", "fact_occurrence_aircraft", "bridge_occurrence_category",
                 "fact_airport_movements", "fact_occurrence", "dim_airport", "dim_operator")
        load_dims(conn)
        airports = lookup(cur, "SELECT airport_key, ident FROM dim_airport")
        operators = lookup(cur, "SELECT operator_key, iata_code FROM dim_operator")
        expected["dim_airport"] = len(load_staged("dim_airport"))
        expected["dim_operator"] = len(operators)
        n_occ, n_cat, n_air = load_occurrences(conn, auth, cats, airports, a.smoke)
        expected.update({"fact_occurrence": n_occ, "bridge_occurrence_category": n_cat,
                         "fact_occurrence_aircraft": n_air})
        expected["fact_airport_movements"] = load_movements(conn, airports, a.smoke)
        if not a.skip_flights:
            expected["fact_flight_performance"] = load_flights(conn, airports, operators, a.smoke, resume=False)

    ok = verify(conn, expected)
    conn.close()
    if a.smoke and ok:
        print("\nsmoke test passed. Next:  python etl/load.py --skip-flights  then  --flights-only")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
