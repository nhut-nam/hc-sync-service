import os
import re
from datetime import datetime
from src import assistant


def load_state():
    print("Fetching active vector store state from Gemini...")
    try:
        store = assistant.get_or_create_store()
    except Exception as e:
        print(f"Error connecting to store: {e}. Falling back to empty state.")
        return {"articles": {}}

    pattern = re.compile(r"^(.+)_id_(\d+)_u_(\d+)\.md$")
    articles_state = {}
    duplicates = []

    try:
        docs = list(assistant.client.file_search_stores.documents.list(parent=store.name))
        print(f"Found {len(docs)} documents in the vector store.")
        for doc in docs:
            display_name = doc.display_name
            match = pattern.match(display_name)
            if match:
                slug, aid, epoch = match.group(1), match.group(2), int(match.group(3))
                if aid in articles_state:
                    prev = articles_state[aid]
                    if epoch > prev["updated_at_epoch"]:
                        duplicates.append(prev["document_name"])
                        articles_state[aid] = {
                            "updated_at_epoch": epoch,
                            "document_name": doc.name,
                            "display_name": display_name
                        }
                    else:
                        duplicates.append(doc.name)
                else:
                    articles_state[aid] = {
                        "updated_at_epoch": epoch,
                        "document_name": doc.name,
                        "display_name": display_name
                    }
            else:
                duplicates.append(doc.name)
                
        if duplicates:
            print(f"Cleaning up {len(duplicates)} duplicate/legacy documents...")
            for doc_name in duplicates:
                try:
                    assistant.delete_document(doc_name)
                except Exception as e:
                    print(f"Failed to delete {doc_name}: {e}")
                    
    except Exception as e:
        print(f"Error listing documents: {e}")
        
    return {"articles": articles_state}


def save_state(state, path=None):
    pass


def diff(articles, state):
    known = state.get("articles", {})
    added, updated, skipped = [], [], []

    for a in articles:
        aid = str(a["id"])
        prev = known.get(aid)

        if prev is None:
            added.append(a)
        else:
            dt = datetime.fromisoformat(a["updated_at"].replace("Z", "+00:00"))
            epoch = int(dt.timestamp())
            if prev.get("updated_at_epoch") != epoch:
                updated.append(a)
            else:
                skipped.append(a)

    return added, updated, skipped


def detect_deleted(articles, state):
    known = state.get("articles", {})
    fetched_ids = {str(a["id"]) for a in articles}
    deleted = []
    
    for aid, info in known.items():
        if aid not in fetched_ids:
            deleted.append(info)
            
    return deleted