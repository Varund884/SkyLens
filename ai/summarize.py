"""One plain-English sentence per occurrence, grounded in the reference documents.

Two paths, because the sources differ:
  NTSB   has a probable-cause sentence; that text is the input.
  CADORS has no narrative at all, so the input is built from the structured
         fields: occurrence type, event names, phase of flight, damage.

Either way the input is first used to retrieve the 3 closest passages from the
"reference-docs" index (hybrid keyword + vector), and the model may use only those
passages and the report itself. This is what makes retrieval load-bearing
rather than decorative: without the glossary, "Missed approach/Go-around" is
just an event code. The passages used are stored in citation_ids so the site
can show its sources.

Identical inputs are summarised once and reused: 23,285 Canadian occurrences in
the window share 2,564 distinct field combinations, and identical input would
produce identical output at temperature 0.

    python ai/summarize.py --limit 25   # small trial, prints every sentence
    python ai/summarize.py              # everything still missing (resumable)
"""
import argparse
import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from aicommon import (PRICE_CHAT_IN, PRICE_CHAT_OUT, PRICE_EMBED, ROOT, chat_deployment,
                      embed_deployment, openai_client)
from db import get_connection
from docs import search

CACHE = ROOT / "data" / "staged" / "summary_cache.json"
WORKERS = 3
TOP_K = 3
SYSTEM = ("You explain aviation occurrence reports to non-experts. Using ONLY the provided "
          "reference text and the report itself, write ONE sentence in plain English describing "
          "what happened. The report may name the official category it was filed under; say what "
          "that category means in ordinary words rather than ignoring it. Do not speculate about "
          "causes. Do not use jargon. Do not state or imply any safety rating.")

SELECT = """
SELECT f.occurrence_key, a.name, f.occurrence_type, f.event_names, f.phase_of_flight,
       f.damage, f.source_text, f.fatalities, f.injuries, c.cictt_label
FROM fact_occurrence f
JOIN dim_source_authority a ON a.authority_key = f.authority_key
LEFT JOIN dim_category c ON c.category_key = f.category_key
WHERE f.in_analysis_window = 1 AND f.narrative_plain IS NULL
"""


def clean(v) -> str:
    """'' for NULL / NaN / pandas NA, whatever the driver hands back."""
    if v is None:
        return ""
    t = str(v).strip()
    return "" if t in ("<NA>", "NaT", "nan", "None") else t


def model_input(row) -> str | None:
    """Text the model summarises. None when there is nothing to describe."""
    _, authority, occ_type, events, phase, damage, text, fatalities, injuries, category = row
    if clean(authority) == "NTSB":
        if clean(text):
            return clean(text)
        # The NTSB publishes a probable cause only with the final report, which
        # takes a year or more. Until then describe what is known: the type of
        # event, the damage and whether anyone was hurt.
        parts = [clean(v) for v in (occ_type, phase, damage) if clean(v)]
        if clean(fatalities) not in ("", "0"):
            parts.append(f"{clean(fatalities)} fatalities")
        elif clean(injuries) not in ("", "0"):
            parts.append(f"{clean(injuries)} injuries")
        parts.append("investigation not yet complete, no probable cause published")
        if clean(category):
            parts.insert(0, f"Category: {clean(category)}")
        return " | ".join(parts) if clean(occ_type) else None
    # The category is the authority's own classification. Without it the model
    # hedges: a bird strike whose event text is vague came out as "an
    # operational issue occurred", never mentioning the bird.
    parts = [clean(v) for v in (occ_type, events, phase, damage) if clean(v)]
    if clean(category):
        parts.insert(1, f"Category: {clean(category)}")
    return " | ".join(parts) if clean(events) else None


