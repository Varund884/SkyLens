"""Statistics Canada table 23-10-0296 -> staged monthly airport movements.

"Aircraft movements, by class of operation, airports with NAV CANADA services
and other selected airports, monthly." Total itinerant + local movements for
126 named airports. The companion table 23-10-0303 has only province totals.

The SDMX download is a series of monthly releases, each re-sending recent
months with revisions; the latest release wins for every airport-month.
Months published as not available ('..') are left out, never written as 0.

Airports are identified by name, so db/map_statcan_airport.csv maps each to
an ICAO ident (113 automatic matches, 13 corrected by hand, all reviewed).

Grain: StatCan is monthly. Rows are stored on the first day of each month,
so sums over the analysis window are correct; do not read them as daily.
"""
import re
import xml.etree.ElementTree as ET
import zipfile

import pandas as pd

from common import RAW, ROOT, WINDOW_END, WINDOW_START, save

ZIP = RAW / "movements" / "23100296-SDMX.zip"
TOTAL_CLASS = "1"           # Total, itinerant and local movements
STR = "{http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure}"


def read_releases(z: zipfile.ZipFile) -> pd.DataFrame:
    rows = []
    for name in z.namelist():
        if "Structure" in name:
            continue
        raw = z.read(name).decode("utf-8-sig")
        prepared = re.search(r"<message:Prepared>([^<]+)", raw).group(1)
        for s in ET.fromstring(raw).iter("Series"):
            if s.get("Class_of_operation") != TOTAL_CLASS:
                continue
            for o in s.findall("Obs"):
                rows.append((prepared, s.get("Airports"), o.get("TIME_PERIOD"), o.get("OBS_VALUE")))
    d = pd.DataFrame(rows, columns=["prepared", "sc_code", "period", "value"])
    # Latest release wins: later files carry revised values.
    return d.sort_values("prepared").drop_duplicates(["sc_code", "period"], keep="last")


def build() -> pd.DataFrame:
    z = zipfile.ZipFile(ZIP)
    assert any("Structure" in n for n in z.namelist()), "not an SDMX download"
    d = read_releases(z)

    mapping = pd.read_csv(ROOT / "db" / "map_statcan_airport.csv", dtype={"sc_code": str})
    d = d[~d["sc_code"].str.startswith("1000")]          # national/NAV CANADA totals
    unmapped = set(d["sc_code"]) - set(mapping["sc_code"])
    assert not unmapped, f"StatCan airports missing from db/map_statcan_airport.csv: {unmapped}"

    d["month"] = pd.to_datetime(d["period"] + "-01")
    d = d[(d["month"] >= WINDOW_START) & (d["month"] <= WINDOW_END)]
    d["movement_count"] = pd.to_numeric(d["value"], errors="coerce").round().astype("Int64")
    d = d[d["movement_count"].notna()]

    out = pd.DataFrame({
        "airport_ident": d["sc_code"].map(mapping.set_index("sc_code")["ident"]).astype("string"),
        "movement_date": d["month"].dt.date,
        "movement_count": d["movement_count"],
        "is_estimated": 0,
        "source": "statcan",
    })
    assert not out.duplicated(["airport_ident", "movement_date"]).any()
    return out.reset_index(drop=True)


if __name__ == "__main__":
    print("statcan")
    m = build()
    per = m.groupby("airport_ident")["movement_count"].agg(["sum", "size"])
    print(f"  airports: {len(per)} | airport-months: {len(m):,} | movements: {int(m['movement_count'].sum()):,}")
    print(f"  airports with <12 months: {per[per['size'] < 12]['size'].to_dict()}")
    print(f"  busiest: {per['sum'].sort_values(ascending=False).head(5).to_dict()}")
    save(m, "movements_statcan")
