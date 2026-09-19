"""NTSB CAROL exports -> staged occurrences and aircraft.

Two inputs with different jobs:
  ntsb_12mo.csv   (2025-07..2026-06) counted in rates, in_analysis_window=1.
                  Restricted to US events: the NTSB also assists on foreign
                  investigations (474 of 1,700 aviation rows), which must not
                  count toward US airport rates.
  ntsb_corpus.csv (2014..2024) text for embeddings and the classifier,
                  in_analysis_window=0, never counted.

Both are filtered to Mode == 'Aviation'; CAROL exports include marine, rail,
highway and pipeline investigations.
"""
import re

import pandas as pd

from common import AUTH_NTSB, NO_NA, RAW, clean_str, load_staged, resolve_airport, save, severity_tier

EVENT_TYPE = {"ACC": "Accident", "INC": "Incident", "OCC": "Occurrence"}
COUNTRY = {"United States": "US", "Canada": "CA"}

# Findings separates entries with ', ' but entries can contain commas
# themselves ('Intake anti-ice, deice'). Split only where the next entry
# starts with a top-level class.
L1_CLASSES = ["Personnel issues", "Aircraft", "Environmental issues",
              "Organizational issues", "Not determined"]
FINDING_SPLIT = re.compile(r", (?=(?:%s) - )" % "|".join(map(re.escape, L1_CLASSES)))


def findings_l1(text: pd.Series) -> pd.Series:
    def one(s):
        if pd.isna(s):
            return pd.NA
        classes = {part.split(" - ")[0].strip() for part in FINDING_SPLIT.split(s)}
        return "; ".join(sorted(c for c in classes if c in L1_CLASSES)) or pd.NA
    return text.map(one).astype("string")


def split_aligned(values: pd.Series, n_parts: pd.Series) -> pd.Series:
    """Split a comma-joined multi-aircraft field only when its part count
    matches the number of registrations; otherwise keep it whole on aircraft 1.
    Operator names contain commas ('NetJets Aviation, Inc')."""
    def one(v, n):
        if pd.isna(v):
            return [pd.NA] * n
        parts = [p.strip() for p in str(v).split(", ")]
        return parts if len(parts) == n else [str(v).strip()] + [pd.NA] * (n - 1)
    return pd.Series([one(v, n) for v, n in zip(values, n_parts)], index=values.index)


