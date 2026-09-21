"""Build the hand-labelling sheet for the NTSB -> CICTT classifier.

Samples 300 NTSB corpus occurrences (2022-07 to 2024, all already embedded),
stratified by their NTSB findings level-1 combination so rare combinations are
represented, and writes data/labelling_sheet.xlsx with an empty cictt_code
column (dropdown) for a person to fill in. It never suggests a label.

The filled-in copy is saved by the labeller as data/labelled_seed.xlsx and is
the only source of training labels.

    python ai/make_label_sheet.py              # 300 rows (for hand labelling)
    python ai/make_label_sheet.py --rows 1500  # larger sheet for LLM drafting
"""
import argparse
import re

import pandas as pd
from openpyxl import Workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from aicommon import ROOT

N = 300
MIN_PER_STRATUM = 3
SEED = 42
OUT = ROOT / "data" / "labelling_sheet.xlsx"
SPLIT = re.compile(r", (?=(?:Personnel issues|Aircraft|Environmental issues|Organizational issues|Not determined) - )")

# CICTT v4.8 occurrence categories (short definitions for the labeller).
CODES = [
    ("ARC", "Abnormal runway contact", "Hard or bounced landing, tail strike, wingtip/nacelle strike, gear-up landing, landing with gear not fully extended."),
    ("AMAN", "Abrupt maneuver", "Intentional abrupt manoeuvring by the crew."),
    ("ADRM", "Aerodrome", "Aerodrome design, condition or services contributed."),
    ("ATM", "ATM/CNS", "Air traffic management or communication/navigation/surveillance service issue."),
    ("BIRD", "Bird", "Collision or near-collision with birds."),
    ("CABIN", "Cabin safety events", "Events in the cabin (turbulence injuries to cabin crew are TURB)."),
    ("CFIT", "Controlled flight into or toward terrain", "In-flight collision with terrain, water or obstacle with no loss of control."),
    ("CTOL", "Collision with obstacles during takeoff and landing", "Airborne collision with an obstacle during takeoff or landing phases."),
    ("EVAC", "Evacuation", "Injury during an evacuation, or unnecessary evacuation."),
    ("EXTL", "External load related", "Occurrences involving external/sling loads."),
    ("F-NI", "Fire/smoke non-impact", "Fire or smoke in or on the aircraft, not caused by impact."),
    ("F-POST", "Fire/smoke post-impact", "Fire or smoke resulting from impact."),
    ("FUEL", "Fuel related", "Power loss from fuel exhaustion, starvation/mismanagement, contamination or wrong fuel; includes carburettor/induction icing."),
    ("GCOL", "Ground collision", "Collision while taxiing, excluding runway incursions."),
    ("GTOW", "Glider towing related", "Events during glider towing or launch."),
    ("ICE", "Icing", "Ice, snow or frost on aircraft surfaces affecting control or performance (not carburettor icing)."),
    ("LALT", "Low altitude operations", "Collision or near-collision while intentionally flying close to the surface (not takeoff/landing), e.g. aerial application, wires."),
    ("LOC-G", "Loss of control - ground", "Loss of control while on the ground that does not leave the runway (if it leaves the runway, RE)."),
    ("LOC-I", "Loss of control - inflight", "Loss of aircraft control while airborne, e.g. stall, spin, spatial disorientation."),
    ("LOLI", "Loss of lifting conditions en route", "Glider/balloon unable to stay aloft for lack of lift."),
    ("MAC", "Airprox/TCAS/loss of separation/midair", "Midair collisions, near-collisions, loss of separation."),
    ("MED", "Medical", "Illness or incapacitation of a person on board."),
    ("NAV", "Navigation errors", "Incorrect navigation, e.g. wrong runway, airspace infringement."),
    ("RAMP", "Ground handling", "Ground servicing, loading, towing, pushback."),
    ("RE", "Runway excursion", "Aircraft veers off the side of or overruns the runway during takeoff or landing."),
    ("RI", "Runway incursion", "Incorrect presence of an aircraft, vehicle or person on a runway."),
    ("SCF-NP", "System/component failure - non-powerplant", "Failure of a system or component other than the engine (gear, flight controls, structure, ...)."),
    ("SCF-PP", "System/component failure - powerplant", "Engine or propeller failure or malfunction not caused by fuel."),
    ("SEC", "Security related", "Unlawful interference, sabotage, security threats."),
    ("TURB", "Turbulence encounter", "Turbulence, including clear-air and wake turbulence."),
    ("UIMC", "Unintended flight in IMC", "Continued VFR flight into instrument conditions."),
    ("USOS", "Undershoot/overshoot", "Touchdown before the runway threshold or beyond its end, off the runway surface."),
    ("WILD", "Wildlife", "Collision with non-bird wildlife."),
    ("WSTRW", "Wind shear or thunderstorm", "Wind shear or thunderstorm encounter."),
    ("OTHR", "Other", "Known event that fits no category above."),
    ("UNK", "Unknown or undetermined", "Not enough information to choose a category."),
]


