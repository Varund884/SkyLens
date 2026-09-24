"""Endpoint behaviour, over HTTP, with the database faked.

What is worth testing here is not that SQL Server works, but the decisions the
API makes on the way in and out: which rows it excludes, how it reports a
missing airport, and whether a model-assigned category is still labelled as one
by the time it reaches the browser.
"""
AIRPORT_ROW = {
    "ident": "CYYZ", "name": "Toronto Pearson International Airport",
    "municipality": "Toronto", "country": "CA", "airport_type": "large_airport",
    "latitude": 43.6772, "longitude": -79.6306,
    "occurrences": 1089, "rate_per_10k": 2.7, "has_report": 1,
}

OCCURRENCE_ROW = {
    "occurrence_key": 1, "date_key": 20250704, "occurrence_time_utc": "14:32:00",
    "authority": "Transport Canada", "source_record_id": "2025C1234",
    "occurrence_type": "Incident", "cictt_code": "BIRD", "cictt_label": "Birdstrike",
    "category_source": "source", "category_confidence": None, "severity_tier": "minor",
    "fatalities": 0, "injuries": 0, "aircraft_count": 1, "flight_number": "AC123",
    "registration": "C-FGDT", "operator_name": "Air Canada",
    "narrative_plain": "A bird struck the aircraft shortly after takeoff.",
    "citation_ids": "pcg-birdstrike,pcg-goaround", "theme": "Wildlife on or near the runway",
}

LEG_ROW = {
    "date_key": 20250704, "origin": "JFK", "destination": "LAX",
    "origin_ident": "KJFK", "destination_ident": "KLAX",
    "sched_dep": "08:00:00", "actual_dep": "08:12:00", "dep_delay_min": 12,
    "arr_delay_min": 4, "cancelled": 0, "cancellation_code": None,
    "diverted": 0, "tail_number": "N787AA", "operator": "American Airlines",
}


# --- health ---------------------------------------------------------------

def test_health_reports_the_row_counts(client, db):
    db.on("dim_airport", [{"n": 36000}])
    db.on("v_occurrence_analysis", [{"n": 19162}])
    db.on("mart_airport_report", [{"n": 495}])
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["airports"] == 36000
    assert body["airport_reports"] == 495


def test_health_is_a_503_when_the_database_is_down(client, db):
    db.fail(RuntimeError("login timeout for user skylens_admin"))
    r = client.get("/health")
    assert r.status_code == 503
    assert "skylens_admin" not in r.text          # never leak credentials or driver detail


# --- map ------------------------------------------------------------------

def test_airports_returns_pins_and_coerces_has_report(client, db):
    db.on("FROM dim_airport a", [AIRPORT_ROW])
    pins = client.get("/airports").json()
    assert len(pins) == 1
    assert pins[0]["ident"] == "CYYZ"
    assert pins[0]["has_report"] is True          # 1 from SQL, bool on the wire


def test_a_bounding_box_is_normalised_before_it_is_bound(client, db):
    """Leaflet can hand back a box with the corners the other way round."""
    db.on("FROM dim_airport a", [])
    client.get("/airports", params={"north": 40, "south": 50, "east": -80, "west": -70})
    south, north, west, east = db.last_params
    assert south < north and west < east


def test_the_known_bad_ourairports_record_is_excluded(client, db):
    db.on("FROM dim_airport a", [])
    client.get("/airports")
    assert "CA-1292" in db.last_sql


def test_min_occurrences_is_bound_not_interpolated(client, db):
    db.on("FROM dim_airport a", [])
    client.get("/airports", params={"min_occurrences": 5})
    assert db.last_params == (5,)
    assert "%s" in db.sql_containing("ISNULL(m.occurrences, 0) >=")


def test_an_oversized_limit_is_rejected(client, db):
    db.on("FROM dim_airport a", [])
    assert client.get("/airports", params={"limit": 100000}).status_code == 422


# --- airport report -------------------------------------------------------

def test_report_is_returned_with_its_generated_at(client, db):
    db.on("FROM mart_airport_report r", [{"payload": '{"ident":"CYYZ","occurrences":1089}',
                                          "generated_at": "2026-09-23 10:00:00"}])
    body = client.get("/airports/cyyz/report").json()
    assert body["occurrences"] == 1089
    assert body["generated_at"].startswith("2026-09-23")


def test_a_real_airport_with_too_few_occurrences_says_so(client, db):
    db.on("FROM mart_airport_report r", [])
    db.on("FROM dim_airport WHERE ident", [{"ident": "CYKF"}])
    r = client.get("/airports/CYKF/report")
    assert r.status_code == 404
    assert "fewer than 5" in r.json()["detail"]


def test_an_unknown_ident_says_that_instead(client, db):
    db.on("FROM mart_airport_report r", [])
    db.on("FROM dim_airport WHERE ident", [])
    r = client.get("/airports/zzzz/report")
    assert r.status_code == 404
    assert "no airport with ident ZZZZ" in r.json()["detail"]


# --- occurrences ----------------------------------------------------------

def test_occurrences_are_shaped_for_the_browser(client, db):
    db.on("SELECT COUNT(*) AS n FROM v_occurrence_analysis", [{"n": 1}])
    db.on("SELECT o.occurrence_key", [OCCURRENCE_ROW])
    body = client.get("/airports/CYYZ/occurrences").json()
    item = body["items"][0]
    assert body["total"] == 1
    assert item["date"] == "2025-07-04"           # 20250704 -> ISO
    assert item["time_utc"] == "14:32"
    assert item["citation_ids"] == ["pcg-birdstrike", "pcg-goaround"]


