"""Aviation reference documents -> Azure AI Search index "regulations".

  1. Read each PDF in data/raw/docs with Azure Document Intelligence
     (prebuilt-layout), which returns paragraphs with their role, so section
     headings survive. The free F0 tier reads only two pages per request, so
     each PDF is split into 2-page pieces and sent piece by piece; the layout
     result is cached in data/staged/docs_layout.json for re-runs.
  2. Split the text into ~500-token chunks with 50 tokens of overlap, keeping
     source document, page number and the heading each chunk sits under.
  3. Embed every chunk with text-embedding-3-small.
  4. Create the index (BM25 text + HNSW vectors) and upload. Retrieval is
     hybrid: keyword and vector together. No semantic ranker: not on the Free
     tier.

These passages are what grounds the plain-language summaries: without the
Pilot/Controller Glossary, a CADORS record is just event codes.

    python ai/docs.py                     # read, chunk, embed, upload
    python ai/docs.py --no-upload         # read and chunk only, print a preview
    python ai/docs.py --query "go-around" # hybrid search against the live index
"""
import argparse
import io
import json
import os
import re
import time

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
import requests
from pypdf import PdfReader, PdfWriter

from aicommon import (EMBED_DIMS, PRICE_EMBED, ROOT, embed_deployment, openai_client, search_client_args)

DOCS = ROOT / "data" / "raw" / "docs"
CACHE = ROOT / "data" / "staged" / "docs_layout.json"
# The name "regulations" is unusable: after an index of that name was deleted,
# this serverless service kept timing out on any attempt to recreate it, while
# a freshly named index is created instantly.
INDEX = "reference-docs"
SEARCH_API_VERSION = "2026-04-01"
PAGES_PER_CALL = 2          # Document Intelligence free tier limit
CHUNK_TOKENS, OVERLAP_TOKENS = 500, 50
# The glossary is a dictionary: one chunk per term retrieves far better than
# fixed-size windows, which mix a dozen unrelated terms into one passage.
GLOSSARY_STEM = "pilot_controller_glossary"
ENTRY = re.compile(r"^([A-Z][A-Z0-9 /&'()\.\-]{2,60})-+\s+(.+)", re.S)
MIN_ENTRY_WORDS = 6
WORDS_PER_TOKEN = 0.75      # ~4 chars/token for English prose
TITLES = {
    "pilot_controller_glossary": "FAA Pilot/Controller Glossary",
    "ntsb_part830": "NTSB 49 CFR Part 830",
    "tp4044_cadors_manual": "Transport Canada CADORS Manual TP 4044",
    "tsb_report": "TSB aviation investigation report",
}


def layout(path, client) -> list[dict]:
    """Return [{page, role, text}] for one PDF, two pages per request."""
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        reader.decrypt("")
    out = []
    for start in range(0, len(reader.pages), PAGES_PER_CALL):
        writer = PdfWriter()
        for p in reader.pages[start:start + PAGES_PER_CALL]:
            writer.add_page(p)
        buf = io.BytesIO()
        writer.write(buf)
        result = client.begin_analyze_document("prebuilt-layout", document=buf.getvalue()).result()
        for para in result.paragraphs or []:
            page = start + (para.bounding_regions[0].page_number if para.bounding_regions else 1)
            out.append({"page": page, "role": para.role or "", "text": " ".join(para.content.split())})
        print(f"    pages {start + 1}-{min(start + PAGES_PER_CALL, len(reader.pages))} read", flush=True)
    return out


def read_all(force=False) -> dict:
    cache = json.loads(CACHE.read_text()) if CACHE.exists() and not force else {}
    pdfs = sorted(DOCS.glob("*.pdf"))
    assert pdfs, f"no PDFs in {DOCS}"
    todo = [p for p in pdfs if p.stem not in cache]
    if todo:
        client = DocumentAnalysisClient(*search_client_args("DOCINTEL"))
        for p in todo:
            print(f"  {p.name}")
            cache[p.stem] = layout(p, client)
            CACHE.write_text(json.dumps(cache))
    print(f"  layout ready for {len(cache)} documents "
          f"({sum(len(v) for v in cache.values()):,} paragraphs)")
    return cache


