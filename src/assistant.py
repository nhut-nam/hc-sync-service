import argparse
import glob
import math
import os
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

from google import genai
from google.genai import types

STORE_NAME = os.environ.get("FILE_SEARCH_STORE_NAME", "optibot-mini-clone")
MD_DIR = "output"

SYSTEM_PROMPT = """You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply."""

# Supports both GEMINI_API_KEY and general API_KEY env vars
api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("API_KEY")
client = genai.Client(api_key=api_key)


def estimate_chunks(text):
    tokens = text.split()
    n = len(tokens)
    if n == 0:
        return 0
    if n <= 300:
        return 1
    return 1 + math.ceil((n - 300) / 270)


def get_or_create_store():
    for store in client.file_search_stores.list():
        if store.display_name == STORE_NAME:
            return store

    return client.file_search_stores.create(
        config={
            "display_name": STORE_NAME,
            "embedding_model": "models/gemini-embedding-001",
        }
    )


def upload_file(store_name, path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read()
        chunks = estimate_chunks(text)
    except Exception:
        chunks = 1

    op = client.file_search_stores.upload_to_file_search_store(
        file=path,
        file_search_store_name=store_name,
        config={
            "display_name": os.path.basename(path),
            "chunking_config": {
                "white_space_config": {
                    "max_tokens_per_chunk": 300,
                    "max_overlap_tokens": 30,
                }
            },
        },
    )

    while not op.done:
        time.sleep(2)
        op = client.operations.get(op)

    return op, chunks


def get_document_name(store_name, display_name):
    for doc in client.file_search_stores.documents.list(parent=store_name):
        if doc.display_name == display_name:
            return doc.name
    return None


def delete_document(document_name):
    client.file_search_stores.documents.delete(name=document_name, config={"force": True})


def load_all(store_name, limit=None, only=None):
    files = sorted(glob.glob(os.path.join(MD_DIR, "*.md")))

    if only:
        kw = only.lower()
        files = [
            f for f in files
            if kw in os.path.basename(f).lower() or kw in open(f, encoding="utf-8").read().lower()
        ]

    if limit:
        files = files[:limit]

    uploaded, failed, chunks_total = 0, 0, 0
    for path in files:
        try:
            _, chunks = upload_file(store_name, path)
            uploaded += 1
            chunks_total += chunks
            print(f"[{uploaded}/{len(files)}] Indexed {os.path.basename(path)} ({chunks} chunks)")
        except Exception as e:
            failed += 1
            print(f"FAILED {os.path.basename(path)}: {e}")

    print(f"\nIndexed {uploaded} files ({chunks_total} chunks). Failed: {failed}")
    return uploaded, failed


def ask(store_name, question):
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=question,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[types.Tool(file_search=types.FileSearch(file_search_store_names=[store_name]))],
        ),
    )

    print("\n--- ANSWER ---")
    print(resp.text)

    metadata = resp.candidates[0].grounding_metadata
    chunks = getattr(metadata, "grounding_chunks", None) if metadata else None
    if chunks:
        print("\n--- SOURCES ---")
        seen = set()
        for c in chunks:
            title = c.retrieved_context.title
            if title not in seen:
                print(f"- {title}")
                seen.add(title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--only", type=str, default=None)
    ap.add_argument("--ask", type=str, default=None)
    args = ap.parse_args()

    store = get_or_create_store()
    
    if args.limit is not None or args.only is not None or not args.ask:
        load_all(store.name, args.limit, args.only)

    if args.ask:
        ask(store.name, args.ask)


if __name__ == "__main__":
    main()