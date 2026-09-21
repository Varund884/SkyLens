"""Database access for the API: one shared connection, retried, plus small caches.

Azure SQL serverless auto-pauses, so the first query after a quiet period has
to wait for it to wake. A single connection is kept open and re-opened when the
driver reports it has gone away; queries are serialised with a lock because
pymssql connections are not thread-safe.

Read-only: the API never writes. Every value it serves was computed in batch by
the etl/ and ai/ scripts.
"""
import os
import sys
import threading
import time

import pymssql
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "etl"))
load_dotenv()

_lock = threading.Lock()
_conn = None
CACHE_SECONDS = 300


def _connect():
    from db import get_connection          # retries while the database wakes
    return get_connection(quiet=True)


def query(sql: str, params: tuple = ()) -> list[dict]:
    """Run a read query and return rows as dictionaries."""
    global _conn
    with _lock:
        for attempt in range(2):
            try:
                if _conn is None:
                    _conn = _connect()
                cur = _conn.cursor(as_dict=True)
                cur.execute(sql, params)
                return cur.fetchall()
            except Exception:
                _conn = None                # dropped connection: reconnect once
                if attempt:
                    raise
                time.sleep(1)
    return []


_cache: dict[tuple, tuple[float, list]] = {}


def cached_query(sql: str, params: tuple = ()) -> list[dict]:
    """Same, but remembers the answer for CACHE_SECONDS.

    The data only changes when the batch jobs run, so repeated requests for the
    same airport should not hit the database at all.
    """
    key = (sql, params)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    rows = query(sql, params)
    _cache[key] = (time.time(), rows)
    return rows


def clear_cache():
    _cache.clear()
