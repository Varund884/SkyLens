"""Transport Canada CADORS -> staged occurrences, categories and aircraft.

Grain: one row per occurrence in cadors_occ. An occurrence can carry several
CICTT categories and involve several aircraft, so those go to cadors_cat and
cadors_air rather than being joined in (which would duplicate occurrences and
inflate every count).
"""
import pandas as pd

from common import (AUTH_TC, CADORS_READ, RAW, ROOT, WINDOW_END, WINDOW_START,
                    clean_str, load_staged, resolve_airport, save, severity_tier)

DAMAGE_RANK = {"Destroyed": 4, "Substantial": 3, "Minor": 2, "No Damage": 1, "Unknown": 0}
COUNTRY = {"Canada": "CA", "the United States of America": "US"}


def read(name, **kw):
    return pd.read_csv(RAW / f"CADORS_{name}.csv", **CADORS_READ, **kw)


def normalize_flight_number(fn: pd.Series) -> pd.Series:
    """Upper-case, drop spaces and punctuation ('NWA 1543' -> 'NWA1543',
    'LSJ445-M' -> 'LSJ445M'). Values with no digits are operator codes only
    ('PAG') and are not flight numbers."""
    out = clean_str(fn, upper=True).str.replace(r"[^A-Z0-9]", "", regex=True).replace("", pd.NA)
    return out.where(out.str.contains(r"\d", na=False))


def normalize_ca_reg(reg: pd.Series) -> pd.Series:
    """CADORS strips the dash from Canadian marks: 'FLPA' -> 'C-FLPA'."""
    r = clean_str(reg, upper=True)
    is_mark = r.str.fullmatch(r"[FG][A-Z]{3}", na=False)
    return r.where(~is_mark, "C-" + r)


