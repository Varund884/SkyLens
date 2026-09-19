"""Airport movement counts -> staged fact_airport_movements.

The denominator for every rate. Current source is BTS, which counts only
US domestic flights by reporting carriers:
  - a departure is a flight that was not cancelled
  - an arrival is a flight that was neither cancelled nor diverted away
    (diverted flights that still reached their destination count)

Canadian airports come from Statistics Canada table 23-10-0296 (etl/statcan.py):
official total itinerant + local movements for 121 airports, stored monthly on
the first of each month. Those airports cover 96% of aircraft-involved CADORS
occurrences at an airport. BTS and StatCan never overlap (US vs Canada).

US towered airports come from FAA ATADS (etl/faa.py): all traffic, airline
plus general aviation, cargo and military, daily. Where an airport has both
FAA and BTS counts, FAA wins for the whole airport (BTS is airline-only and
would inflate rates). Each airport keeps exactly one source so a sum over the
window never mixes them. BTS remains the source for the 73 airline airports
without an FAA tower, where it under-counts non-airline traffic.
"""
import pandas as pd

from common import STAGED, load_staged, save


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


def combined() -> pd.DataFrame:
    bts = from_bts()
    parts = []
    if (STAGED / "movements_faa.parquet").exists():
        faa = load_staged("movements_faa")
        replaced = bts["airport_ident"].isin(set(faa["airport_ident"]))
        print(f"  faa replaces bts at {bts.loc[replaced, 'airport_ident'].nunique()} airports")
        bts = bts[~replaced]
        parts.append(faa)
    else:
        print("  note: no faa movements staged; run  python etl/faa.py  for US all-traffic rates")
    parts.insert(0, bts)
    if (STAGED / "movements_statcan.parquet").exists():
        parts.append(load_staged("movements_statcan"))
    else:
        print("  note: no statcan movements staged; run  python etl/statcan.py  for Canadian rates")
    m = pd.concat(parts, ignore_index=True)
    overlap = m.groupby("airport_ident")["source"].nunique()
    assert (overlap == 1).all(), f"airports with two sources: {overlap[overlap > 1].index.tolist()}"
    return m


if __name__ == "__main__":
    print("movements")
    m = combined()
    assert not m.duplicated(["airport_ident", "movement_date"]).any()
    per_airport = m.groupby("airport_ident")["movement_count"].sum().sort_values(ascending=False)
    print(f"  airport-days: {len(m):,} | airports: {m['airport_ident'].nunique()} "
          f"| total movements: {int(m['movement_count'].sum()):,}")
    print(f"  by source: {m.groupby('source')['airport_ident'].nunique().to_dict()} airports")
    print(f"  busiest: {per_airport.head(5).to_dict()}")
    save(m, "movements")
