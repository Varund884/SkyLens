# Data notes

## Sources

| File | Source | Coverage | Purpose |
|---|---|---|---|
| CADORS (5 CSVs) | Transport Canada, open.canada.ca | 1964-06-09 to 2026-08-24 | Canadian occurrences |
| ntsb_12mo.csv | NTSB CAROL | 2025-07-01 to 2026-06-30 | US occurrences, counted in rates |
| ntsb_corpus.csv | NTSB CAROL (4 merged exports) | 2014-01-01 to 2024-12-31 | Text corpus, never counted |
| BTS on-time (12 CSVs) | transtats.bts.gov | 2025-07 to 2026-06 | US flight operations + rate denominator |
| OurAirports (5 CSVs) | ourairports.com, CC0 | current | Airport reference and map geometry |
| 4 PDFs | FAA, TC, NTSB, TSB | - | Retrieval grounding corpus |

## Analysis window: 2025-07-01 to 2026-06-30

Aligned across CADORS, NTSB and BTS. Rates are only valid here because BTS
movement counts (the denominator) exist only for this period.

CADORS occurrences in window: 23,285
Top airports: CYYZ 1116, CYVR 787, CYUL 730, CYLW 560, CYYC 482

Rates and counts read only rows with in_analysis_window = 1. Enforced with
a view so the mistake is structurally impossible:

    CREATE VIEW v_occurrence_analysis AS
    SELECT * FROM fact_occurrence WHERE in_analysis_window = 1;

## Encoding

All CADORS CSVs are UTF-8. Reading as latin-1 produces mojibake.

## Ragged rows

