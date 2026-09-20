"""Embed NTSB probable-cause text with text-embedding-3-small -> fact_occurrence.embedding.

Which rows:
  - every in-window NTSB occurrence with text (so airport reports can show themes)
  - the 3,000 most recent corpus occurrences (2014-2024), for clustering
CADORS publishes no narrative text, so Canadian rows are not embedded.

Resumable: rows that already have an embedding are skipped, and each batch of
50 is committed as soon as it is written, so a crash loses at most one batch.

    python ai/embed.py            # embed everything still missing
    python ai/embed.py --dry-run  # show what would be embedded and the cost
"""
import argparse
import time

import pandas as pd

from aicommon import PRICE_EMBED, embed_deployment, hex_literal, openai_client, to_bytes
from db import get_connection

CORPUS_ROWS = 3000
BATCH = 50

SELECT = """
SELECT f.occurrence_key, f.date_key, CAST(f.in_analysis_window AS INT),
       f.source_text, CASE WHEN f.embedding IS NULL THEN 0 ELSE 1 END
FROM fact_occurrence f
JOIN dim_source_authority a ON a.authority_key = f.authority_key
WHERE a.name = 'NTSB' AND f.source_text IS NOT NULL AND LEN(f.source_text) > 0
"""


def select_rows(conn) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(SELECT)
    d = pd.DataFrame(cur.fetchall(), columns=["occurrence_key", "date_key", "in_window", "text", "done"])
    window = d[d["in_window"] == 1]
    corpus = (d[d["in_window"] == 0]
              .sort_values(["date_key", "occurrence_key"], ascending=False)
              .head(CORPUS_ROWS))
    return pd.concat([window, corpus], ignore_index=True)


def update_sql(keys, vectors) -> str:
    values = ",\n".join(f"({int(k)}, {hex_literal(to_bytes(v))})" for k, v in zip(keys, vectors))
    return ("UPDATE f SET embedding = v.e\nFROM fact_occurrence f\n"
            f"JOIN (VALUES\n{values}\n) AS v(k, e) ON f.occurrence_key = v.k")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    conn = get_connection()
    rows = select_rows(conn)
    todo = rows[rows["done"] == 0].reset_index(drop=True)
    est_tokens = int(todo["text"].str.len().sum() / 4)
    print(f"selected {len(rows):,} rows ({int((rows['in_window'] == 1).sum()):,} in window, "
          f"{int((rows['in_window'] == 0).sum()):,} corpus) | already embedded {int(rows['done'].sum()):,} "
          f"| to embed {len(todo):,} | ~{est_tokens:,} tokens, ~${est_tokens * PRICE_EMBED / 1e6:.4f}")
    if a.dry_run or todo.empty:
        return

    client, model = openai_client(), embed_deployment()
    cur = conn.cursor()
    tokens, t0, done = 0, time.time(), 0
    for i in range(0, len(todo), BATCH):
        chunk = todo.iloc[i:i + BATCH]
        r = client.embeddings.create(model=model, input=chunk["text"].tolist())
        vectors = [e.embedding for e in sorted(r.data, key=lambda e: e.index)]
        assert len(vectors) == len(chunk)
        tokens += r.usage.total_tokens
        cur.execute(update_sql(chunk["occurrence_key"], vectors))
        conn.commit()
        done += len(chunk)
        if done % 100 < BATCH or done == len(todo):
            rate = done / max(time.time() - t0, 1e-9)
            print(f"  embedded {done:,}/{len(todo):,}  ({rate:.0f} rows/s, "
                  f"{tokens:,} tokens, ${tokens * PRICE_EMBED / 1e6:.4f})", flush=True)

    cur.execute("SELECT COUNT(*) FROM fact_occurrence WHERE embedding IS NOT NULL")
    print(f"done: {cur.fetchone()[0]:,} occurrences now have an embedding "
          f"(expected {len(rows):,}); cost ${tokens * PRICE_EMBED / 1e6:.4f}")


if __name__ == "__main__":
    main()
