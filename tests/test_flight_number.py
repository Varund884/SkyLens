"""The flight-number parser.

BTS stores the airline code and the number in separate columns, so "AA100" has
to be split before it can be matched. The awkward cases are real: airline codes
can start with a digit (9E, 5Y), BTS stores numbers without leading zeros, and
a bare number has to stay a number rather than being read as a carrier.
"""
import pytest

from api.main import FLIGHT_NUMBER


def parse(text: str):
    """What the endpoint does with the raw path segment."""
    m = FLIGHT_NUMBER.match(text.upper().replace(" ", ""))
    return None if not m else (m.group(1), str(int(m.group(2))))


@pytest.mark.parametrize("text, expected", [
    ("AA1", ("AA", "1")),
    ("aa1", ("AA", "1")),
    ("AA 100", ("AA", "100")),
    ("AA0100", ("AA", "100")),          # leading zeros dropped: BTS stores 100
    ("9E123", ("9E", "123")),           # carrier code starting with a digit
    ("B61", ("B6", "1")),               # JetBlue
    ("WN1234", ("WN", "1234")),
    ("100", (None, "100")),             # bare number, not carrier "10" + "0"
    ("0001", (None, "1")),
])
def test_accepts(text, expected):
    assert parse(text) == expected


@pytest.mark.parametrize("text", ["", "AAAA1", "AA12345", "!!", "AA"])
def test_rejects(text):
    assert parse(text) is None
