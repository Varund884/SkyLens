"""Deploy db/schema.sql to Azure SQL. Idempotent — safe to re-run."""
import os
import re
import pymssql
from dotenv import load_dotenv

load_dotenv()

with open("db/schema.sql", "r", encoding="utf-8") as f:
    sql = f.read()

# Azure SQL does not accept GO as a statement; it is a client-side batch separator.
batches = [b.strip() for b in re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE)]
batches = [b for b in batches if b]

conn = pymssql.connect(
    server=os.environ["SQL_SERVER"],
    user=os.environ["SQL_USER"],
    password=os.environ["SQL_PASSWORD"],
    database=os.environ["SQL_DATABASE"],
)
cur = conn.cursor()

for i, batch in enumerate(batches, 1):
    try:
        cur.execute(batch)
        conn.commit()
        print(f"batch {i}/{len(batches)} ok")
    except Exception as e:
        print(f"batch {i}/{len(batches)} FAILED: {e}")
        print(batch[:300])
        raise

cur.execute("""
    SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_TYPE='BASE TABLE' ORDER BY TABLE_NAME
""")
tables = [r[0] for r in cur.fetchall()]
print(f"\ntables ({len(tables)}):")
for t in tables:
    print("  ", t)

cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.VIEWS")
print("views:", [r[0] for r in cur.fetchall()])

conn.close()