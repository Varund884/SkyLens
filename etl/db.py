"""Shared Azure SQL connection helper.

The database is serverless with auto-pause enabled, so the first connection
after a period of inactivity fails with error 40613 while the database wakes.
Every caller retries rather than failing.
"""
import os
import time

import pymssql
from dotenv import load_dotenv

load_dotenv()

_RETRIES = 6
_WAIT_SECONDS = 15


def get_connection(quiet: bool = False):
    """Return a live pymssql connection, waking the database if it is paused."""
    last_error = None
    for attempt in range(1, _RETRIES + 1):
        try:
            conn = pymssql.connect(
                server=os.environ["SQL_SERVER"],
                user=os.environ["SQL_USER"],
                password=os.environ["SQL_PASSWORD"],
                database=os.environ["SQL_DATABASE"],
                login_timeout=60,
                timeout=300,
            )
            if attempt > 1 and not quiet:
                print(f"connected after {attempt} attempts")
            return conn
        except Exception as e:
            last_error = e
            if "40615" in str(e):
                raise RuntimeError(
                    "Azure SQL firewall blocked this computer (error 40615): your IP address is not "
                    "allowed. In the portal open the server > Security > Networking > "
                    "'Add your client IPv4 address' > Save, then run again.") from None
            if attempt < _RETRIES:
                if not quiet:
                    print(f"database waking, retrying in {_WAIT_SECONDS}s "
                          f"({attempt}/{_RETRIES})")
                time.sleep(_WAIT_SECONDS)
    raise RuntimeError(f"could not connect after {_RETRIES} attempts") from last_error


def executemany(conn, sql: str, rows, batch_size: int = 1000, label: str = ""):
    """Insert rows in batches, committing per batch. Returns the row count."""
    cur = conn.cursor()
    total = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i:i + batch_size]
        cur.executemany(sql, chunk)
        conn.commit()
        total += len(chunk)
        print(f"  {label} {total:,}/{len(rows):,}", end="\r")
    print(f"  {label} {total:,} rows inserted    ")
    return total


def truncate(conn, *tables):
    """Truncate tables so loaders are idempotent."""
    cur = conn.cursor()
    for t in tables:
        cur.execute(f"TRUNCATE TABLE {t}")
    conn.commit()
    print("truncated:", ", ".join(tables))


def scalar(conn, sql: str):
    """Run a query and return the first column of the first row."""
    cur = conn.cursor()
    cur.execute(sql)
    row = cur.fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    conn = get_connection()
    print("server:", scalar(conn, "SELECT @@VERSION")[:50])
    print("tables:", scalar(conn,
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE'"))
    conn.close()
    