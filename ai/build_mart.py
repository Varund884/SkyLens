"""Per-airport report payloads -> mart_airport_report.

Everything the airport page needs, computed once here and stored as JSON, so
the website runs one indexed lookup per airport and never computes at request
time (and never calls a model at request time).

Each payload holds:
  identity        ident, name, municipality, country, type, coordinates
  counts          occurrences in the 12-month window, accidents, fatalities
  rate            per 10,000 movements, with the denominator's source, or null
                  when no official movement count exists for that airport
  trend           occurrences per month with a 3-month rolling average
  change          rate in the last 6 months vs the first 6
  categories      CICTT breakdown, excluding 'Other', flagged when predicted
  themes          top 3 themes (NTSB text only; Canadian records have no text)
  seasonality     month x hour-of-day grid
  peers           median rate for airports of the same type with a denominator
  operations      US only: BTS flights, on-time and cancellation stats
  summary         2-3 generated sentences drawn from this airport's own
                  plain-language summaries (temperature 0, no safety ratings)

    python ai/build_mart.py             # build and write
    python ai/build_mart.py --no-text   # skip the generated summaries
    python ai/build_mart.py --dry-run   # print one payload, write nothing
"""
import argparse
import json
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from aicommon import PRICE_CHAT_IN, PRICE_CHAT_OUT, ROOT, chat_deployment, openai_client
from db import get_connection

MIN_OCCURRENCES = 5
WORKERS = 3
CACHE = ROOT / "data" / "staged" / "mart_summary_cache.json"
SYSTEM = ("You write short factual notes about airports for a public safety dashboard. "
          "Given counts and example occurrence summaries for ONE airport, write 2-3 sentences "
          "describing what kinds of events were reported there in the last twelve months. "
          "Use only the information given. Do not rate safety. Do not speculate about causes. "
          "Do not compare with other airports. Do not give advice.")

OCC_SQL = """
SELECT o.airport_key, o.date_key, o.occurrence_time_utc, o.category_key, o.theme_key,
       o.occurrence_type, o.severity_tier, o.fatalities, o.aircraft_count,
       o.category_source, o.narrative_plain, a.name
FROM v_occurrence_analysis o
JOIN dim_source_authority a ON a.authority_key = o.authority_key
WHERE o.airport_key IS NOT NULL
"""
MOVE_SQL = "SELECT airport_key, date_key, movement_count FROM fact_airport_movements"
AIRPORT_SQL = ("SELECT airport_key, ident, name, municipality, iso_country, airport_type, "
               "latitude, longitude, is_closed FROM dim_airport")
FLIGHT_SQL = """
SELECT origin_airport_key AS airport_key, COUNT(*) AS flights,
       SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END) AS cancelled,
       SUM(CASE WHEN dep_delay_min > 15 THEN 1 ELSE 0 END) AS delayed_over_15,
       AVG(CAST(dep_delay_min AS FLOAT)) AS avg_dep_delay_min
FROM fact_flight_performance
GROUP BY origin_airport_key
"""


def frame(cur, sql, cols) -> pd.DataFrame:
    cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=cols)


def load(conn):
    cur = conn.cursor()
    occ = frame(cur, OCC_SQL, ["airport_key", "date_key", "time", "category_key", "theme_key",
                               "occurrence_type", "severity_tier", "fatalities", "aircraft_count",
                               "category_source", "narrative", "authority"])
    mov = frame(cur, MOVE_SQL, ["airport_key", "date_key", "movement_count"])
    air = frame(cur, AIRPORT_SQL, ["airport_key", "ident", "name", "municipality", "iso_country",
                                   "airport_type", "latitude", "longitude", "is_closed"])
    cat = frame(cur, "SELECT category_key, cictt_code, cictt_label, exclude_from_charts FROM dim_category",
                ["category_key", "code", "label", "exclude"])
    thm = frame(cur, "SELECT theme_key, label FROM dim_theme", ["theme_key", "label"])
    # MIN() rejects a bit column in SQL Server, hence the CAST.
    src = frame(cur, "SELECT airport_key, MIN(source) AS source, MAX(CAST(is_estimated AS INT)) AS est "
                     "FROM fact_airport_movements GROUP BY airport_key",
                ["airport_key", "movement_source", "is_estimated"])
    fl = frame(cur, FLIGHT_SQL, ["airport_key", "flights", "cancelled", "delayed_over_15", "avg_dep_delay_min"])
    return occ, mov, air, cat, thm, src, fl


def month(date_key) -> str:
    s = str(int(date_key))
    return f"{s[:4]}-{s[4:6]}"


