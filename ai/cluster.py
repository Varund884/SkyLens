"""Group NTSB occurrences into themes: k-means on embeddings, labelled by the chat model.

  1. Load every embedding written by ai/embed.py.
  2. Fit k-means (k=12) on the 3,000 historical corpus rows only, so themes
     describe long-run patterns, then assign every embedded row (including the
     in-window ones) to its nearest theme.
  3. For each theme, send the 5 texts closest to its centre to the chat model
     (temperature 0) for a 3-6 word label.
  4. Rewrite dim_theme and fact_occurrence.theme_key (safe to re-run).

growth_rate compares a theme's share of in-window occurrences with its share
of the historical corpus: +0.5 means it is 50% more common in the last twelve
months than in 2022-2024. It is descriptive, not a statistical test.

    python ai/cluster.py            # cluster, label, write to SQL, write docs/themes.md
    python ai/cluster.py --dry-run  # cluster and print, no model calls, no writes
"""
import argparse
import re

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from aicommon import PRICE_CHAT_IN, PRICE_CHAT_OUT, ROOT, chat_deployment, from_bytes, openai_client
from db import get_connection

K = 12
SEED = 42
K_CHECK = (8, 10, 12, 14, 16)
CAVEAT = ('**Caveat on "Change in share":** only 2% of fatal and 61% of non-fatal NTSB occurrences in the last twelve months had a published probable cause when the data was downloaded, because final reports on serious accidents take a year or more. Last-twelve-month themes therefore lean toward simple, quickly closed accidents, and themes typical of longer investigations (fuel exhaustion, undetermined power loss) look rarer than they are. Treat the change column as descriptive only.')
PROMPT = ("Given these aviation occurrence summaries, output a short 3-6 word label "
          "describing what they have in common. Output only the label.")


def load(conn) -> tuple[pd.DataFrame, np.ndarray]:
    cur = conn.cursor()
    cur.execute("SELECT occurrence_key, CAST(in_analysis_window AS INT), source_text, embedding "
                "FROM fact_occurrence WHERE embedding IS NOT NULL ORDER BY occurrence_key")
    rows = cur.fetchall()
    d = pd.DataFrame([r[:3] for r in rows], columns=["occurrence_key", "in_window", "text"])
    X = np.vstack([from_bytes(r[3]) for r in rows]).astype("float64")
    X /= np.linalg.norm(X, axis=1, keepdims=True)        # unit length: k-means ~ cosine
    return d, X


def fit(d, X):
    corpus = (d["in_window"] == 0).to_numpy()
    sil = {k: silhouette_score(X[corpus], KMeans(k, random_state=SEED, n_init=10).fit_predict(X[corpus]),
                               metric="cosine") for k in K_CHECK}
    km = KMeans(K, random_state=SEED, n_init=10).fit(X[corpus])
    d = d.assign(cluster=km.predict(X), dist=np.linalg.norm(X - km.cluster_centers_[km.predict(X)], axis=1))
    return d, km, sil


def clean_label(s: str) -> str:
    s = s.strip().splitlines()[0].strip()
    s = re.sub(r"^(label|theme)\s*:\s*", "", s, flags=re.I)
    return s.strip().strip("\"'*`\u201c\u201d").rstrip(".").strip()[:150]


def label_themes(d, client, model):
    labels, tokens_in, tokens_out = {}, 0, 0
    for c in sorted(d["cluster"].unique()):
        core = d[(d["cluster"] == c) & (d["in_window"] == 0)].nsmallest(5, "dist")["text"]
        msgs = [{"role": "system", "content": PROMPT},
                {"role": "user", "content": "\n".join(f"- {t}" for t in core)}]
        if labels:
            msgs[1]["content"] += "\n\nThe label must differ from these existing labels: " + "; ".join(labels.values())
        r = client.chat.completions.create(model=model, messages=msgs, temperature=0, max_tokens=20)
        labels[c] = clean_label(r.choices[0].message.content)
        tokens_in += r.usage.prompt_tokens
        tokens_out += r.usage.completion_tokens
    cost = tokens_in * PRICE_CHAT_IN / 1e6 + tokens_out * PRICE_CHAT_OUT / 1e6
    return labels, cost