def sample(N: int = N) -> pd.DataFrame:
    occ = pd.read_parquet(ROOT / "data" / "staged" / "ntsb_occ.parquet")
    air = pd.read_parquet(ROOT / "data" / "staged" / "ntsb_air.parquet")
    c = occ[(occ["in_analysis_window"] == 0) & occ["source_text"].notna()
            & (pd.to_datetime(occ["occ_date"]) > "2022-06-30")].copy()
    c["stratum"] = c["findings_l1"].fillna("None")

    sizes = c["stratum"].value_counts()
    alloc = (sizes / sizes.sum() * N).round().astype(int).clip(lower=1)
    alloc = pd.concat([alloc, sizes.clip(upper=MIN_PER_STRATUM)], axis=1).max(axis=1).clip(upper=sizes)
    while alloc.sum() > N:                       # trim from the largest strata
        alloc[alloc.idxmax()] -= 1
    while alloc.sum() < N:
        alloc[(sizes - alloc).idxmax()] += 1

    s = pd.concat([c[c["stratum"] == k].sample(int(n), random_state=SEED) for k, n in alloc.items()])
    s = s.sample(frac=1, random_state=SEED)       # shuffle so strata are mixed while labelling
    first = air[air["aircraft_seq"] == 1].set_index("source_record_id")
    s["aircraft"] = s["source_record_id"].map(
        (first["make"].fillna("") + " " + first["model"].fillna("")).str.strip())
    return s


def write(s: pd.DataFrame):
    wb = Workbook()
    ws = wb.active
    ws.title = "Label"
    head = ["#", "record_id", "date", "aircraft", "damage", "fatalities",
            "probable_cause", "findings", "cictt_code", "notes"]
    ws.append(head)
    for i, r in enumerate(s.itertuples(), 1):
        findings = "\n".join(SPLIT.split(r.findings)) if isinstance(r.findings, str) else ""
        values = [i, r.source_record_id, str(r.occ_date), r.aircraft, r.damage,
                  int(r.fatalities) if pd.notna(r.fatalities) else 0, r.source_text, findings, None, None]
        # a few NTSB texts carry invisible control characters that Excel cannot store
        ws.append([ILLEGAL_CHARACTERS_RE.sub("", v) if isinstance(v, str) else v for v in values])
    widths = {"A": 5, "B": 13, "C": 11, "D": 20, "E": 12, "F": 9, "G": 60, "H": 60, "I": 12, "J": 25}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDEBF7")
    for cell in ws["I"][1:]:
        cell.fill = PatternFill("solid", fgColor="FFF2CC")
    ws.freeze_panes = "C2"
    dv = DataValidation(type="list", formula1='"' + ",".join(c for c, _, _ in CODES) + '"',
                        allow_blank=True, showErrorMessage=True,
                        errorTitle="Unknown code", error="Pick a code from the list (see the Codes tab).")
    ws.add_data_validation(dv)
    dv.add(f"I2:I{len(s) + 1}")

    codes = wb.create_sheet("Codes")
    codes.append(["code", "name", "use when"])
    for c in CODES:
        codes.append(list(c))
    for col, w in {"A": 9, "B": 42, "C": 100}.items():
        codes.column_dimensions[col].width = w
    for cell in codes[1]:
        cell.font = Font(bold=True)

    how = wb.create_sheet("How to")
    for line in [
        "For each row on the Label tab, read probable_cause (and findings if needed) and pick ONE code in the yellow cictt_code column.",
        "Choose the category that best describes what happened to the aircraft, not why it happened.",
        "If two apply, pick the one describing the outcome (e.g. a fuel exhaustion leading to a forced landing is FUEL).",
        "If you cannot tell, use UNK. Use notes for anything you were unsure about.",
        "Definitions are on the Codes tab.",
        "When finished, save a copy as data/labelled_seed.xlsx (keep the columns as they are).",
    ]:
        how.append([line])
    how.column_dimensions["A"].width = 130
    wb.move_sheet("How to", offset=-2)
    wb.active = 1
    wb.save(OUT)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=N)
    s = sample(ap.parse_args().rows)
    write(s)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(s)} rows from {s['stratum'].nunique()} findings strata")
    print(s["stratum"].value_counts().to_string())
