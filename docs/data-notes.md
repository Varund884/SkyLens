# Data notes

## Sources

| File | Source | Coverage | Purpose |
|---|---|---|---|
| CADORS (5 CSVs) | Transport Canada, open.canada.ca | 1964-06-09 to 2026-08-24 | Canadian occurrences |
| ntsb_12mo.csv | NTSB CAROL | 2025-07-01 to 2026-06-30 | US occurrences, counted in rates |
| ntsb_corpus.csv | NTSB CAROL (4 merged exports) | 2014-01-01 to 2024-12-31 | Text corpus, never counted |
| BTS on-time (12 CSVs) | transtats.bts.gov | 2025-07 to 2026-06 | US flight operations + rate denominator |
| 23100296-SDMX.zip | Statistics Canada table 23-10-0296 | 2025-07 to 2026-06 | Canadian rate denominator |
| faa_atads_daily.xls | FAA ATADS (aspm.faa.gov/opsnet) | 2025-07-01 to 2026-06-30 | US towered-airport rate denominator |
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
foreignaircraftregistration is correct for US marks ('N6409H') but other
countries are also dashless ('A6XWE' = A6-XWE, 'EIGAJ' = EI-GAJ). Stored as
reported. Joins to BTS Tail_Number are unaffected, since BTS is US-only.
CA regs: 138,542 | foreign regs: 18,346

## Aerodrome matching - verified

1,437 distinct CADORS aerodromes. 98.9% match OurAirports ident directly.

The unmatched codes are not missing airports. When an airport closes or
changes code, OurAirports renames its ident and keeps the old code only in
the free-text `keywords` field:
  CYKZ (Toronto Buttonville, 1,593 records) -> CA-1108, closed
  CYXD (Edmonton City Centre, 872)          -> CA-1110, closed
  CNB9 -> CYLS (Barrie), CPN4 -> CYHS (Hanover), CYTB -> CNQ4 (Tillsonburg)

Fix: etl/airports.py harvests 4-character ICAO-style codes from keywords into
an alias table (652 aliases; ambiguous ones dropped, live idents never
shadowed). Closed airports are kept and flagged is_closed.
Result: 99.94% of all-history aerodromes match, 99.995% in the analysis
window (1 unmatched record: CHB3).

pandas reads the text 'NA' as missing by default; all reads of code columns
use keep_default_na=False.

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
' - ' separates hierarchy levels. Entries are separated by ', ', but entries
can contain commas themselves ('Intake anti-ice, deice'), so a naive split on
', ' produces junk classes ('deice', 'main system', 'etc)').
Correct split: only on ', ' followed by a known level-1 class and ' - '.

The apparent duplicates 'Personnel' / 'Organizational' occur only in the
non-aviation rows (marine, rail) and disappear with Mode == 'Aviation'.
Result: exactly 5 level-1 classes - Personnel issues, Aircraft,
Environmental issues, Organizational issues, Not determined.

### N# format

80.2% start with 'N'. Multi-aircraft rows hold comma-separated values
('N4407T, N2889K'). Foreign registrations appear ('CN-ROJ').
Split on ', ' and take the first element. N# sometimes holds prose
('UNREGISTERED ULTRALIGHT'); values that are not a 2-10 character mark are
treated as missing.

## Taxonomy harmonization

CADORS occurrence_category_etxt already uses CICTT wording (Runway excursion,
CFIT, LOC-I, SCF-PP, USOS, ARC). Canada to CICTT is close to 1:1.

NTSB has no CICTT category field - only the Findings hierarchy and free-text
ProbableCause. Mapping NTSB to CICTT is the substantive harmonization work.

## 'Other' category

139,946 CADORS records (25%) are categorized 'Other' - too broad to map
meaningfully. Counted in totals, excluded from category breakdown charts,
disclosed in the app's data limitations section.

## Azure OpenAI
Resource: vdawrha-4857-resource (AIServices/Foundry), rg skylens-rg, West US 3.
Note: West US 3, not Canada Central — Foundry chose the region. Relevant to
data residency and to any future region-restricting policy.