def glossary_chunks(stem: str, paras: list[dict], titles) -> list[dict]:
    """One chunk per glossary term; cross-reference stubs are dropped."""
    out, current = [], None
    for para in paras:
        if para["role"] in ("pageHeader", "pageFooter", "pageNumber"):
            continue
        m = ENTRY.match(para["text"])
        if m:
            if current:
                out.append(current)
            term, body = m.group(1).strip(), m.group(2).strip()
            current = {"source_document": titles, "page_number": para["page"],
                       "section": term, "text": f"{term}: {body}"}
        elif current:
            current["text"] += " " + para["text"]
    if current:
        out.append(current)
    out = [c for c in out if len(c["text"].split()) >= MIN_ENTRY_WORDS]
    for i, c in enumerate(out):
        c["chunk_id"] = f"{stem}-{i:04d}"
    return out


def chunks(cache: dict) -> list[dict]:
    """Split paragraphs into overlapping chunks, one section heading each."""
    size = int(CHUNK_TOKENS * WORDS_PER_TOKEN)
    step = int((CHUNK_TOKENS - OVERLAP_TOKENS) * WORDS_PER_TOKEN)
    out = []
    for stem, paras in cache.items():
        if stem == GLOSSARY_STEM:
            out += glossary_chunks(stem, paras, TITLES.get(stem, stem))
            continue
        section = ""
        buf = []          # (word, page) so a chunk knows the page it starts on
        def flush(words):
            if not words:
                return
            text = " ".join(w for w, _ in words)
            out.append({"chunk_id": f"{stem}-{len(out):04d}",
                        "source_document": TITLES.get(stem, stem),
                        "page_number": words[0][1], "section": section or "(document body)",
                        "text": text})
        for para in paras:
            if para["role"] in ("title", "sectionHeading"):
                flush(buf)
                buf, section = [], para["text"][:150]
                continue
            if para["role"] in ("pageHeader", "pageFooter", "pageNumber"):
                continue
            buf += [(w, para["page"]) for w in para["text"].split()]
            while len(buf) >= size:
                flush(buf[:size])
                buf = buf[step:]
        flush(buf)
    return [c for c in out if len(c["text"].split()) >= MIN_ENTRY_WORDS]   # drop stubs


EMBED_CACHE = ROOT / "data" / "staged" / "doc_embed_cache.json"


def embed(chunks_, client, model):
    cache = json.loads(EMBED_CACHE.read_text()) if EMBED_CACHE.exists() else {}
    for c in chunks_:
        if c["text"] in cache:
            c["embedding"] = cache[c["text"]]
    todo = [c for c in chunks_ if "embedding" not in c]
    tokens = 0
    for i in range(0, len(todo), 50):
        part = todo[i:i + 50]
        r = client.embeddings.create(model=model, input=[c["text"] for c in part])
        for c, e in zip(part, sorted(r.data, key=lambda e: e.index)):
            c["embedding"] = e.embedding
        tokens += r.usage.total_tokens
        for c in part:
            cache[c["text"]] = c["embedding"]
    EMBED_CACHE.write_text(json.dumps(cache))
    return tokens


INDEX_DEFINITION = {
    "name": INDEX,
    "fields": [
        {"name": "chunk_id", "type": "Edm.String", "key": True},
        {"name": "source_document", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "page_number", "type": "Edm.Int32", "filterable": True},
        {"name": "section", "type": "Edm.String", "searchable": True},
        {"name": "text", "type": "Edm.String", "searchable": True},
        {"name": "embedding", "type": "Collection(Edm.Single)", "searchable": True, "retrievable": False,
         "dimensions": EMBED_DIMS, "vectorSearchProfile": "hnsw-profile"},
    ],
    "vectorSearch": {"algorithms": [{"name": "hnsw", "kind": "hnsw"}],
                     "profiles": [{"name": "hnsw-profile", "algorithm": "hnsw"}]},
}


