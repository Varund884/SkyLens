"""FAA ATADS tower counts -> staged daily airport movements for US airports.

ATADS (Air Traffic Activity Data System) is the FAA's official count of
operations at airports with an FAA or contract control tower: air carrier,
air taxi, general aviation and military, itinerant and local. One takeoff or
one landing is one operation, the same unit as BTS departures + arrivals and
Statistics Canada movements.

Download: aspm.faa.gov/opsnet/sys/Airport.asp, Standard Report, date Range
07/01/2025 to 06/30/2026, grouped by Date and Airport, exported to Excel.
The "Excel" file is really an HTML table (latin-1), so it is parsed with
regular expressions; each data row has 15 cells and the Facility cell is the
FAA location identifier (LOCID), matched to our ident through local_code.

Known limits (see docs/data-notes.md):
  - only towered airports (528 in the window); non-towered airports have none
  - only operations while the tower is open; part-time towers under-count
  - days a tower did not report have no row; they are never written as 0
"""
import re

import pandas as pd

from common import RAW, WINDOW_END, WINDOW_START, load_staged, resolve_airport, save

FILE = RAW / "movements" / "faa_atads_daily.xls"
ROW = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
DATE = re.compile(r"\d\d/\d\d/\d{4}$")
FOOTER_TOTAL = re.compile(r"Total:.*?([\d,]+)</td>\s*</tr>\s*</table>", re.S)


def read_rows(html: str) -> pd.DataFrame:
    body = html.split("</thead>", 1)[1]
    rows = [CELL.findall(r) for r in ROW.findall(body)]
    # Keep data rows only: sub-total rows have 10 cells and no date in the first one.
    data = [r for r in rows if len(r) == 15 and DATE.match(r[0].strip())]
    return pd.DataFrame({
        "date": [r[0].strip() for r in data],
        "state": [r[4].strip() for r in data],
        "locid": [r[5].strip() for r in data],
        "total": [r[14].strip().replace(",", "") for r in data],
    })


def build() -> pd.DataFrame:
    html = FILE.read_text(encoding="latin-1")
    rng = re.search(r"YYYYMMDD>=(\d{8}) AND YYYYMMDD<=(\d{8})", html)
    assert rng, "report query not found; was the file exported with a date Range?"
    assert "GROUP BY YYYYMMDD" in html, "report must be grouped by Date (daily rows)"

    d = read_rows(html)
    d["movement_date"] = pd.to_datetime(d["date"], format="%m/%d/%Y")
    d["movement_count"] = pd.to_numeric(d["total"]).astype("Int64")

    # The report's own grand total must equal the sum of what we parsed.
    footer = int(FOOTER_TOTAL.search(html).group(1).replace(",", ""))
    assert int(d["movement_count"].sum()) == footer, "parsed rows do not add up to the report total"

    d = d[(d["movement_date"] >= WINDOW_START) & (d["movement_date"] <= WINDOW_END)]

    airports, aliases = load_staged("dim_airport"), load_staged("airport_alias")
    fac = pd.Series(d["locid"].unique())
    ident = resolve_airport(fac, airports, ["local_code", "k_prefix", "iata_code", "alias"], aliases)
    unmatched = fac[ident.isna()].tolist()
    assert not unmatched, f"FAA LOCIDs not matched to an airport: {unmatched}"
    lut = pd.Series(ident.values, index=fac.values)

    out = pd.DataFrame({
        "airport_ident": d["locid"].map(lut).astype("string"),
        "movement_date": d["movement_date"].dt.date,
        "movement_count": d["movement_count"],
        "is_estimated": 0,
        "source": "faa",
    })
    assert not out.duplicated(["airport_ident", "movement_date"]).any(), "two LOCIDs on one airport"
    return out.reset_index(drop=True)


if __name__ == "__main__":
    print("faa")
    m = build()
    per = m.groupby("airport_ident")["movement_count"].agg(["sum", "size"])
    print(f"  airports: {len(per)} | airport-days: {len(m):,} | operations: {int(m['movement_count'].sum()):,}")
    print(f"  airports reporting fewer than 365 days: {int((per['size'] < 365).sum())}")
    print(f"  busiest: {per['sum'].sort_values(ascending=False).head(5).to_dict()}")
    save(m, "movements_faa")
