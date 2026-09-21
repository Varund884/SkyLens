"""Response shapes. Pydantic validates every field before it leaves the API,
so a change in the database cannot silently send the website a wrong shape."""
from pydantic import BaseModel, Field


class AirportPin(BaseModel):
    """One dot on the map."""
    ident: str
    name: str
    municipality: str | None = None
    country: str
    airport_type: str
    latitude: float
    longitude: float
    occurrences: int = 0
    rate_per_10k: float | None = None
    has_report: bool = False


class Occurrence(BaseModel):
    occurrence_key: int
    date: str
    time_utc: str | None = None
    authority: str
    source_record_id: str
    occurrence_type: str | None = None
    category_code: str | None = None
    category_label: str | None = None
    category_is_predicted: bool = False
    category_confidence: float | None = None
    severity_tier: str | None = None
    fatalities: int | None = None
    injuries: int | None = None
    aircraft_count: int | None = None
    flight_number: str | None = None
    registration: str | None = None
    operator_name: str | None = None
    summary: str | None = Field(None, description="Plain-English sentence, generated in batch")
    citation_ids: list[str] = []
    theme: str | None = None


class OccurrencePage(BaseModel):
    total: int
    offset: int
    limit: int
    items: list[Occurrence]


class FlightLeg(BaseModel):
    date: str
    origin: str | None = None
    destination: str | None = None
    scheduled_departure: str | None = None
    actual_departure: str | None = None
    departure_delay_min: int | None = None
    arrival_delay_min: int | None = None
    cancelled: bool = False
    cancellation_reason: str | None = None
    diverted: bool = False
    tail_number: str | None = None


class FlightHistory(BaseModel):
    flight_number: str
    operator: str | None = None
    legs_found: int
    on_time_pct: float | None = None
    cancelled_pct: float | None = None
    median_departure_delay_min: float | None = None
    worst_delay_min: int | None = None
    routes: list[str] = []
    legs: list[FlightLeg] = []


class Category(BaseModel):
    code: str
    label: str
    occurrences: int


class Theme(BaseModel):
    label: str
    member_count: int | None = None


class Health(BaseModel):
    status: str
    database: str
    airports: int | None = None
    occurrences_in_window: int | None = None
    airport_reports: int | None = None
