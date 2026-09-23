"""Shared test setup.

These tests never touch Azure SQL. The API reads the database through exactly
two functions, `query` and `cached_query`, so replacing those with a fake is
enough to exercise every endpoint — the SQL each one builds, the parameters it
binds, and the shape it returns. That keeps the suite fast, deterministic and
runnable in CI with no credentials and no firewall rule.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeDb:
    """Returns canned rows for whichever SQL fragment matches, and records the
    calls so a test can assert on the SQL and the bound parameters."""

    def __init__(self):
        self._rules: list[tuple[str, object]] = []
        self.calls: list[tuple[str, tuple]] = []

    def on(self, fragment: str, rows):
        """Answer any query containing `fragment` with `rows` (or rows(params))."""
        self._rules.append((fragment, rows))
        return self

    def fail(self, exc: Exception):
        self._rules.append(("", exc))
        return self

    def __call__(self, sql: str, params: tuple = ()):
        self.calls.append((sql, params))
        for fragment, rows in self._rules:
            if fragment in sql:
                if isinstance(rows, Exception):
                    raise rows
                return rows(params) if callable(rows) else rows
        return []

    @property
    def last_sql(self) -> str:
        return self.calls[-1][0]

    @property
    def last_params(self) -> tuple:
        return self.calls[-1][1]

    def sql_containing(self, fragment: str) -> str:
        return next(sql for sql, _ in self.calls if fragment in sql)


@pytest.fixture
def db(monkeypatch):
    """Point both database helpers at one fake."""
    from api import main

    fake = FakeDb()
    monkeypatch.setattr(main, "query", fake)
    monkeypatch.setattr(main, "cached_query", fake)
    return fake


@pytest.fixture
def client():
    """The API over HTTP, so query defaults, validation and status codes are
    exercised the same way a browser would exercise them."""
    from fastapi.testclient import TestClient

    from api.main import app

    with TestClient(app) as c:
        yield c
