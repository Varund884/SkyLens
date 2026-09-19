"""Airport movement counts -> staged fact_airport_movements.

The denominator for every rate. Current source is BTS, which counts only
US domestic flights by reporting carriers:
  - a departure is a flight that was not cancelled
  - an arrival is a flight that was neither cancelled nor diverted away
    (diverted flights that still reached their destination count)

Known limitation, measured on the 2025-07..2026-06 data: BTS covers 358
airports. 85% of NTSB rate-window occurrences with an airport, and all CADORS
occurrences, are at airports with no BTS flights. Official all-traffic counts
(Statistics Canada, FAA ATADS) are needed for those; each row carries a
`source` so they can be added without changing BTS rows.
"""
import pandas as pd

from common import STAGED, save


def from_bts() -> pd.DataFrame:
    parts = []
    for f in sorted((STAGED / "bts").glob("*.parquet")):
        d = pd.read_parquet(f, columns=["flight_date", "origin_ident", "dest_ident",
                                        "cancelled", "diverted", "div_reached_dest"])
        flew = d["cancelled"] == 0
        arrived = flew & ((d["diverted"] == 0) | (d["div_reached_dest"].fillna(0) == 1))
        dep = d[flew].groupby(["origin_ident", "flight_date"]).size()
        arr = d[arrived].groupby(["dest_ident", "flight_date"]).size()
        dep.index.names = arr.index.names = ["airport_ident", "flight_date"]
        parts.append(dep.add(arr, fill_value=0))
    m = pd.concat(parts).groupby(level=[0, 1]).sum().rename("movement_count").reset_index()
    m["movement_count"] = m["movement_count"].astype("Int64")
    m["is_estimated"] = 0
    m["source"] = "bts"
    return m.rename(columns={"flight_date": "movement_date"})


if __name__ == "__main__":
    print("movements")
    m = from_bts()
    assert not m.duplicated(["airport_ident", "movement_date"]).any()
    per_airport = m.groupby("airport_ident")["movement_count"].sum().sort_values(ascending=False)
    print(f"  airport-days: {len(m):,} | airports: {m['airport_ident'].nunique()} "
          f"| total movements: {int(m['movement_count'].sum()):,}")
    print(f"  busiest: {per_airport.head(5).to_dict()}")
    save(m, "movements")
