"""Shared constants and helpers for the ETL parsers.

Parsers read raw files and write staged parquet under data/staged/ using
natural identifiers (ICAO ident, CICTT code, authority name). They never touch
the database. etl/load.py resolves those identifiers to surrogate keys.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
STAGED = ROOT / "data" / "staged"
STAGED.mkdir(parents=True, exist_ok=True)

# Analysis window. Aligned to the 12 months of BTS data, which supplies the
# movement counts every rate is divided by.
WINDOW_START = pd.Timestamp("2025-07-01")
WINDOW_END = pd.Timestamp("2026-06-30")

AUTH_TC = "Transport Canada"
AUTH_NTSB = "NTSB"
AUTH_BTS = "BTS"

# BTS reports flights to US territories as domestic, and OurAirports files
# those airports under their own country codes.
AIRPORT_COUNTRIES = ["US", "CA", "PR", "VI", "GU", "AS", "MP"]

# CADORS CSVs are UTF-8 and contain 5 rows (of 1.9M) with backslash-escaped
# quotes that do not parse; those are skipped.
CADORS_READ = dict(encoding="utf-8", low_memory=False, on_bad_lines="skip")

# pandas reads the literal text "NA" as missing by default, which would blank
# real airport and code values. Only empty cells count as missing.
NO_NA = dict(keep_default_na=False, na_values=[""])


def clean_str(s: pd.Series, upper: bool = False) -> pd.Series:
    """Strip whitespace and turn empty strings into NA."""
    out = s.astype("string").str.strip()
    if upper:
        out = out.str.upper()
    return out.replace("", pd.NA)


def severity_tier(fatalities, injuries, serious, damage, is_accident) -> pd.Series:
    """Coarse severity used for UI pills. Not a risk rating.

    high   - any fatality, serious injury, or destroyed aircraft
    medium - an accident, substantial damage, or any injury
    low    - everything else

    CADORS reports only a combined injury count, so pass serious=None there.
    """
    idx = fatalities.index
    num = lambda x: pd.to_numeric(x, errors="coerce").fillna(0) if x is not None else pd.Series(0, index=idx)
    fat, inj, ser = num(fatalities), num(injuries), num(serious)
    dmg = damage.astype("string").fillna("")
    acc = is_accident.astype("boolean").fillna(False).astype(bool)
    tier = pd.Series("low", index=idx, dtype="string")
    tier[acc | dmg.str.contains("Substantial") | (inj > 0)] = "medium"
    tier[(fat > 0) | (ser > 0) | dmg.str.contains("Destroyed")] = "high"
    return tier


def resolve_airport(codes: pd.Series, airports: pd.DataFrame, chain, aliases=None) -> pd.Series:
    """Map external airport codes to our canonical ICAO ident.

    chain lists lookups to try in order: "ident", "alias", "local_code",
    "k_prefix", "iata_code". "alias" needs the airport_alias frame. Open airports win over closed ones when a code is shared
    (OurAirports has 81 duplicated FAA local codes).
    """
    ap = airports.assign(_closed=airports["is_closed"].astype(int)).sort_values("_closed")
    c = clean_str(codes, upper=True)
    out = pd.Series(pd.NA, index=codes.index, dtype="string")
    for step in chain:
        todo = out.isna() & c.notna()
        if not todo.any():
            break
        if step == "alias":
            lut = aliases.set_index("alias")["ident"]
            out[todo] = c[todo].map(lut).astype("string")
            continue
        if step == "k_prefix":
            keys, col = "K" + c[todo], "ident"
        else:
            keys, col = c[todo], step
        lut = ap.dropna(subset=[col]).drop_duplicates(col).set_index(col, drop=False)["ident"]
        out[todo] = keys.map(lut).astype("string")
    return out


def save(df: pd.DataFrame, name: str) -> Path:
    path = STAGED / f"{name}.parquet"
    df.to_parquet(path, index=False)
    print(f"  wrote {path.relative_to(ROOT)}  ({len(df):,} rows)")
    return path


def load_staged(name: str) -> pd.DataFrame:
    return pd.read_parquet(STAGED / f"{name}.parquet")
