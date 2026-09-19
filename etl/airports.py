"""OurAirports -> staged dim_airport and airport_alias.

When an airport closes or changes code, OurAirports renames its ident and
keeps the old code only in the free-text keywords field. Toronto Buttonville
was CYKZ and is now CA-1108; Barrie was CNB9 and is now CYLS. CADORS still
reports the old codes (CYKZ and CYXD alone carry 2,465 records), so closed
airports are kept and flagged, and former codes are harvested from keywords
into an alias table used when resolving source airport codes.
"""
import re
import pandas as pd

from common import AIRPORT_COUNTRIES, NO_NA, RAW, clean_str, save


def build() -> pd.DataFrame:
    ap = pd.read_csv(RAW / "airports.csv", low_memory=False, **NO_NA)
    ap = ap[ap["iso_country"].isin(AIRPORT_COUNTRIES)].copy()

    rw = pd.read_csv(RAW / "runways.csv", low_memory=False, **NO_NA)
    rw = rw[pd.to_numeric(rw["closed"], errors="coerce").fillna(0) == 0]
    rw["length_ft"] = pd.to_numeric(rw["length_ft"], errors="coerce")
    rstats = rw.groupby("airport_ident").agg(
        runway_count=("length_ft", "size"),
        longest_runway_ft=("length_ft", "max"),
    )

    out = pd.DataFrame({
        "ident": clean_str(ap["ident"], upper=True),
        "iata_code": clean_str(ap["iata_code"], upper=True),
        "local_code": clean_str(ap["local_code"], upper=True),
        "name": clean_str(ap["name"]),
        "airport_type": clean_str(ap["type"]),
        "latitude": pd.to_numeric(ap["latitude_deg"], errors="coerce"),
        "longitude": pd.to_numeric(ap["longitude_deg"], errors="coerce"),
        "elevation_ft": pd.to_numeric(ap["elevation_ft"], errors="coerce").round().astype("Int64"),
        "iso_country": clean_str(ap["iso_country"]),
        "iso_region": clean_str(ap["iso_region"]),
        "municipality": clean_str(ap["municipality"]),
        "is_closed": (ap["type"] == "closed").astype(int),
    })
    out = out.join(rstats, on="ident")
    out["runway_count"] = out["runway_count"].fillna(0).astype("Int64")
    out["longest_runway_ft"] = out["longest_runway_ft"].round().astype("Int64")

    # Column widths in dim_airport
    for col, width in [("ident", 10), ("iata_code", 5), ("local_code", 10),
                       ("name", 200), ("airport_type", 30), ("iso_region", 10),
                       ("municipality", 100)]:
        too_long = out[col].str.len() > width
        assert not too_long.any(), f"{col} exceeds {width}: {out.loc[too_long, col].head().tolist()}"

    assert out["ident"].notna().all() and not out["ident"].duplicated().any(), "ident must be unique"
    return out, build_aliases(ap, set(out["ident"]))


def build_aliases(ap: pd.DataFrame, idents: set) -> pd.DataFrame:
    """Former 4-character ICAO-style codes listed in keywords -> current ident."""
    kw = ap[["ident", "keywords"]].dropna()
    kw = kw.assign(token=kw["keywords"].str.split(",")).explode("token")
    kw["token"] = kw["token"].str.strip().str.upper()
    kw = kw[kw["token"].str.fullmatch(r"[CKPT][A-Z0-9]{3}", na=False)]
    kw = kw[kw["token"] != kw["ident"].str.upper()]
    kw = kw[~kw["token"].isin(idents)]          # never shadow a live ident
    kw = kw.drop_duplicates(["token", "ident"])
    ambiguous = kw["token"].duplicated(keep=False)
    kw = kw[~ambiguous]                          # one alias -> one airport only
    return kw.rename(columns={"token": "alias"})[["alias", "ident"]].reset_index(drop=True)


if __name__ == "__main__":
    print("airports")
    df, aliases = build()
    print(df["airport_type"].value_counts().to_string())
    print(f"  countries: {df['iso_country'].value_counts().to_dict()}")
    print(f"  closed: {df['is_closed'].sum():,}   with runways: {(df['runway_count'] > 0).sum():,}")
    print(f"  former-code aliases: {len(aliases):,}")
    save(df, "dim_airport")
    save(aliases, "airport_alias")