def build():
    # ---------- occurrences in the analysis window ----------
    occ = read("Occurrence_Information")
    occ["occ_date"] = pd.to_datetime(occ["occurrencedate"], errors="coerce")
    occ = occ[(occ["occ_date"] >= WINDOW_START) & (occ["occ_date"] <= WINDOW_END)].copy()
    occ["cadorsnumber"] = clean_str(occ["cadorsnumber"], upper=True)
    ids = set(occ["cadorsnumber"])
    print(f"  occurrences in window: {len(occ):,}")

    # ---------- aircraft (many per occurrence) ----------
    air = read("Aircraft_Information")
    air["cadorsnumber"] = clean_str(air["cadorsnumber"], upper=True)
    air = air[air["cadorsnumber"].isin(ids)].copy()
    # Float in this file, int in the event file; cast before any join.
    air["aircraftnumber"] = pd.to_numeric(air["aircraftnumber"], errors="coerce").astype("Int64")
    air = air.sort_values(["cadorsnumber", "aircraftnumber"])
    air["aircraft_seq"] = air.groupby("cadorsnumber").cumcount() + 1

    fn = normalize_flight_number(air["flightnumber"])
    fn_is_nreg = fn.str.fullmatch(r"N\d[A-Z0-9]{0,4}", na=False)
    ca_reg = normalize_ca_reg(air["aircraftregistration"])
    foreign_reg = clean_str(air["foreignaircraftregistration"], upper=True)
    reg = ca_reg.fillna(foreign_reg)
    # 81 N-registrations sit in the flightnumber field in this window.
    reg = reg.fillna(fn.where(fn_is_nreg))
    fn = fn.where(~fn_is_nreg)

    air_out = pd.DataFrame({
        "source_record_id": air["cadorsnumber"],
        "aircraft_seq": air["aircraft_seq"].astype("Int64"),
        "flight_number": fn,
        "registration": reg,
        "operator_name": clean_str(air["operator"]).str.slice(0, 150),
        "phase_of_flight": clean_str(air["phasenamee"]),
        "damage": clean_str(air["damagedescriptione"]),
        "make": clean_str(air["aircraft_make_name_nm"]).str.slice(0, 80),
        "model": clean_str(air["aircraft_model_name_nm"].astype("string")).str.slice(0, 60),
        "year_built": pd.to_numeric(air["aircraftyearbuilt"], errors="coerce").round().astype("Int64"),
    })

    # ---------- event names (occurrence- and aircraft-level) ----------
    oev = read("Occurrence_Event_Information")
    aev = read("Aircraft_Event_Information")
    ev = pd.concat([oev[["cadorsnumber", "event_name_enm"]], aev[["cadorsnumber", "event_name_enm"]]])
    ev["cadorsnumber"] = clean_str(ev["cadorsnumber"], upper=True)
    ev["event_name_enm"] = clean_str(ev["event_name_enm"])
    ev = ev[ev["cadorsnumber"].isin(ids)].dropna().drop_duplicates()
    event_names = ev.groupby("cadorsnumber")["event_name_enm"].agg(lambda s: "; ".join(sorted(s)))

    # ---------- CICTT categories via the hand-built mapping ----------
    cat = read("Occurrence_Category")
    cat["cadorsnumber"] = clean_str(cat["cadorsnumber"], upper=True)
    cat = cat[cat["cadorsnumber"].isin(ids)]
    mapping = pd.read_csv(ROOT / "db" / "map_source_category.csv")
    mapping = mapping[mapping["authority_name"] == AUTH_TC]
    lut = mapping.set_index("source_category_label")["cictt_code"]
    cat = cat.assign(cictt_code=cat["occurrence_category_etxt"].str.strip().map(lut))
    unmapped = cat.loc[cat["cictt_code"].isna(), "occurrence_category_etxt"].unique()
    assert len(unmapped) == 0, f"unmapped CADORS categories: {unmapped}"
    # Both runway-incursion labels map to RI; one occurrence can carry both.
    cat_out = (cat[["cadorsnumber", "cictt_code"]].drop_duplicates()
               .rename(columns={"cadorsnumber": "source_record_id"}))

    # Primary category: the most specific (least frequent in window),
    # skipping OTHR and UNK unless nothing else applies.
    freq = cat_out["cictt_code"].value_counts()
    ranked = cat_out.assign(
        _generic=cat_out["cictt_code"].isin(["OTHR", "UNK"]).astype(int),
        _freq=cat_out["cictt_code"].map(freq),
    ).sort_values(["source_record_id", "_generic", "_freq", "cictt_code"])
    primary = ranked.drop_duplicates("source_record_id").set_index("source_record_id")["cictt_code"]

    # ---------- per-occurrence rollups from aircraft ----------
    first = air_out[air_out["aircraft_seq"] == 1].set_index("source_record_id")
    worst = (air_out.assign(_r=air_out["damage"].map(DAMAGE_RANK).fillna(-1))
             .sort_values("_r", ascending=False)
             .drop_duplicates("source_record_id").set_index("source_record_id")["damage"])
    n_air = air_out.groupby("source_record_id").size()

    # ---------- airport ----------
    airports = load_staged("dim_airport")
    aliases = load_staged("airport_alias")
    airport_ident = resolve_airport(occ["aerodromeid"], airports, ["ident", "alias"], aliases)
    unmatched = occ.loc[occ["aerodromeid"].notna() & airport_ident.isna(), "aerodromeid"]
    if len(unmatched):
        unmatched.value_counts().to_csv(ROOT / "data" / "staged" / "unmatched_aerodromes.csv")

    # Occurrence time is UTC ('1915 Z'); validated 0000-2359 in the window.
    t = clean_str(occ["occurrencetime"]).str.extract(r"^(\d{2})(\d{2})")
    time_utc = (t[0] + ":" + t[1] + ":00").astype("string")

    sid = occ["cadorsnumber"]
    occ_out = pd.DataFrame({
        "authority_name": AUTH_TC,
        "source_record_id": sid,
        "occ_date": occ["occ_date"].dt.date,
        "occurrence_time_utc": time_utc,
        "airport_ident": airport_ident,
        "occurrence_country": occ["country_enm"].map(COUNTRY).astype("string"),
        "occurrence_type": clean_str(occ["occurrencetypedescriptione"]),
        "fatalities": pd.to_numeric(occ["fatalities"], errors="coerce").round().astype("Int64"),
        "injuries": pd.to_numeric(occ["Injuries"], errors="coerce").round().astype("Int64"),
        "phase_of_flight": sid.map(first["phase_of_flight"]).astype("string"),
        "damage": sid.map(worst).astype("string"),
        "flight_number": sid.map(first["flight_number"]).astype("string"),
        "registration": sid.map(first["registration"]).astype("string"),
        "operator_name": sid.map(first["operator_name"]).astype("string"),
        "aircraft_count": sid.map(n_air).fillna(0).astype("Int64"),
        "event_names": sid.map(event_names).astype("string").str.slice(0, 500),
        "primary_cictt": sid.map(primary).astype("string"),
        "source_text": pd.Series(pd.NA, index=occ.index, dtype="string"),
        "findings_l1": pd.Series(pd.NA, index=occ.index, dtype="string"),
        "in_analysis_window": 1,
    })
    occ_out["severity_tier"] = severity_tier(
        occ_out["fatalities"], occ_out["injuries"], None, occ_out["damage"],
        occ_out["occurrence_type"] == "Accident")

    assert not occ_out["source_record_id"].duplicated().any()
    assert set(air_out["source_record_id"]) <= ids and set(cat_out["source_record_id"]) <= ids
    return occ_out.reset_index(drop=True), cat_out.reset_index(drop=True), air_out.reset_index(drop=True)


if __name__ == "__main__":
    print("cadors")
    occ, cat, air = build()
    print(f"  airport matched: {occ['airport_ident'].notna().sum():,} "
          f"| en-route/no aerodrome: {occ['airport_ident'].isna().sum():,}")
    print(f"  categories: {len(cat):,} rows | occurrences with >1: "
          f"{(cat.groupby('source_record_id').size() > 1).sum():,}")
    print(f"  aircraft: {len(air):,} rows | occurrences with none: {(occ['aircraft_count'] == 0).sum():,}")
    print(f"  severity: {occ['severity_tier'].value_counts().to_dict()}")
    print(f"  country: {occ['occurrence_country'].value_counts(dropna=False).to_dict()}")
    save(occ, "cadors_occ")
    save(cat, "cadors_cat")
    save(air, "cadors_air")