def parse(path, in_window: int, us_only: bool, airports, aliases):
    d = pd.read_csv(path, low_memory=False, **NO_NA)
    d = d[d["Mode"] == "Aviation"].copy()
    if us_only:
        d = d[d["Country"] == "United States"].copy()
    d["NtsbNo"] = clean_str(d["NtsbNo"], upper=True)
    assert not d["NtsbNo"].duplicated().any()

    ts = pd.to_datetime(d["EventDate"], errors="coerce", utc=True)
    hhmm = ts.dt.strftime("%H:%M")
    # Date-only events are exported at local midnight Eastern (04:00/05:00Z);
    # those are not real times of day.
    time_utc = ts.dt.strftime("%H:%M:%S").astype("string").where(~hhmm.isin(["04:00", "05:00"]))

    is_us = d["Country"] == "United States"
    airport_ident = pd.Series(pd.NA, index=d.index, dtype="string")
    airport_ident[is_us] = resolve_airport(
        d.loc[is_us, "AirportID"], airports, ["ident", "local_code", "k_prefix", "iata_code"], aliases)

    fat = pd.to_numeric(d["FatalInjuryCount"], errors="coerce")
    ser = pd.to_numeric(d["SeriousInjuryCount"], errors="coerce")
    minor = pd.to_numeric(d["MinorInjuryCount"], errors="coerce")
    damage_first = clean_str(d["AirCraftDamage"]).str.split(", ").str[0]

    # ---------- aircraft (N# may list several, comma-separated) ----------
    regs = clean_str(d["N#"], upper=True).str.split(", ")
    n = regs.map(lambda x: len(x) if isinstance(x, list) else 1)
    cols = {c: split_aligned(d[c], n) for c in ["Make", "Model", "Operator", "AirCraftDamage"]}
    rows = []
    for i, sid in d["NtsbNo"].items():
        rlist = regs[i] if isinstance(regs[i], list) else [pd.NA]
        for k in range(n[i]):
            rows.append({
                "source_record_id": sid,
                "aircraft_seq": k + 1,
                "flight_number": pd.NA,
                "registration": rlist[k] if k < len(rlist) else pd.NA,
                "operator_name": cols["Operator"][i][k],
                "phase_of_flight": pd.NA,
                "damage": cols["AirCraftDamage"][i][k],
                "make": cols["Make"][i][k],
                "model": cols["Model"][i][k],
                "year_built": pd.NA,
            })
    air = pd.DataFrame(rows)
    for c in ["registration", "operator_name", "damage", "make", "model", "flight_number", "phase_of_flight"]:
        air[c] = clean_str(air[c])
    # N# sometimes holds prose ('UNREGISTERED ULTRALIGHT') rather than a mark.
    air["registration"] = air["registration"].where(
        air["registration"].str.fullmatch(r"[A-Z0-9-]{2,10}", na=False))
    air["operator_name"] = air["operator_name"].str.slice(0, 150)
    air["make"] = air["make"].str.slice(0, 80)
    air["model"] = air["model"].str.slice(0, 60)
    air["aircraft_seq"] = air["aircraft_seq"].astype("Int64")
    air["year_built"] = pd.array([pd.NA] * len(air), dtype="Int64")

    occ = pd.DataFrame({
        "authority_name": AUTH_NTSB,
        "source_record_id": d["NtsbNo"],
        "occ_date": ts.dt.date,
        "occurrence_time_utc": time_utc,
        "airport_ident": airport_ident,
        "occurrence_country": d["Country"].map(COUNTRY).astype("string"),
        "occurrence_type": d["EventType"].map(EVENT_TYPE).astype("string"),
        "fatalities": fat.round().astype("Int64"),
        "injuries": (ser.fillna(0) + minor.fillna(0)).where(ser.notna() | minor.notna()).round().astype("Int64"),
        "phase_of_flight": pd.Series(pd.NA, index=d.index, dtype="string"),
        "damage": damage_first,
        "flight_number": pd.Series(pd.NA, index=d.index, dtype="string"),
        "registration": pd.Series(pd.NA, index=d.index, dtype="string"),  # from aircraft 1, below
        "operator_name": pd.Series(pd.NA, index=d.index, dtype="string"),
        "aircraft_count": n.astype("Int64"),
        "event_names": pd.Series(pd.NA, index=d.index, dtype="string"),
        "primary_cictt": pd.Series(pd.NA, index=d.index, dtype="string"),  # set by the classifier
        "source_text": clean_str(d["ProbableCause"]),
        "findings": clean_str(d["Findings"]),
        "findings_l1": findings_l1(d["Findings"]),
        "in_analysis_window": in_window,
    })
    first = air[air["aircraft_seq"] == 1].set_index("source_record_id")
    occ["registration"] = occ["source_record_id"].map(first["registration"]).astype("string")
    occ["operator_name"] = occ["source_record_id"].map(first["operator_name"]).astype("string")
    occ["severity_tier"] = severity_tier(fat, ser.fillna(0) + minor.fillna(0), ser,
                                         clean_str(d["AirCraftDamage"]), d["EventType"] == "ACC")
    return occ.reset_index(drop=True), air.reset_index(drop=True)


def build():
    airports = load_staged("dim_airport")
    aliases = load_staged("airport_alias")
    o1, a1 = parse(RAW / "ntsb" / "ntsb_12mo.csv", 1, True, airports, aliases)
    o2, a2 = parse(RAW / "ntsb" / "ntsb_corpus.csv", 0, False, airports, aliases)
    overlap = set(o1["source_record_id"]) & set(o2["source_record_id"])
    assert not overlap, f"records in both files: {list(overlap)[:5]}"
    return pd.concat([o1, o2], ignore_index=True), pd.concat([a1, a2], ignore_index=True)


if __name__ == "__main__":
    print("ntsb")
    occ, air = build()
    for w, g in occ.groupby("in_analysis_window"):
        label = "rate file (US, in window)" if w == 1 else "text corpus"
        print(f"  {label}: {len(g):,} | airport matched {g['airport_ident'].notna().sum():,}"
              f" | with ProbableCause {g['source_text'].notna().sum():,}"
              f" | with Findings {g['findings'].notna().sum():,}")
    print(f"  findings_l1 classes: {sorted(set('; '.join(occ['findings_l1'].dropna()).split('; ')))}")
    print(f"  aircraft rows: {len(air):,} | multi-aircraft events: {(occ['aircraft_count'] > 1).sum():,}")
    print(f"  severity: {occ['severity_tier'].value_counts().to_dict()}")
    save(occ, "ntsb_occ")
    save(air, "ntsb_air")