Endpoint form is https://<resource>.services.ai.azure.com/ for Foundry
resources, NOT the .openai.azure.com form used by classic Azure OpenAI.

Deployments (names are stable; code never references the underlying model):
  chat       -> gpt-4.1-mini (2025-04-14), Global Standard
  embeddings -> text-embedding-3-small v1, 1536 dims, Global Standard

gpt-4o-mini is deprecated for new deployments as of Sept 2026.
Embedding dimension 1536 must match the AI Search index vector field.

## Findings from building the parsers

### Occurrences have many categories and many aircraft
In the analysis window, 5,816 of 23,277 categorized CADORS occurrences carry
2-7 CICTT categories (CICTT explicitly permits multiple coding), and 2,078 of
15,263 occurrences with aircraft involve 2-23 aircraft (the largest is one
en-route ATC event with 23). Joining either into fact_occurrence would
duplicate occurrences and inflate every count.
Model (db/migrate_001.sql): fact_occurrence stays one row per occurrence;
bridge_occurrence_category and fact_occurrence_aircraft hold the detail.
category_key on fact_occurrence is a convenience "primary" category: the
least frequent code in the window, skipping OTHR/UNK unless nothing else
applies. Breakdown charts must use the bridge table.

### CADORS event names
23,284 of 23,285 window occurrences have at least one named event (max 267
chars joined). Stored as event_names; this is the input to plain-language
summaries for Canadian records.

### NTSB rate file is not US-only
474 of 1,700 aviation rows in ntsb_12mo.csv are foreign events the NTSB
assisted on (Brazil 52, Australia 50, UK 28, ...). Rate file restricted to
Country == 'United States': 1,226 events. Corpus keeps all countries (text
only), and 192 corpus rows are Canadian - never counted, so no double count
with CADORS.
NTSB AirportID is mostly an FAA code ('3M7', 'PEX'). Resolved via ident ->
FAA local_code (open airports preferred; 81 local codes are duplicated) ->
'K'+code -> IATA. 95% of US rows with an AirportID match; the rest are
'NONE', 'PVT', or Puerto Rico (filed under country PR).

### NTSB times
EventDate carries a Z suffix. Date-only events appear at 04:00/05:00Z
(midnight US Eastern); those times are blanked. After the US filter only 2
rate-file rows are affected.

### Multi-aircraft NTSB fields
N#, Make, Model, Operator and AirCraftDamage are comma-joined per aircraft,
but operator names contain commas ('NetJets Aviation, Inc'). Fields are
split only when their part count equals the N# count.

### BTS
7,043,316 flights, 12 months, 358 airports, 14 carriers (12-13 from 2026).
- Time fields use 2400 for midnight (hundreds of rows per month); SQL Server
  TIME rejects it, so 2400 -> 00:00.
- BTS counts PR, VI, GU, AS and MP as domestic; OurAirports files them under
  those country codes, so dim_airport includes them.
- Palm Beach: BTS still reports PBI through 2026-06; OurAirports lists KPBI
  with IATA DJT. Resolved via the 'K'+code fallback. All 358 codes resolve.
- ~124 MB of INSERT SQL per month; ~30-90 min to load on a home connection.

### Rate denominator
BTS movements are airline-only and cannot serve most occurrences: 86% of US
NTSB rate-file events are FAR Part 91 (general aviation), 85% of those with an
airport are at airports with no BTS flights, and no CADORS occurrence is at a
BTS airport.