def key_of(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def summarise(client, chat_model, embed_model, text: str):
    passages = search(text, TOP_K)
    refs = "\n\n".join(f"[{p['source_document']}, p{p['page_number']}] {p['text']}" for p in passages)
    r = client.chat.completions.create(
        model=chat_model, temperature=0, max_tokens=90,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": f"Reference text:\n{refs}\n\nReport:\n{text}"}])
    sentence = " ".join((r.choices[0].message.content or "").split())[:1000]
    cites = ",".join(p["chunk_id"] for p in passages)[:200]
    return sentence, cites, r.usage


def write_back(conn, rows):
    """rows: (occurrence_key, sentence, citation_ids)"""
    cur = conn.cursor()
    # Small committed batches: a 500-row statement carries ~100 KB of text, and
    # one stalled round trip on a paused database would otherwise lose the lot.
    for i in range(0, len(rows), 200):
        part = rows[i:i + 200]
        vals = ",\n".join("({}, N'{}', N'{}')".format(k, s.replace("'", "''"), c.replace("'", "''"))
                          for k, s, c in part)
        cur.execute("UPDATE f SET narrative_plain = v.s, citation_ids = v.c\n"
                    f"FROM fact_occurrence f\nJOIN (VALUES\n{vals}\n) AS v(k, s, c) ON f.occurrence_key = v.k")
        conn.commit()
        print(f"  saved {min(i + 200, len(rows)):,}/{len(rows):,} rows to the database", end="\r", flush=True)
    print(" " * 60, end="\r")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, help="only summarise this many distinct inputs")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--refresh", action="store_true",
                   help="rewrite summaries that already exist, reusing the cache (safe to re-run)")
    p.add_argument("--regenerate", action="store_true",
                   help="with --refresh, also discard the cache and call the model again (costs money)")
    a = p.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(SELECT.replace("AND f.narrative_plain IS NULL", "") if (a.refresh or a.regenerate) else SELECT)
    rows = cur.fetchall()
    pairs = [(r[0], model_input(r)) for r in rows]
    usable = [(k, t) for k, t in pairs if t]
    # --refresh alone reuses whatever is cached, so an interrupted run can be
    # resumed for free; only --regenerate pays to call the model again.
    cache = {} if a.regenerate else (json.loads(CACHE.read_text()) if CACHE.exists() else {})
    distinct = {}
    for _, t in usable:
        distinct.setdefault(key_of(t), t)
    pending = [t for h, t in distinct.items() if h not in cache]
    todo = pending[:a.limit] if a.limit else pending
    print(("refreshing all summaries: " if a.refresh else "occurrences needing a summary: ")
          + f"{len(usable):,} of {len(rows):,} "
          f"({len(rows) - len(usable):,} have nothing to describe)")
    print(f"distinct inputs: {len(distinct):,} | already summarised: {len(distinct) - len(pending):,} "
          f"| still missing: {len(pending):,} | doing now: {len(todo):,} "
          f"| estimated cost ${len(todo) * 0.0005:.2f}")
    if a.dry_run or not todo:
        if not a.dry_run and usable:
            pass
        else:
            for t in todo[:5]:
                print("   input:", t[:120])
            return

    client = openai_client()
    chat_model, embed_model = chat_deployment(), embed_deployment()
    lock, cost, done, failed = threading.Lock(), [0.0], [0], []

    def work(text):
        from openai import RateLimitError
        for attempt in range(12):
            try:
                return text, summarise(client, chat_model, embed_model, text)
            except RateLimitError:
                time.sleep(min(10 * (attempt + 1), 60))
        return text, summarise(client, chat_model, embed_model, text)

    pool = ThreadPoolExecutor(WORKERS)
    try:
        for fut in as_completed([pool.submit(work, t) for t in todo]):
            try:
                text, (sentence, cites, usage) = fut.result()
            except Exception as e:
                failed.append(f"{type(e).__name__}: {str(e)[:120]}")
                continue
            with lock:
                cache[key_of(text)] = [sentence, cites]
                cost[0] += (usage.prompt_tokens * PRICE_CHAT_IN + usage.completion_tokens * PRICE_CHAT_OUT) / 1e6
                done[0] += 1
                if done[0] % 25 == 0 or done[0] == len(todo):
                    CACHE.write_text(json.dumps(cache))
                    print(f"  summarised {done[0]}/{len(todo)} distinct inputs  (${cost[0]:.2f})", flush=True)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        CACHE.write_text(json.dumps(cache))

    out = [(k, *cache[key_of(t)]) for k, t in usable if key_of(t) in cache]   # SELECT already excluded rows that have one
    write_back(conn, out)
    cur.execute("SELECT COUNT(*) FROM v_occurrence_analysis WHERE narrative_plain IS NOT NULL")
    print(f"wrote {len(out):,} summaries; {cur.fetchone()[0]:,} occurrences in the window now have one")
    if a.limit:
        for k, s, c in out[:a.limit]:
            print(f"\n  {s}\n    sources: {c}")
    if failed:
        print(f"  {len(failed)} inputs failed (first: {failed[0]}); run again to retry them")


if __name__ == "__main__":
    main()