def build_payloads(occ, mov, air, cat, thm, fl, src):
    """One payload per airport with at least MIN_OCCURRENCES occurrences."""
    occ = occ.copy()
    # Canadian service reports (no aircraft involved) are excluded from counts and rates.
    occ = occ[(occ["authority"] != "Transport Canada") | (occ["aircraft_count"].fillna(0) > 0)]
    occ["month"] = occ["date_key"].map(month)
    occ["hour"] = occ["time"].map(lambda t: t.hour if hasattr(t, "hour") else None)
    cat_label = cat.set_index("category_key")[["code", "label", "exclude"]].to_dict("index")
    theme_label = thm.set_index("theme_key")["label"].to_dict()
    air_by_key = air.set_index("airport_key")

    moves = mov.groupby("airport_key")["movement_count"].sum()
    months = sorted({month(d) for d in mov["date_key"]}) or sorted(occ["month"].unique())
    first_half, second_half = set(months[:6]), set(months[6:])
    mov_half = mov.assign(m=mov["date_key"].map(month))
    mov_first = mov_half[mov_half["m"].isin(first_half)].groupby("airport_key")["movement_count"].sum()
    mov_second = mov_half[mov_half["m"].isin(second_half)].groupby("airport_key")["movement_count"].sum()
    flights = fl.set_index("airport_key")
    sources = src.set_index("airport_key")

    # Any airport with enough occurrences gets a report. US airports rarely
    # reach that bar (the NTSB records only accidents and serious incidents,
    # ~1,200 a year nationwide), so airports with airline traffic data also get
    # one: their page is worth showing for operations even with few events.
    counts = occ.groupby("airport_key").size()
    keep = counts[counts >= MIN_OCCURRENCES].index.union(fl["airport_key"])
    rate_by_key = {}
    payloads = {}

    for key in keep:
        if key not in air_by_key.index:
            continue
        a = air_by_key.loc[key]
        d = occ[occ["airport_key"] == key]
        if len(d) < MIN_OCCURRENCES and key not in flights.index:
            continue
        total_moves = int(moves.get(key, 0))
        rate = round(len(d) / total_moves * 10000, 2) if total_moves and len(d) else None
        rate_by_key[key] = rate

        by_month = d.groupby("month").size().reindex(months, fill_value=0)
        rolling = by_month.rolling(3, min_periods=1).mean().round(2)
        cats = Counter()
        predicted = 0
        for ck, cs in zip(d["category_key"], d["category_source"]):
            if pd.isna(ck) or cat_label.get(ck, {}).get("exclude"):
                continue
            cats[cat_label[ck]["code"]] += 1
            predicted += cs == "model"
        themes = Counter(theme_label[t] for t in d["theme_key"] if t in theme_label)
        grid = (d.dropna(subset=["hour"]).groupby(["month", "hour"]).size()
                .reset_index(name="n").to_dict("records"))

        first_n = int(by_month.reindex(sorted(first_half)).sum())
        second_n = int(by_month.reindex(sorted(second_half)).sum())
        mf, ms = int(mov_first.get(key, 0)), int(mov_second.get(key, 0))
        change = None
        if mf and ms and len(d):
            r1, r2 = first_n / mf * 10000, second_n / ms * 10000
            change = round((r2 - r1) / r1 * 100, 1) if r1 else None

        payload = {
            "ident": a["ident"], "name": a["name"], "municipality": a["municipality"],
            "country": a["iso_country"], "airport_type": a["airport_type"],
            "latitude": float(a["latitude"]), "longitude": float(a["longitude"]),
            "occurrences": int(len(d)),
            "accidents": int((d["occurrence_type"].fillna("") == "Accident").sum()),
            "fatalities": int(d["fatalities"].fillna(0).sum()),
            "severity": d["severity_tier"].value_counts().to_dict(),
            "movements": total_moves or None,
            "movement_source": (sources.loc[key, "movement_source"] if key in sources.index else None),
            "movement_is_estimated": (bool(sources.loc[key, "is_estimated"]) if key in sources.index else None),
            "rate_per_10k": rate,
            "rate_change_pct_h2_vs_h1": change,
            "trend": [{"month": m, "occurrences": int(by_month[m]), "rolling_3m": float(rolling[m])}
                      for m in months],
            "categories": [{"code": c, "occurrences": n} for c, n in cats.most_common()],
            "categories_predicted": int(predicted),
            "themes": [{"label": t, "occurrences": n} for t, n in themes.most_common(3)],
            "seasonality": grid,
        }
        if key in flights.index:
            f = flights.loc[key]
            payload["operations"] = {
                "flights": int(f["flights"]),
                "cancelled_pct": round(float(f["cancelled"]) / float(f["flights"]) * 100, 2),
                "delayed_over_15_pct": round(float(f["delayed_over_15"]) / float(f["flights"]) * 100, 2),
                "avg_departure_delay_min": round(float(f["avg_dep_delay_min"]), 1)
                if pd.notna(f["avg_dep_delay_min"]) else None,
            }
        payloads[key] = payload

    # Peer comparison is per country as well as per size. Canada logs every
    # reportable occurrence (bird sightings, go-arounds, service reports) while
    # the NTSB logs only accidents and serious incidents, so a Canadian rate
    # and a US rate are not the same measurement and must not be compared.
    peers = pd.DataFrame([{"key": k, "type": payloads[k]["airport_type"],
                           "country": payloads[k]["country"], "rate": payloads[k]["rate_per_10k"]}
                          for k in payloads])
    rated = peers[peers["rate"].notna() & (peers["rate"] > 0)]
    med = rated.groupby(["country", "type"])["rate"].median().round(2).to_dict()
    n_peers = rated.groupby(["country", "type"]).size().to_dict()
    for k, p in payloads.items():
        key = (p["country"], p["airport_type"])
        p["peer_median_rate_per_10k"] = med.get(key)
        p["peer_group"] = f"{'Canadian' if p['country'] == 'CA' else 'US'} {p['airport_type'].replace('_', ' ')}s"
        p["peer_count"] = int(n_peers.get(key, 0))
    return payloads, occ


