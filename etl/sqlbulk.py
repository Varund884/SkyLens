"""Fast multi-row inserts for Azure SQL over pymssql.

pymssql's executemany sends one round trip per row, which is hopeless for
millions of rows over a home connection. This packs up to 1,000 rows (SQL
Server's limit for a VALUES list) into each INSERT as escaped literals.

All values come from our own staged files, and every string is escaped, so
building literals is safe here.
"""
import datetime as dt
import math
import time

import pandas as pd

MAX_ROWS = 1000


def literal(v) -> str:
    if v is None or v is pd.NA or v is pd.NaT:
        return "NULL"
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return "NULL"
        return repr(v)
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if hasattr(v, "item"):                      # numpy scalars
        return literal(v.item())
    if isinstance(v, (dt.date, dt.datetime)):
        return "'" + v.isoformat() + "'"
    s = str(v).replace("\x00", "")
    return "N'" + s.replace("'", "''") + "'"


def insert_statements(table: str, columns, df: pd.DataFrame, batch: int = MAX_ROWS):
    """Yield (n_rows, sql) for df[columns] in batches."""
    assert batch <= MAX_ROWS
    cols = ", ".join(columns)
    data = df[list(columns)].astype(object).where(df[list(columns)].notna(), None)
    rows = data.itertuples(index=False, name=None)
    buf = []
    for r in rows:
        buf.append("(" + ", ".join(literal(v) for v in r) + ")")
        if len(buf) == batch:
            yield len(buf), f"INSERT INTO {table} ({cols}) VALUES\n" + ",\n".join(buf)
            buf = []
    if buf:
        yield len(buf), f"INSERT INTO {table} ({cols}) VALUES\n" + ",\n".join(buf)


def bulk_insert(conn, table: str, columns, df: pd.DataFrame, label: str = "", batch: int = MAX_ROWS) -> int:
    """Insert df[columns] into table, committing per batch. Returns rows inserted."""
    cur = conn.cursor()
    total, n = 0, len(df)
    start = time.time()
    for k, sql in insert_statements(table, columns, df, batch):
        cur.execute(sql)
        conn.commit()
        total += k
        rate = total / max(time.time() - start, 1e-6)
        eta = (n - total) / rate if rate else 0
        print(f"  {label or table}: {total:,}/{n:,}  ({rate:,.0f} rows/s, ~{eta/60:.1f} min left)   ", end="\r")
    print(f"  {label or table}: {total:,} rows in {time.time() - start:,.0f}s" + " " * 30)
    return total


def date_key(s: pd.Series) -> pd.Series:
    """date -> yyyymmdd int (matches dim_date.date_key)."""
    d = pd.to_datetime(s, errors="coerce")
    return (d.dt.year * 10000 + d.dt.month * 100 + d.dt.day).astype("Int64")