def summarize(d):
    corpus_share = d[d["in_window"] == 0]["cluster"].value_counts(normalize=True)
    window_share = d[d["in_window"] == 1]["cluster"].value_counts(normalize=True)
    t = pd.DataFrame({"corpus_n": d[d["in_window"] == 0]["cluster"].value_counts(),
                      "window_n": d[d["in_window"] == 1]["cluster"].value_counts()}).fillna(0).astype(int)
    t["member_count"] = t["corpus_n"] + t["window_n"]
    t["growth_rate"] = (window_share.reindex(t.index).fillna(0) / corpus_share.reindex(t.index)) - 1
    return t.sort_index()


def write_sql(conn, d, t, labels):
    cur = conn.cursor()
    cur.execute("UPDATE fact_occurrence SET theme_key = NULL WHERE theme_key IS NOT NULL")
    cur.execute("TRUNCATE TABLE dim_theme")
    vals = ",\n".join(
        f"({c + 1}, N'{labels[c].replace(chr(39), chr(39) * 2)}', NULL, {int(r.member_count)}, {r.growth_rate:.4f})"
        for c, r in t.iterrows())
    cur.execute("SET IDENTITY_INSERT dim_theme ON;\n"
                "INSERT INTO dim_theme (theme_key, label, airport_key, member_count, growth_rate) VALUES\n"
                f"{vals};\nSET IDENTITY_INSERT dim_theme OFF;")
    for i in range(0, len(d), 1000):
        chunk = d.iloc[i:i + 1000]
        v = ",\n".join(f"({int(k)}, {int(c) + 1})" for k, c in zip(chunk["occurrence_key"], chunk["cluster"]))
        cur.execute("UPDATE f SET theme_key = v.t\nFROM fact_occurrence f\n"
                    f"JOIN (VALUES\n{v}\n) AS v(k, t) ON f.occurrence_key = v.k")
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM fact_occurrence WHERE theme_key IS NOT NULL")
    n = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM dim_theme")
    return n, cur.fetchone()[0]


def write_doc(d, t, labels, sil):
    lines = ["# Occurrence themes", "",
             "Generated by `ai/cluster.py`. k-means (k=12, cosine on text-embedding-3-small",
             "vectors) fitted on the 3,000 most recent NTSB corpus occurrences (2022-2024),",
             "then applied to in-window occurrences. Labels written by gpt-4.1-mini from the",
             "5 probable-cause texts nearest each theme's centre.", "",
             "Silhouette (cosine) by k, for reference; low values are normal for short texts",
             "and mean themes overlap rather than separate cleanly:", "",
             "| k | silhouette |", "|---|---|"]
    lines += [f"| {k} | {s:.3f} |" for k, s in sil.items()]
    lines += ["", CAVEAT]
    lines += ["", "| # | Theme | Corpus | Last 12 months | Change in share | Example |",
              "|---|---|---|---|---|---|"]
    for c, r in t.sort_values("member_count", ascending=False).iterrows():
        ex = d[d["cluster"] == c].nsmallest(1, "dist")["text"].iloc[0].replace("|", "/")
        lines.append(f"| {c + 1} | {labels[c]} | {int(r.corpus_n)} | {int(r.window_n)} | {r.growth_rate:+.0%} | {ex} |")
    (ROOT / "docs" / "themes.md").write_text("\n".join(lines) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    conn = get_connection()
    d, X = load(conn)
    print(f"loaded {len(d):,} embeddings ({int((d['in_window'] == 1).sum())} in window)")
    d, km, sil = fit(d, X)
    print("silhouette by k: " + ", ".join(f"{k}={s:.3f}" for k, s in sil.items()))
    t = summarize(d)
    if a.dry_run:
        for c, r in t.iterrows():
            ex = d[d["cluster"] == c].nsmallest(1, "dist")["text"].iloc[0][:90]
            print(f"  theme {c + 1:>2}: {int(r.corpus_n):>4} corpus, {int(r.window_n):>3} window, {r.growth_rate:+.0%} | {ex}")
        return
    labels, cost = label_themes(d, openai_client(), chat_deployment())
    n, themes = write_sql(conn, d, t, labels)
    write_doc(d, t, labels, sil)
    for c, r in t.sort_values("member_count", ascending=False).iterrows():
        print(f"  {c + 1:>2}. {labels[c]:<45} {int(r.corpus_n):>4} corpus  {int(r.window_n):>3} window  {r.growth_rate:+.0%}")
    print(f"done: {themes} themes, {n:,} occurrences tagged (expected {len(d):,}); "
          f"labelling cost ${cost:.4f}; wrote docs/themes.md")


if __name__ == "__main__":
    main()