def create_index(recreate=False):
    """Create the index over the REST API.

    The Python SDK's create_or_update_index times out against this Free
    (serverless) service, while the same definition sent as a plain PUT
    succeeds, so the index is defined here as JSON. Everything else (uploading,
    searching) still goes through the SDK.
    """
    endpoint = os.environ["AZURE_SEARCH_ENDPOINT"].rstrip("/")
    head = {"api-key": os.environ["AZURE_SEARCH_KEY"], "Content-Type": "application/json"}
    url = f"{endpoint}/indexes/{INDEX}?api-version={SEARCH_API_VERSION}"
    if recreate:
        requests.delete(url, headers=head, timeout=120)
        time.sleep(10)
    r = requests.put(url, headers=head, json=INDEX_DEFINITION, timeout=180)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"could not create index '{INDEX}': HTTP {r.status_code} {r.text[:300]}")
    print(f"  index '{INDEX}' ready (HTTP {r.status_code})")


def prune(keep_ids):
    """Delete chunks left over from an earlier chunking scheme."""
    endpoint, credential = search_client_args("SEARCH")
    sc = SearchClient(endpoint, INDEX, credential)
    existing = {d["chunk_id"] for d in sc.search(search_text="*", select=["chunk_id"], top=100000)}
    stale = sorted(existing - set(keep_ids))
    for i in range(0, len(stale), 100):
        sc.delete_documents([{"chunk_id": c} for c in stale[i:i + 100]])
    return len(stale)


def upload(chunks_):
    endpoint, credential = search_client_args("SEARCH")
    sc = SearchClient(endpoint, INDEX, credential)      # positional order: endpoint, index, credential
    uploaded, t0 = 0, time.time()
    # Each chunk carries a 1,536-number vector (~30 KB as JSON), so batches stay
    # small: a home upload link is the slow part, not the service.
    for i in range(0, len(chunks_), 25):
        batch = [{k: v for k, v in c.items()} for c in chunks_[i:i + 25]]
        uploaded += sum(r.succeeded for r in sc.upload_documents(batch))
        rate = uploaded / max(time.time() - t0, 1e-9)
        print(f"  uploaded {uploaded}/{len(chunks_)} chunks "
              f"(~{(len(chunks_) - uploaded) / max(rate, 1e-9) / 60:.1f} min left)", flush=True)
    return uploaded


def search(question: str, k: int = 3):
    """Hybrid retrieval: BM25 on the text plus vector similarity, fused by the service."""
    from azure.search.documents.models import VectorizedQuery
    vec = openai_client().embeddings.create(model=embed_deployment(), input=question).data[0].embedding
    endpoint, credential = search_client_args("SEARCH")
    sc = SearchClient(endpoint, INDEX, credential)      # positional order: endpoint, index, credential
    return list(sc.search(search_text=question, top=k,
                          vector_queries=[VectorizedQuery(vector=vec, k_nearest_neighbors=k, fields="embedding")],
                          select=["chunk_id", "source_document", "page_number", "section", "text"]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--no-upload", action="store_true")
    p.add_argument("--reread", action="store_true", help="ignore the cached layout")
    p.add_argument("--query", help="search the existing index instead of building it")
    p.add_argument("--recreate", action="store_true", help="delete the index first (slow on Free tier)")
    a = p.parse_args()

    if a.query:
        for r in search(a.query):
            print(f"\n  score {r['@search.score']:.3f} | {r['source_document']} p{r['page_number']} | {r['section']}")
            print("  " + r["text"][:300] + "...")
        return

    print("document intelligence")
    cache = read_all(force=a.reread)
    cs = chunks(cache)
    per_doc = {}
    for c in cs:
        per_doc[c["source_document"]] = per_doc.get(c["source_document"], 0) + 1
    words = sum(len(c["text"].split()) for c in cs)
    print(f"chunks: {len(cs)} ({words:,} words) | " + ", ".join(f"{k}: {v}" for k, v in per_doc.items()))
    if a.no_upload:
        for c in cs[:3]:
            print(f"\n  [{c['chunk_id']}] {c['source_document']} p{c['page_number']} - {c['section']}\n  {c['text'][:300]}...")
        return
    tokens = embed(cs, openai_client(), embed_deployment())
    print(f"embedded {len(cs)} chunks ({tokens:,} tokens, ${tokens * PRICE_EMBED / 1e6:.4f})")
    create_index(recreate=a.recreate)
    n = upload(cs)
    stale = prune([c["chunk_id"] for c in cs])
    print(f"index '{INDEX}': uploaded {n}/{len(cs)} chunks; removed {stale} stale chunks")


if __name__ == "__main__":
    main()