5 rows across 1.9M fail to parse - backslash-escaped quotes inside quoted
fields (e.g. 82 35'02\"W) where RFC 4180 expects doubled quotes.
Use on_bad_lines='skip'. Dropped: Occurrence_Information 1, Aircraft_Information 4.

## Metadata files unavailable

open.canada.ca record a348c1d1 lists 5 metadata TXT resources on
opendatatc.blob.core.windows.net. That host returns NXDOMAIN as of Sept 2026;
the CSV host (opendatatc.tc.canada.ca) is live. Schema reverse-engineered from
headers and value profiling.

## No narrative text in CADORS

The open data extract contains structured fields only. The CADORS web
interface shows narratives; the CSVs do not. Text corpus is therefore NTSB
ProbableCause and Findings, plus the Pilot/Controller Glossary for term
definitions.

## Row counts (full history)

    Occurrence_Information        405,642
    Occurrence_Event_Information  196,092
    Aircraft_Information          330,325
    Aircraft_Event_Information    430,914
    Occurrence_Category           560,124

## Join keys - verified

cadorsnumber joins cleanly across all five CADORS files (1 orphan total).

111,128 of 405,642 occurrences (27%) have NO aircraft row. These are ATM,
aerodrome and facility events with no aircraft involved. Use LEFT joins and
handle aircraft-less occurrences in the UI.

aircraftnumber is float in Aircraft_Information (521473.0) and int in
Aircraft_Event_Information (448703). Casting to str gives a 0% join rate.
Cast both with pd.to_numeric(errors='coerce').astype('Int64') - verified:
1 orphan out of 290,033 keys.

## Key columns

occurrence: cadorsnumber, occurrencedate (ISO), occurrencetime ('1915 Z'),
  aerodromeid (ICAO), occurrencetypedescriptione (Incident/Accident),
  fatalities, Injuries, subdivision_enm, tc_region_enm, occurrencelocation
aircraft:   flightnumber, aircraftregistration, foreignaircraftregistration,
  phasenamee, damagedescriptione, operator, aircraft_make_name_nm,
  aircraft_model_name_nm
events:     event_name_enm - 131 occurrence-level types, 143 aircraft-level types
category:   occurrence_category_etxt - 37 values, already CICTT wording

## Numerics

fatalities and Injuries parse correctly with pd.to_numeric. No special
handling needed despite the 0E-18 display form. Range 0 to 229, zero nulls.

## Registrations

CADORS strips the dash: 4 chars, 99.9% start with F or G, none contain '-'.
Normalize by prefixing 'C-' ('FLPA' -> C-FLPA).
foreignaircraftregistration is already correct ('N6409H').
CA regs: 138,542 | foreign regs: 18,346

## Aerodrome matching - verified

1,437 distinct CADORS aerodromes, 98.9% match OurAirports ident.

Unmatched are CLOSED airports that OurAirports excludes under type='closed':
CYKZ (Toronto Buttonville, 1593 records), CYXD (Edmonton City Centre, 872),
CYSR, CSK3, CSS3, CNB9, CYTB, CPN4.

Do NOT filter closed airports out of dim_airport. Flag them is_closed
instead, or 2,500+ records lose their location.

## Null aerodromes are en-route - verified

92,284 records (21.4% of the window) have no aerodromeid.
occurrencelocation confirms: airspace references, bearings and distances from
airports, raw coordinates. Some values are French.
worldareaname: North America 87,139 | Gander Oceanic 3,943 | Europe 496.
Counted nationally, excluded from the map.

## Flight numbers

58.8% present (194,138 of 330,325).
94.7% are clean ICAO callsigns after stripping spaces.
1,549 are N-registrations sitting in the flightnumber field - route to
registration matching.
8,821 other: operator code only ('PAG') or suffixed ('GLR204T').
Top prefixes: ACA 25374, JZA 21200, WJA 16993, WEN 5236, POE 4291

### Minimal BTS overlap - by design

BTS covers US domestic flights only. CADORS is dominated by Canadian carriers
(ACA/JZA/WJA/WEN/POE/TSC/ROU), none of which appear in BTS. US carriers seen in
CADORS (UAL/AAL/DAL/SKW) are flying into Canada, i.e. international, also
excluded from BTS.

Consequence: flightnumber is used for CADORS-to-CADORS matching ("other
occurrences on ACA903"), not for joining CADORS to BTS.
Confirms the My Flight scope: US domestic only, with a coverage indicator.

## Match confidence tiers

    exact_flight    normalized flight number matches
    registration    N# or C-Fxxx matches
    operator_route  operator + city pair match

## NTSB - rate file

ntsb_12mo.csv, 2025-07-01 to 2026-06-30.
ProbableCause 73% null, Findings 72.4% null - investigations take 1-2 years
and recent cases are still 'In work'. Counts and rates only.

## NTSB - text corpus

ntsb_corpus.csv - 18,628 records, 2014-01-01 to 2024-12-31, merged from 4
CAROL exports (10k per-export cap), deduped on NtsbNo (0 duplicates).
ProbableCause and Findings populated: 78.8% (14,681 usable).
Loaded with in_analysis_window = 0.

### Findings structure - verified

Delimited hierarchy, not free text. 100% contain ' - '.
Mean 3.05 findings per row (median 3, max 27).
Split on ', ' for separate findings, ' - ' for hierarchy levels.

23 level-1 classes, but requires normalization:
  'Personnel issues' (17,447) vs 'Personnel' (161) - same class
  'Organizational issues' (600) vs 'Organizational' (189) - same class
  'deice' (100) - malformed value
  'Pipeline', 'Vessels and equipment' - non-aviation records in the export

Filter to Mode == 'Aviation' before use.
Usable classes after cleanup: Personnel issues, Aircraft, Environmental
issues, Organizational issues, Not determined.

### N# format

80.2% start with 'N'. Multi-aircraft rows hold comma-separated values
('N4407T, N2889K'). Foreign registrations appear ('CN-ROJ').
Split on ', ' and take the first element.

## Taxonomy harmonization

CADORS occurrence_category_etxt already uses CICTT wording (Runway excursion,
CFIT, LOC-I, SCF-PP, USOS, ARC). Canada to CICTT is close to 1:1.

NTSB has no CICTT category field - only the Findings hierarchy and free-text
ProbableCause. Mapping NTSB to CICTT is the substantive harmonization work.

## 'Other' category

139,946 CADORS records (25%) are categorized 'Other' - too broad to map
meaningfully. Counted in totals, excluded from category breakdown charts,
disclosed in the app's data limitations section.
