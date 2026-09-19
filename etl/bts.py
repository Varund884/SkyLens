"""BTS On-Time Performance -> staged flights, one parquet per month.

Processes a month at a time: 12 months is ~7.0M rows, too much to hold in
memory comfortably.

Coverage: US domestic flights by carriers above 0.5% of domestic passenger
revenue. Reports territories (PR, VI, GU, AS, MP) as domestic.
"""
import re

import pandas as pd

from common import NO_NA, RAW, STAGED, clean_str, load_staged, resolve_airport, save

COLS = ["FlightDate", "Reporting_Airline", "Tail_Number", "Flight_Number_Reporting_Airline",
        "Origin", "Dest", "CRSDepTime", "DepTime", "DepDelay", "TaxiOut", "WheelsOff",
        "WheelsOn", "TaxiIn", "CRSArrTime", "ArrTime", "ArrDelay", "Cancelled",
        "CancellationCode", "Diverted", "AirTime", "Distance", "CarrierDelay",
        "WeatherDelay", "NASDelay", "SecurityDelay", "LateAircraftDelay",
        "Div1Airport", "DivReachedDest"]

# Carrier codes in this extract. Names from the BTS carrier lookup.
CARRIERS = {
    "AA": "American Airlines", "AS": "Alaska Airlines", "B6": "JetBlue Airways",
    "DL": "Delta Air Lines", "F9": "Frontier Airlines", "G4": "Allegiant Air",
    "HA": "Hawaiian Airlines", "MQ": "Envoy Air", "NK": "Spirit Air Lines",
    "OH": "PSA Airlines", "OO": "SkyWest Airlines", "UA": "United Air Lines",
    "WN": "Southwest Airlines", "YX": "Republic Airline",
}

TIME_COLS = {"CRSDepTime": "sched_dep", "DepTime": "actual_dep", "WheelsOff": "wheels_off",
             "WheelsOn": "wheels_on", "CRSArrTime": "sched_arr", "ArrTime": "actual_arr"}


def hhmm_to_time(s: pd.Series) -> pd.Series:
    """BTS local-time HHMM integers -> 'HH:MM:SS'. BTS writes midnight as
    2400, which SQL Server's TIME rejects, so 2400 becomes 00:00."""
    v = pd.to_numeric(s, errors="coerce")
    v = v.where(v != 2400, 0)
    ok = v.notna() & (v >= 0) & (v <= 2359) & ((v % 100) <= 59)
    v = v.where(ok)
    hh = (v // 100).astype("Int64").astype("string").str.zfill(2)
    mm = (v % 100).astype("Int64").astype("string").str.zfill(2)
    return (hh + ":" + mm + ":00").astype("string")


def as_int(s):
    return pd.to_numeric(s, errors="coerce").round().astype("Int64")


def month_files():
    files = sorted(RAW.glob("On_Time_Reporting_Carrier_On_Time_Performance*.csv"))
    files += sorted((RAW / "bts").glob("*.csv")) if (RAW / "bts").exists() else []
    out = []
    for f in files:
        m = re.search(r"(\d{4})_(\d{1,2})\.csv$", f.name)
        if m:
            out.append((int(m.group(1)), int(m.group(2)), f))
    return sorted(out)


def parse_month(path, airports, aliases, code_cache):
    d = pd.read_csv(path, usecols=COLS, low_memory=False, **NO_NA)

    # Resolve each distinct airport code once. IATA first; the ICAO fallback
    # catches renamed airports (BTS still reports Palm Beach as PBI while
    # OurAirports now lists KPBI with IATA DJT).
    codes = pd.Series(sorted((set(d["Origin"]) | set(d["Dest"])) - set(code_cache)))
    if len(codes):
        resolved = resolve_airport(codes, airports, ["iata_code", "local_code", "k_prefix", "alias"], aliases)
        code_cache.update(dict(zip(codes, resolved)))

    out = pd.DataFrame({
        "flight_date": pd.to_datetime(d["FlightDate"]).dt.date,
        "carrier_code": clean_str(d["Reporting_Airline"], upper=True),
        "flight_number": d["Flight_Number_Reporting_Airline"].astype("Int64").astype("string"),
        "tail_number": clean_str(d["Tail_Number"], upper=True),
        "origin_ident": d["Origin"].map(code_cache).astype("string"),
        "dest_ident": d["Dest"].map(code_cache).astype("string"),
        "dep_delay_min": as_int(d["DepDelay"]),
        "taxi_out_min": as_int(d["TaxiOut"]),
        "taxi_in_min": as_int(d["TaxiIn"]),
        "arr_delay_min": as_int(d["ArrDelay"]),
        "air_time_min": as_int(d["AirTime"]),
        "distance_mi": as_int(d["Distance"]),
        "cancelled": as_int(d["Cancelled"]).fillna(0),
        "cancellation_code": clean_str(d["CancellationCode"], upper=True),
        "diverted": as_int(d["Diverted"]).fillna(0),
        "div_airport": clean_str(d["Div1Airport"], upper=True),
        "div_reached_dest": as_int(d["DivReachedDest"]),
        "carrier_delay_min": as_int(d["CarrierDelay"]),
        "weather_delay_min": as_int(d["WeatherDelay"]),
        "nas_delay_min": as_int(d["NASDelay"]),
        "security_delay_min": as_int(d["SecurityDelay"]),
        "late_aircraft_delay_min": as_int(d["LateAircraftDelay"]),
    })
    for src, dst in TIME_COLS.items():
        out[dst] = hhmm_to_time(d[src])
    return out


def build():
    airports = load_staged("dim_airport")
    aliases = load_staged("airport_alias")
    code_cache = {}
    months = month_files()
    assert len(months) == 12, f"expected 12 monthly files, found {len(months)}"
    (STAGED / "bts").mkdir(exist_ok=True)
    total = 0
    for y, m, f in months:
        df = parse_month(f, airports, aliases, code_cache)
        unk = df["origin_ident"].isna().sum() + df["dest_ident"].isna().sum()
        assert unk == 0, f"{y}-{m:02d}: {unk} unresolved airport codes"
        unknown_carriers = set(df["carrier_code"]) - set(CARRIERS)
        assert not unknown_carriers, f"add carrier names for {unknown_carriers}"
        path = STAGED / "bts" / f"{y}_{m:02d}.parquet"
        df.to_parquet(path, index=False)
        total += len(df)
        print(f"  {y}-{m:02d}: {len(df):>8,} flights | cancelled {int(df['cancelled'].sum()):>6,}"
              f" | diverted {int(df['diverted'].sum()):>5,}")
    operators = pd.DataFrame({"iata_code": list(CARRIERS), "name": list(CARRIERS.values())})
    save(operators, "dim_operator")
    print(f"  total: {total:,} flights, {len(code_cache)} airports")


if __name__ == "__main__":
    print("bts")
    build()
