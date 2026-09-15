"""
Assess viability of flight-level matching in CADORS.

CADORS publishes flightnumber as a structured column, so no text extraction
is required. This script measures coverage and format consistency.
"""
import pandas as pd
import warnings

warnings.simplefilter("ignore")
READ = dict(encoding="utf-8", low_memory=False, on_bad_lines="skip")

air = pd.read_csv("data/raw/CADORS_Aircraft_Information.csv", **READ)

total = len(air)
fn = air.flightnumber.dropna().astype(str).str.strip().str.replace(" ", "", regex=False)

callsign = fn.str.match(r"^[A-Z]{2,3}\d{1,4}[A-Z]?$")
nreg = fn.str.match(r"^N\d")

print(f"aircraft rows        : {total:,}")
print(f"flightnumber present : {len(fn):,} ({len(fn)/total:.1%})")
print(f"  ICAO callsign      : {callsign.sum():,} ({callsign.mean():.1%})")
print(f"  N-registration     : {nreg.sum():,}")
print(f"  other              : {(~callsign & ~nreg).sum():,}")
print()
print("top carrier prefixes:")
print(fn[callsign].str.extract(r"^([A-Z]{2,3})")[0].value_counts().head(20).to_string())
print()

reg = air.aircraftregistration.dropna().astype(str)
print(f"CA registrations     : {len(reg):,}")
print(f"  4 chars            : {(reg.str.len() == 4).mean():.1%}")
print(f"  start with F or G  : {reg.str[0].isin(['F','G']).mean():.1%}")
print(f"  contain a dash     : {reg.str.contains('-').mean():.1%}  (normalize with 'C-' prefix)")
print(f"foreign registrations: {air.foreignaircraftregistration.notna().sum():,}")
