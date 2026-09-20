"""Check that every Azure AI service in .env answers. Never prints keys.

    python scripts/check_services.py
"""
import os

from dotenv import load_dotenv

load_dotenv()


def openai_chat():
    from openai import AzureOpenAI
    c = AzureOpenAI(azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                    api_key=os.environ["AZURE_OPENAI_KEY"], api_version="2024-10-21")
    r = c.chat.completions.create(model=os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"], max_tokens=5,
                                  messages=[{"role": "user", "content": "Reply with the word ready."}])
    e = c.embeddings.create(model=os.environ["AZURE_OPENAI_EMBED_DEPLOYMENT"], input="go-around")
    return f"chat says {r.choices[0].message.content.strip()!r}, embedding has {len(e.data[0].embedding)} dims"


def search():
    from azure.core.credentials import AzureKeyCredential
    from azure.search.documents.indexes import SearchIndexClient
    from azure.core.exceptions import ResourceNotFoundError
    c = SearchIndexClient(os.environ["AZURE_SEARCH_ENDPOINT"], AzureKeyCredential(os.environ["AZURE_SEARCH_KEY"]))
    # Serverless (Free) services refuse the unpaged "list indexes" call, so probe
    # a name that does not exist: 404 proves the endpoint and key are both valid.
    try:
        c.get_index("connection-check")
    except ResourceNotFoundError:
        pass
    try:
        st = c.get_service_statistics()
        q = st["counters"]["storage_size"]["quota"] if isinstance(st, dict) else st.counters.storage_size_counter.quota
        return f"key accepted, storage quota {q / 1e6:.0f} MB"
    except Exception:
        return "key accepted (statistics not offered on this tier)"


def docintel():
    from azure.ai.formrecognizer import DocumentModelAdministrationClient
    from azure.core.credentials import AzureKeyCredential
    c = DocumentModelAdministrationClient(os.environ["AZURE_DOCINTEL_ENDPOINT"],
                                          AzureKeyCredential(os.environ["AZURE_DOCINTEL_KEY"]))
    d = c.get_resource_details()
    return f"custom model limit {d.custom_document_models.limit} (limit 0 or small = free tier)"


def language():
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.core.credentials import AzureKeyCredential
    c = TextAnalyticsClient(os.environ["AZURE_LANGUAGE_ENDPOINT"], AzureKeyCredential(os.environ["AZURE_LANGUAGE_KEY"]))
    r = c.recognize_entities(["Air Canada 123 landed at Toronto Pearson."])[0]
    return "entities: " + ", ".join(f"{e.text} ({e.category})" for e in r.entities)


if __name__ == "__main__":
    ok = True
    for name, fn in [("Azure OpenAI", openai_chat), ("AI Search", search),
                     ("Document Intelligence", docintel), ("Language", language)]:
        try:
            print(f"  ok    {name:<22} {fn()}")
        except Exception as ex:
            ok = False
            print(f"  FAIL  {name:<22} {type(ex).__name__}: {str(ex).splitlines()[0][:150]}")
    print("all services ready" if ok else "fix the FAIL lines above (check that endpoint and key are from the same resource)")