def examples(d, n=8):
    """Empty for an airport with nothing reported; the summary then says so."""
    """The most common distinct plain-language summaries at this airport."""
    texts = [t for t in d["narrative"].dropna() if t.strip()]
    return [t for t, _ in Counter(texts).most_common(n)]


def add_summaries(payloads, occ, client, model):
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    todo = [k for k in payloads if payloads[k]["ident"] not in cache]
    lock, cost, done, failed = threading.Lock(), [0.0], [0], []

    def work(key):
        p = payloads[key]
        ex = examples(occ[occ["airport_key"] == key])
        facts = (f"Airport: {p['name']} ({p['ident']}), {p['municipality']}, {p['country']}\n"
                 f"Occurrences reported in the last 12 months: {p['occurrences']}"
                 + (f" ({p['accidents']} accidents)" if p['accidents'] else "")
                 + (f"\nMost common categories: " + ", ".join(c['code'] for c in p['categories'][:4]) if p['categories'] else "")
                 + ("\nExamples of what was reported:\n" + "\n".join(f"- {t}" for t in ex) if ex
                    else "\nNo occurrence descriptions are available for this airport. Say only that "
                         "few or no occurrences were reported in the period."))
        r = client.chat.completions.create(model=model, temperature=0, max_tokens=140,
                                           messages=[{"role": "system", "content": SYSTEM},
                                                     {"role": "user", "content": facts}])
        return p["ident"], " ".join((r.choices[0].message.content or "").split()), r.usage

    pool = ThreadPoolExecutor(WORKERS)
    try:
        for fut in as_completed([pool.submit(work, k) for k in todo]):
            try:
                ident, text, usage = fut.result()
            except Exception as e:
                failed.append(f"{type(e).__name__}: {str(e)[:100]}")
                continue
            with lock:
                cache[ident] = text
                cost[0] += (usage.prompt_tokens * PRICE_CHAT_IN + usage.completion_tokens * PRICE_CHAT_OUT) / 1e6
                done[0] += 1
                if done[0] % 25 == 0 or done[0] == len(todo):
                    CACHE.write_text(json.dumps(cache))
                    print(f"  wrote {done[0]}/{len(todo)} airport summaries  (${cost[0]:.2f})", flush=True)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        CACHE.write_text(json.dumps(cache))
    for k, p in payloads.items():
        p["summary"] = cache.get(p["ident"])
    if failed:
        print(f"  {len(failed)} airports failed (first: {failed[0]}); run again to retry")


def write(conn, payloads):
    cur = conn.cursor()
    cur.execute("TRUNCATE TABLE mart_airport_report")
    items = list(payloads.items())
    for i in range(0, len(items), 50):
        vals = ",\n".join("({}, N'{}')".format(k, json.dumps(p, default=str).replace("'", "''"))
                          for k, p in items[i:i + 50])
        cur.execute(f"INSERT INTO mart_airport_report (airport_key, payload) VALUES\n{vals}")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM mart_airport_report")
    return cur.fetchone()[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-text", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    conn = get_connection()
    print("loading")
    occ, mov, air, cat, thm, src, fl = load(conn)
    print(f"  {len(occ):,} occurrences at an airport | {len(mov):,} movement days | {len(fl):,} airports with flights")
    payloads, occ2 = build_payloads(occ, mov, air, cat, thm, fl, src)
    rated = sum(1 for p in payloads.values() if p["rate_per_10k"] is not None)
    print(f"airports with >= {MIN_OCCURRENCES} occurrences: {len(payloads)} ({rated} with a rate)")
    if a.dry_run:
        k = max(payloads, key=lambda k: payloads[k]["occurrences"])
        print(json.dumps(payloads[k], indent=2, default=str)[:2500])
        return
    if not a.no_text:
        add_summaries(payloads, occ2, openai_client(), chat_deployment())
    n = write(conn, payloads)
    print(f"mart_airport_report: {n} airports written")
    busiest = sorted(payloads.values(), key=lambda p: -p["occurrences"])[:5]
    for p in busiest:
        print(f"  {p['ident']}: {p['occurrences']} occurrences, rate {p['rate_per_10k']}, "
              f"peer median {p['peer_median_rate_per_10k']}")
        if p.get("summary"):
            print(f"      {p['summary'][:160]}")


if __name__ == "__main__":
    main()
