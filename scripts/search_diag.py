"""Ask Azure AI Search directly what is wrong with the index. Prints no keys.

    python scripts/search_diag.py
"""
import json
import os
import sys

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai"))
load_dotenv()

ENDPOINT = os.environ["AZURE_SEARCH_ENDPOINT"].rstrip("/")
HEAD = {"api-key": os.environ["AZURE_SEARCH_KEY"], "Content-Type": "application/json"}
INDEX = "regulations"


CLEANUP = "--cleanup" in sys.argv


def show(label, r):
    print(f"\n{label}: HTTP {r.status_code}")
    try:
        body = r.json()
    except Exception:
        print("  " + r.text[:500])
        return None
    print("  " + json.dumps(body)[:900])
    return body


if CLEANUP:
    for name in ("diag-test", "diag-plain"):
        show(f"delete {name}",
             requests.delete(f"{ENDPOINT}/indexes/{name}?api-version=2026-04-01", headers=HEAD, timeout=60))
    sys.exit()

for version in ("2026-04-01", "2025-09-01", "2024-07-01"):
    show(f"list indexes (api-version {version})",
         requests.get(f"{ENDPOINT}/indexes?api-version={version}&$select=name&$top=50", headers=HEAD, timeout=60))

show("get 'regulations'", requests.get(f"{ENDPOINT}/indexes/{INDEX}?api-version=2026-04-01", headers=HEAD, timeout=60))

body = {
    "name": "diag-test",
    "fields": [
        {"name": "chunk_id", "type": "Edm.String", "key": True},
        {"name": "text", "type": "Edm.String", "searchable": True},
        {"name": "embedding", "type": "Collection(Edm.Single)", "searchable": True, "retrievable": False,
         "dimensions": 1536, "vectorSearchProfile": "hnsw-profile"},
    ],
    "vectorSearch": {"algorithms": [{"name": "hnsw", "kind": "hnsw"}],
                     "profiles": [{"name": "hnsw-profile", "algorithm": "hnsw"}]},
}
show("create a tiny test index (vector)",
     requests.put(f"{ENDPOINT}/indexes/diag-test?api-version=2026-04-01", headers=HEAD, json=body, timeout=120))
show("create a tiny test index (no vector)",
     requests.put(f"{ENDPOINT}/indexes/diag-plain?api-version=2026-04-01", headers=HEAD,
                  json={"name": "diag-plain", "fields": body["fields"][:2]}, timeout=120))
