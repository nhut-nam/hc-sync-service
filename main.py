import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from src import scraper, assistant, state as state_mod

OUT_DIR = "output"
MAX_WORKERS = 4


def process_one(store_name, article):
    path = scraper.save_article(article, OUT_DIR)
    display_name = os.path.basename(path)
    op, chunks = assistant.upload_file(store_name, path)
    doc_name = op.response.document_name if hasattr(op, "response") and op.response else None
    return str(article["id"]), article["updated_at"], display_name, chunks, doc_name


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--query", type=str, default=None)
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    print("== fetching articles from Zendesk ==")
    if args.query:
        articles = scraper.search_articles(args.query)
    else:
        articles = scraper.get_articles(limit=args.limit)
    print(f"fetched {len(articles)} articles")

    st = state_mod.load_state()
    added, updated, skipped = state_mod.diff(articles, st)
    print(f"delta: {len(added)} added, {len(updated)} updated, {len(skipped)} skipped")

    to_process = added + updated
    if not to_process:
        print("nothing changed, exiting")
        if args.limit is None and args.query is None:
            deleted = state_mod.detect_deleted(articles, st)
            if deleted:
                print(f"Cleaning up {len(deleted)} orphaned documents...")
                for info in deleted:
                    try:
                        assistant.delete_document(info["document_name"])
                        print(f"  Deleted orphaned doc: {info['display_name']}")
                    except Exception as e:
                        print(f"  Failed to delete orphaned doc {info['display_name']}: {e}")
        return

    store = assistant.get_or_create_store()
    known = st.setdefault("articles", {})

    for a in updated:
        prev = known.get(str(a["id"]))
        if prev and prev.get("document_name"):
            try:
                assistant.delete_document(prev["document_name"])
                print(f"  removed stale doc for article {a['id']}")
            except Exception as e:
                print(f"  warn: couldn't delete old doc for {a['id']}: {e}")

    print(f"uploading {len(to_process)} file(s) with {MAX_WORKERS} parallel workers...")
    failed = 0
    total_embedded_chunks = 0
    total_embedded_files = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(process_one, store.name, a): a for a in to_process}
        for i, fut in enumerate(as_completed(futures), 1):
            a = futures[fut]
            try:
                aid, updated_at, display_name, chunks, doc_name = fut.result()
                total_embedded_chunks += chunks
                total_embedded_files += 1
                print(f"  [{i}/{len(to_process)}] indexed {display_name} ({chunks} chunks)")
            except Exception as e:
                failed += 1
                print(f"  [{i}/{len(to_process)}] FAILED {a.get('title')}: {e}")

    if args.limit is None and args.query is None:
        deleted = state_mod.detect_deleted(articles, st)
        if deleted:
            print(f"Cleaning up {len(deleted)} orphaned documents...")
            for info in deleted:
                try:
                    assistant.delete_document(info["document_name"])
                    print(f"  Deleted orphaned doc: {info['display_name']}")
                except Exception as e:
                    print(f"  Failed to delete orphaned doc {info['display_name']}: {e}")

    print(f"\nDONE — added {len(added)}, updated {len(updated)}, skipped {len(skipped)}, failed {failed}")
    print(f"Total files embedded this run: {total_embedded_files}, Total chunks embedded: {total_embedded_chunks}")


if __name__ == "__main__":
    main()