Canada - resolved with Statistics Canada table 23-10-0296 ("Aircraft
movements, by class of operation, airports with NAV CANADA services and other
selected airports, monthly"), total itinerant + local movements.
- Table 23-10-0303, the obvious first choice, has province totals only.
- SDMX download: 29 monthly releases, each re-sending recent months with
  revisions; the latest release wins per airport-month.
- 126 airports, identified by name only. db/map_statcan_airport.csv maps them
  to ICAO idents: 113 automatic, 13 corrected by hand, all reviewed. The
  automatic matcher's errors included Hamilton -> "Hampton", Lethbridge -> a
  private strip, and several airports -> their seaplane bases.
- 5 airports publish no data for the whole window (Fort Smith, Hall Beach,
  Peace River, Resolute Bay, Stephenville); left out, never zero-filled.
  121 airports have all 12 months; total 5,759,001 movements, equal to
  StatCan's own all-airports total.
- These airports cover 96% of aircraft-involved CADORS occurrences at an
  airport (10,243 of 10,664); the rest are scattered small fields with <=10
  events each, shown as counts without a rate.
- Monthly grain, stored on the first of each month.
Rates are per total movements, which include local training circuits. Busy
training airports (Boundary Bay: 241k movements, 2.7 per 10k) therefore read
low. Disclose on the About page.

US - resolved for towered airports with FAA ATADS (Air Traffic Activity
Data System), Standard Report, grouped by Date and Airport, date Range
07/01/2025 to 06/30/2026.
- The "Excel" export is an HTML table in latin-1. The embedded query must
  read YYYYMMDD>=20250701 AND YYYYMMDD<=20260630; a first attempt with two
  single dates returned only those two days. etl/faa.py checks the range,
  and that the parsed rows add up to the report's own grand total
  (56,961,862 operations).
- 528 towered airports, 190,404 airport-days. All Facility codes (FAA LOCIDs)
  match an open airport through local_code; none unmatched, none shared.
- Operations = air carrier + air taxi + GA + military, itinerant + local; one
  takeoff or landing each, same unit as BTS and StatCan.
- Counted only while the tower is open, so part-time towers under-count.
  245 towers report fewer than 365 days (closed days, new towers such as
  Trent Lott KPQL at 150 days); missing days are left out, never zero-filled.
- FAA >= BTS at every one of the 285 airports in both (median 6x, O'Hare
  1.3x, Orlando Sanford 21x from flight training). FAA replaces BTS for the
  whole airport; each airport keeps exactly one source.
- BTS remains the denominator for 73 airline airports without an FAA tower
  (mostly Alaska and small western fields), where it under-counts.
- US rate-file occurrences at an airport with a denominator: 276 of 870
  (was 134 with BTS only): 261 FAA, 15 BTS. The other 594 are at non-towered
  general-aviation fields, for which no official count exists; they are shown
  as counts without a rate.

Combined fact_airport_movements: 722 airports (528 faa, 73 bts, 121 statcan),
215,881 rows, 62,869,907 movements.

OurAirports data issues found while matching:
- Stephenville (CYJT) is marked closed, but StatCan still reports its traffic.
- CA-1292 is a malformed record named "YEG", typed large_airport in Edmonton,
  with coordinates in rural Saskatchewan. It would render as a false major
  airport on the map; exclude it from map queries.

### CADORS mixes aircraft events with service reports
First rate check (top airports by raw count, analysis window) ranked Arctic
Bay (CYAB 287), Wemindji (CYNC 274), Quaqtaq (CYHA 256) and Aupaluk (CYLA 252)
above Winnipeg. Nearly all of those are 'ATM - operations' events with no
aircraft involved (CYNC: 274 of 274, 0 aircraft) - near-daily air navigation
service reports from remote stations, not incidents. At CYYZ, 1,089 of 1,116
occurrences involve an aircraft.
Decision: maps and rates default to aircraft-involved occurrences
(aircraft_count > 0); service reports are shown separately. Raw counts that
blend the two are misleading even with a correct denominator.

### Probable cause is missing for most recent serious accidents - verified
The NTSB publishes ProbableCause only with the final report. In the analysis
window 653 of 1,226 rate-file occurrences have it, but only 2% of fatal ones
(3 of 168) against 61% of non-fatal ones, and 35% for April-June 2026 against
63% for July-September 2025. So everything built from NTSB text in the window
(themes, classifier predictions, plain-language summaries) covers mostly
non-fatal, quickly closed accidents. Themes' growth_rate is descriptive only
and should not be shown as a trend without this caveat. Counts and rates are
unaffected: they use every occurrence, with or without text.