def test_an_official_category_is_not_marked_predicted(client, db):
    db.on("SELECT COUNT(*) AS n FROM v_occurrence_analysis", [{"n": 1}])
    db.on("SELECT o.occurrence_key", [OCCURRENCE_ROW])
    item = client.get("/airports/CYYZ/occurrences").json()["items"][0]
    assert item["category_is_predicted"] is False


def test_a_model_category_is_marked_predicted(client, db):
    db.on("SELECT COUNT(*) AS n FROM v_occurrence_analysis", [{"n": 1}])
    db.on("SELECT o.occurrence_key",
          [{**OCCURRENCE_ROW, "category_source": "model", "category_confidence": 0.82}])
    item = client.get("/airports/CYYZ/occurrences").json()["items"][0]
    assert item["category_is_predicted"] is True
    assert item["category_confidence"] == 0.82


def test_canadian_service_reports_are_filtered_out(client, db):
    """The occurrence list and the report mart must agree on what counts."""
    db.on("SELECT COUNT(*) AS n FROM v_occurrence_analysis", [{"n": 0}])
    db.on("SELECT o.occurrence_key", [])
    client.get("/airports/CYYZ/occurrences")
    assert "aircraft_count" in db.sql_containing("FROM v_occurrence_analysis")


def test_a_malformed_month_filter_is_rejected(client, db):
    db.on("SELECT COUNT(*) AS n FROM v_occurrence_analysis", [{"n": 0}])
    assert client.get("/airports/CYYZ/occurrences", params={"month": "July"}).status_code == 422


# --- flights --------------------------------------------------------------

def test_an_unknown_flight_number_suggests_real_ones(client, db):
    db.on("SELECT TOP 50 f.date_key", [])
    db.on("SELECT TOP 5 o.iata_code", [{"flight": "AA1", "legs": 349},
                                       {"flight": "AA2", "legs": 341}])
    r = client.get("/flights/AA9999")
    assert r.status_code == 404
    assert "AA1" in r.json()["detail"]
    assert "US domestic" in r.json()["detail"]


def test_flight_codes_are_the_ones_travellers_recognise(client, db):
    """IATA (JFK), not the ICAO ident (KJFK), which is what the table stores."""
    db.on("SELECT TOP 50 f.date_key", [])
    db.on("SELECT TOP 5 o.iata_code", [])
    client.get("/flights/AA9999")
    assert "iata_code" in db.sql_containing("f.date_key")


def test_statistics_cover_every_leg_not_just_the_page(client, db):
    db.on("SELECT TOP 50 f.date_key", [LEG_ROW])
    db.on("SELECT COUNT(*) AS legs", [{"legs": 349, "cancelled": 7, "measured": 342,
                                       "on_time": 300, "worst": 260}])
    db.on("PERCENTILE_CONT", [{"median_delay": 9.0}])
    body = client.get("/flights/AA1").json()
    assert body["legs_found"] == 349              # not the single leg listed
    assert len(body["legs"]) == 1
    assert body["on_time_pct"] == round(300 / 342 * 100, 1)
    assert body["cancelled_pct"] == round(7 / 349 * 100, 1)
    assert body["routes"] == ["JFK-LAX"]


def test_a_leg_carries_the_ident_needed_to_link_to_the_airport_report(client, db):
    """The table shows JFK; the link has to go to /airport/KJFK."""
    db.on("SELECT TOP 50 f.date_key", [LEG_ROW])
    db.on("SELECT COUNT(*) AS legs", [{"legs": 1, "cancelled": 0, "measured": 1,
                                       "on_time": 1, "worst": 12}])
    db.on("PERCENTILE_CONT", [{"median_delay": 12.0}])
    leg = client.get("/flights/AA1").json()["legs"][0]
    assert (leg["origin"], leg["origin_ident"]) == ("JFK", "KJFK")
    assert (leg["destination"], leg["destination_ident"]) == ("LAX", "KLAX")


def test_a_cancellation_code_becomes_a_reason(client, db):
    db.on("SELECT TOP 50 f.date_key",
          [{**LEG_ROW, "cancelled": 1, "cancellation_code": "B", "dep_delay_min": None}])
    db.on("SELECT COUNT(*) AS legs", [{"legs": 1, "cancelled": 1, "measured": 0,
                                       "on_time": 0, "worst": None}])
    db.on("PERCENTILE_CONT", [])
    body = client.get("/flights/AA1").json()
    assert body["legs"][0]["cancelled"] is True
    assert body["legs"][0]["cancellation_reason"] == "weather"
    assert body["on_time_pct"] is None            # nothing measurable to average


def test_an_unparseable_flight_number_is_a_422(client, db):
    assert client.get("/flights/not-a-flight").status_code == 422


# --- reference ------------------------------------------------------------

def test_categories_hide_the_ones_marked_excluded(client, db):
    db.on("FROM dim_category c", [{"code": "BIRD", "label": "Birdstrike", "occurrences": 4200}])
    assert client.get("/categories").json()[0]["code"] == "BIRD"
    assert "exclude_from_charts = 0" in db.last_sql


def test_themes_come_back_largest_first(client, db):
    db.on("FROM dim_theme", [{"label": "Wildlife near the runway", "member_count": 812}])
    assert client.get("/themes").json()[0]["member_count"] == 812
    assert "ORDER BY member_count DESC" in db.last_sql
