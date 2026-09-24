"""SkyLens API: aviation safety and operations for US and Canadian airports.

Everything served here was computed in batch (etl/ and ai/) and stored in Azure
SQL. No model is ever called while answering a request: the endpoints are plain
indexed reads, which is why they are fast and cost nothing to run.

    uvicorn api.main:app --reload      # http://127.0.0.1:8000/docs
"""
import json
import re

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import cached_query, query
from .models import (AirportPin, Category, FlightHistory, FlightLeg, Health,
                     Occurrence, OccurrencePage, Theme)

app = FastAPI(
    title="SkyLens API",
    version="1.0",
    description="Occurrence rates, airport reports and flight history for the US and Canada. "
                "Rates are per 10,000 aircraft movements and use official traffic counts "
                "(FAA ATADS, Statistics Canada, BTS). Categories marked as predicted come from "
                "a model, not from the reporting authority.",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

MAX_PINS = 500
# CADORS mixes aircraft events with service reports (ATM equipment, staffing).
# The report mart counts only aircraft-involved occurrences, so the occurrence
# list must use the same rule or the page would show two different totals.
# An airline code is two characters and always contains a letter (AA, B6, 9E),
# so a bare number like "100" is not mistaken for carrier "10" plus "0".
FLIGHT_NUMBER = re.compile(r"^([A-Z][A-Z0-9]|[0-9][A-Z])?0*(\d{1,4})$")
AIRCRAFT_INVOLVED = "(s.name <> 'Transport Canada' OR ISNULL(o.aircraft_count, 0) > 0)"
# CA-1292 is a malformed OurAirports record ("YEG", typed large_airport, with
# coordinates in rural Saskatchewan). It would draw a false major airport.
BAD_IDENTS = ("CA-1292",)


@app.get("/health", response_model=Health, tags=["meta"])
def health():
    try:
        a = query("SELECT COUNT(*) AS n FROM dim_airport")[0]["n"]
        o = query("SELECT COUNT(*) AS n FROM v_occurrence_analysis")[0]["n"]
        m = query("SELECT COUNT(*) AS n FROM mart_airport_report")[0]["n"]
        return Health(status="ok", database="connected", airports=a,
                      occurrences_in_window=o, airport_reports=m)
    except Exception as e:
        raise HTTPException(503, f"database unavailable: {type(e).__name__}")


@app.get("/airports", response_model=list[AirportPin], tags=["map"])
def airports(
    north: float | None = Query(None, ge=-90, le=90, description="Top of the visible map"),
    south: float | None = Query(None, ge=-90, le=90),
    east: float | None = Query(None, ge=-180, le=180),
    west: float | None = Query(None, ge=-180, le=180),
    min_occurrences: int = Query(0, ge=0, description="Only airports with at least this many"),
    limit: int = Query(MAX_PINS, ge=1, le=MAX_PINS),
):
    """Airports for the map.

    With a bounding box, returns what is inside the current view. Without one
    (the zoomed-out first load), returns the airports with the most occurrences,
    so the continent view is useful rather than 36,000 identical dots.
    """
    where = ["a.is_closed = 0", "a.latitude IS NOT NULL", f"a.ident NOT IN ('{BAD_IDENTS[0]}')"]
    params: list = []
    if None not in (north, south, east, west):
        where.append("a.latitude BETWEEN %s AND %s AND a.longitude BETWEEN %s AND %s")
        params += [min(south, north), max(south, north), min(west, east), max(west, east)]
    if min_occurrences:
        where.append("ISNULL(m.occurrences, 0) >= %s")
        params.append(min_occurrences)

    sql = f"""
    SELECT TOP {limit} a.ident, a.name, a.municipality, a.iso_country AS country,
           a.airport_type, a.latitude, a.longitude,
           ISNULL(m.occurrences, 0) AS occurrences, m.rate_per_10k,
           CASE WHEN m.airport_key IS NULL THEN 0 ELSE 1 END AS has_report
    FROM dim_airport a
    LEFT JOIN (
        SELECT airport_key,
               CAST(JSON_VALUE(payload, '$.occurrences') AS INT) AS occurrences,
               CAST(JSON_VALUE(payload, '$.rate_per_10k') AS FLOAT) AS rate_per_10k
        FROM mart_airport_report
    ) m ON m.airport_key = a.airport_key
    WHERE {' AND '.join(where)}
    ORDER BY ISNULL(m.occurrences, 0) DESC, a.airport_type, a.ident
    """
    rows = cached_query(sql, tuple(params))
    return [AirportPin(**{**r, "has_report": bool(r["has_report"])}) for r in rows]


@app.get("/airports/{ident}/report", tags=["airport"])
def airport_report(ident: str):
    """The precomputed report for one airport: counts, rate, trend, categories,
    themes, peer comparison, US operations stats and a short generated note."""
    rows = cached_query(
        "SELECT r.payload, r.generated_at FROM mart_airport_report r "
        "JOIN dim_airport a ON a.airport_key = r.airport_key WHERE a.ident = %s", (ident.upper(),))
    if not rows:
        exists = query("SELECT ident FROM dim_airport WHERE ident = %s", (ident.upper(),))
        if exists:
            raise HTTPException(404, f"{ident.upper()} has fewer than 5 reported occurrences "
                                     "in the last 12 months, so no report was built")
        raise HTTPException(404, f"no airport with ident {ident.upper()}")
    payload = json.loads(rows[0]["payload"])
    payload["generated_at"] = str(rows[0]["generated_at"])
    return payload


@app.get("/airports/{ident}/occurrences", response_model=OccurrencePage, tags=["airport"])
def airport_occurrences(
    ident: str,
    category: str | None = Query(None, description="CICTT code, e.g. RE"),
    month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    offset: int = Query(0, ge=0),
    limit: int = Query(25, ge=1, le=100),
):
    """Individual occurrences at an airport, newest first, with their
    plain-English summaries and the passages those summaries cite.

    Counts match the airport report: Canadian service reports with no aircraft
    involved are left out. Transport Canada sometimes files more than one
    report for a single event, so near-identical entries a minute apart are
    genuine separate records, not a bug.
    """
    where = ["a.ident = %s", AIRCRAFT_INVOLVED]
    params: list = [ident.upper()]
    if category:
        where.append("c.cictt_code = %s")
        params.append(category.upper())
    if month:
        where.append("LEFT(CAST(o.date_key AS VARCHAR(8)), 6) = %s")
        params.append(month.replace("-", ""))
    clause = " AND ".join(where)

    total = query(f"""
        SELECT COUNT(*) AS n FROM v_occurrence_analysis o
        JOIN dim_airport a ON a.airport_key = o.airport_key
        JOIN dim_source_authority s ON s.authority_key = o.authority_key
        LEFT JOIN dim_category c ON c.category_key = o.category_key
        WHERE {clause}""", tuple(params))[0]["n"]

    rows = query(f"""
        SELECT o.occurrence_key, o.date_key, o.occurrence_time_utc, s.name AS authority,
               o.source_record_id, o.occurrence_type, c.cictt_code, c.cictt_label,
               o.category_source, o.category_confidence, o.severity_tier, o.fatalities,
               o.injuries, o.aircraft_count, o.flight_number, o.registration, o.operator_name,
               o.narrative_plain, o.citation_ids, t.label AS theme
        FROM v_occurrence_analysis o
        JOIN dim_airport a ON a.airport_key = o.airport_key
        JOIN dim_source_authority s ON s.authority_key = o.authority_key
        LEFT JOIN dim_category c ON c.category_key = o.category_key
        LEFT JOIN dim_theme t ON t.theme_key = o.theme_key
        WHERE {clause}
        ORDER BY o.date_key DESC, o.occurrence_key DESC
        OFFSET {offset} ROWS FETCH NEXT {limit} ROWS ONLY""", tuple(params))

    items = [Occurrence(
        occurrence_key=r["occurrence_key"],
        date=f"{str(r['date_key'])[:4]}-{str(r['date_key'])[4:6]}-{str(r['date_key'])[6:]}",
        time_utc=str(r["occurrence_time_utc"])[:5] if r["occurrence_time_utc"] else None,
        authority=r["authority"], source_record_id=r["source_record_id"],
        occurrence_type=r["occurrence_type"], category_code=r["cictt_code"],
        category_label=r["cictt_label"], category_is_predicted=r["category_source"] == "model",
        category_confidence=r["category_confidence"], severity_tier=r["severity_tier"],
        fatalities=r["fatalities"], injuries=r["injuries"], aircraft_count=r["aircraft_count"],
        flight_number=r["flight_number"], registration=r["registration"],
        operator_name=r["operator_name"], summary=r["narrative_plain"],
        citation_ids=(r["citation_ids"] or "").split(",") if r["citation_ids"] else [],
        theme=r["theme"]) for r in rows]
    return OccurrencePage(total=total, offset=offset, limit=limit, items=items)


@app.get("/flights/{flight_number}", response_model=FlightHistory, tags=["flight"])
def flight_history(
    flight_number: str,
    origin: str | None = Query(None, description="Filter by origin airport ident"),
    limit: int = Query(50, ge=1, le=200, description="How many legs to list; the statistics always cover every leg"),
):
    """Every scheduled leg of a US domestic flight number in the 12-month window,
    with its delays and cancellations.

    Accepts "AA100", "AA 100" or just "100". BTS stores the airline code and the
    number in separate columns, so the airline part is matched against the
    operator's IATA code (AA, DL, WN, ...) and the digits against the number.
    """
    m = FLIGHT_NUMBER.match(flight_number.upper().replace(" ", ""))
    if not m:
        raise HTTPException(422, "flight number should look like AA100, AA 100 or 100")
    carrier, digits = m.group(1), str(int(m.group(2)))      # drop any leading zeros
    where = ["f.flight_number = %s"]
    params: list = [digits]
    if carrier:
        where.append("o.iata_code = %s")
        params.append(carrier)
    if origin:
        where.append("og.ident = %s")
        params.append(origin.upper())
    clause = " AND ".join(where)

    rows = query(f"""
        SELECT TOP {limit} f.date_key,
               COALESCE(NULLIF(og.iata_code, ''), og.ident) AS origin,
               COALESCE(NULLIF(de.iata_code, ''), de.ident) AS destination,
               og.ident AS origin_ident, de.ident AS destination_ident,
               f.sched_dep, f.actual_dep, f.dep_delay_min, f.arr_delay_min,
               f.cancelled, f.cancellation_code, f.diverted, f.tail_number, o.name AS operator
        FROM fact_flight_performance f
        LEFT JOIN dim_airport og ON og.airport_key = f.origin_airport_key
        LEFT JOIN dim_airport de ON de.airport_key = f.dest_airport_key
        LEFT JOIN dim_operator o ON o.operator_key = f.operator_key
        WHERE {clause}
        ORDER BY f.date_key DESC""", tuple(params))
    if not rows:
        # Users guess famous numbers (AA100 is JFK-London), but BTS covers US
        # domestic flights only, so point them at numbers that do exist.
        near = cached_query("""
            SELECT TOP 5 o.iata_code + f.flight_number AS flight, COUNT(*) AS legs
            FROM fact_flight_performance f
            JOIN dim_operator o ON o.operator_key = f.operator_key
            WHERE (%s IS NULL OR o.iata_code = %s)
            GROUP BY o.iata_code + f.flight_number
            ORDER BY COUNT(*) DESC""", (carrier, carrier))
        hint = ", ".join(r["flight"] for r in near)
        raise HTTPException(404, f"no flights found for {carrier or ''}{digits}. This covers US domestic "
                                 f"flights by reporting carriers, July 2025 to June 2026"
                                 + (f". Try {hint}." if hint else "."))

    # Statistics cover every leg in the window, not just the page being shown,
    # so "86% on time" means the year, not the most recent 50 flights.
    stats = query(f"""
        SELECT COUNT(*) AS legs,
               SUM(CASE WHEN f.cancelled = 1 THEN 1 ELSE 0 END) AS cancelled,
               SUM(CASE WHEN f.cancelled = 0 AND f.dep_delay_min IS NOT NULL THEN 1 ELSE 0 END) AS measured,
               SUM(CASE WHEN f.cancelled = 0 AND f.dep_delay_min <= 15 THEN 1 ELSE 0 END) AS on_time,
               MAX(f.dep_delay_min) AS worst
        FROM fact_flight_performance f
        LEFT JOIN dim_airport og ON og.airport_key = f.origin_airport_key
        LEFT JOIN dim_operator o ON o.operator_key = f.operator_key
        WHERE {clause}""", tuple(params))[0]
    median = query(f"""
        SELECT DISTINCT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY f.dep_delay_min)
               OVER () AS median_delay
        FROM fact_flight_performance f
        LEFT JOIN dim_airport og ON og.airport_key = f.origin_airport_key
        LEFT JOIN dim_operator o ON o.operator_key = f.operator_key
        WHERE {clause} AND f.cancelled = 0 AND f.dep_delay_min IS NOT NULL""", tuple(params))
    codes = {"A": "carrier", "B": "weather", "C": "national air system", "D": "security"}
    legs = [FlightLeg(
        date=f"{str(r['date_key'])[:4]}-{str(r['date_key'])[4:6]}-{str(r['date_key'])[6:]}",
        origin=r["origin"], destination=r["destination"],
        origin_ident=r.get("origin_ident"), destination_ident=r.get("destination_ident"),
        scheduled_departure=str(r["sched_dep"])[:5] if r["sched_dep"] else None,
        actual_departure=str(r["actual_dep"])[:5] if r["actual_dep"] else None,
        departure_delay_min=r["dep_delay_min"], arrival_delay_min=r["arr_delay_min"],
        cancelled=bool(r["cancelled"]),
        cancellation_reason=codes.get((r["cancellation_code"] or "").strip()),
        diverted=bool(r["diverted"]), tail_number=r["tail_number"]) for r in rows]

    measured, total_legs = stats["measured"] or 0, stats["legs"] or 0
    return FlightHistory(
        flight_number=f"{carrier or ''}{digits}",
        operator=next((r["operator"] for r in rows if r["operator"]), None),
        legs_found=total_legs,
        on_time_pct=round(stats["on_time"] / measured * 100, 1) if measured else None,
        cancelled_pct=round(stats["cancelled"] / total_legs * 100, 1) if total_legs else None,
        median_departure_delay_min=float(median[0]["median_delay"]) if median else None,
        worst_delay_min=stats["worst"],
        routes=sorted({f"{r['origin']}-{r['destination']}" for r in rows if r["origin"] and r["destination"]}),
        legs=legs)


@app.get("/categories", response_model=list[Category], tags=["reference"])
def categories():
    """Occurrence categories with how many occurrences fall in each, for filters."""
    rows = cached_query("""
        SELECT c.cictt_code AS code, c.cictt_label AS label, COUNT(o.occurrence_key) AS occurrences
        FROM dim_category c
        LEFT JOIN v_occurrence_analysis o ON o.category_key = c.category_key
        WHERE c.exclude_from_charts = 0
        GROUP BY c.cictt_code, c.cictt_label
        HAVING COUNT(o.occurrence_key) > 0
        ORDER BY COUNT(o.occurrence_key) DESC""")
    return [Category(**r) for r in rows]


@app.get("/themes", response_model=list[Theme], tags=["reference"])
def themes():
    """Themes found by clustering NTSB reports. US reports only: CADORS has no text."""
    rows = cached_query("SELECT label, member_count FROM dim_theme ORDER BY member_count DESC")
    return [Theme(**r) for r in rows]
