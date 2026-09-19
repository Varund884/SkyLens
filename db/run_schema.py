"""Run a SQL file against Azure SQL, splitting on GO batch separators.

Usage:
    python db/run_schema.py                     # runs db/schema.sql
    python db/run_schema.py db/migrate_001.sql  # runs a migration

All SQL files in db/ are written to be idempotent, so re-running is safe.
"""
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "etl"))
from db import get_connection  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "db/schema.sql"
with open(path, "r", encoding="utf-8") as f:
    sql = f.read()

# GO is a client-side batch separator, not T-SQL; split on it.
batches = [b.strip() for b in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE)]
batches = [b for b in batches if b]

conn = get_connection()
cur = conn.cursor()
print(f"running {path} ({len(batches)} batches)")

for i, batch in enumerate(batches, 1):
    try:
        cur.execute(batch)
        conn.commit()
        print(f"  batch {i}/{len(batches)} ok")
    except Exception as e:
        print(f"  batch {i}/{len(batches)} FAILED: {e}")
        print(batch[:300])
        raise

cur.execute("""
    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME
""")
tables = [r[0] for r in cur.fetchall()]
print(f"\ntables ({len(tables)}): {', '.join(tables)}")
cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS")
print("views:", [r[0] for r in cur.fetchall()])
conn.close()
