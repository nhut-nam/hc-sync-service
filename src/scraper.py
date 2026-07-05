import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv()

import requests
from markdownify import markdownify as html_to_md
from slugify import slugify

BASE = "https://support.optisigns.com"
ARTICLES_URL = f"{BASE}/api/v2/help_center/en-us/articles.json"
SEARCH_URL = f"{BASE}/api/v2/help_center/articles/search.json"
OUT_DIR = "output"
PER_PAGE = 100

session = requests.Session()
session.headers.update({"User-Agent": "optisigns-scraper/1.0"})


def get_articles(limit=None):
    articles = []
    url = f"{ARTICLES_URL}?per_page={PER_PAGE}"

    while url:
        r = session.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()

        articles += data["articles"]
        if limit and len(articles) >= limit:
            return articles[:limit]

        url = data["next_page"]
        if url:
            time.sleep(0.3)

    return articles


def search_articles(query):
    r = session.get(SEARCH_URL, params={"query": query}, timeout=30)
    r.raise_for_status()
    return r.json()["results"]


def strip_junk(html):
    if not html:
        return ""
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S | re.I)
    html = re.sub(r"<p>(\s|&nbsp;)*</p>", "", html, flags=re.I)
    return html.strip()


def to_markdown(html):
    md = html_to_md(html, heading_style="ATX", bullets="-")
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def save_article(article, out_dir):
    title = article["title"]
    slug = slugify(title)[:80] or str(article["id"])

    dt = datetime.fromisoformat(article["updated_at"].replace("Z", "+00:00"))
    epoch = int(dt.timestamp())

    path = os.path.join(out_dir, f"{slug}_id_{article['id']}_u_{epoch}.md")
    body = to_markdown(strip_junk(article["body"]))

    header = (
        "---\n"
        f"title: {json.dumps(title)}\n"
        f"article_id: {article['id']}\n"
        f"source_url: {article['html_url']}\n"
        f"updated_at: {article['updated_at']}\n"
        "---\n\n"
    )

    with open(path, "w", encoding="utf-8") as f:
        f.write(header + f"# {title}\n\n" + body + f"\n\nArticle URL: {article['html_url']}\n")

    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--query", type=str, default=None)
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)

    if args.query:
        articles = search_articles(args.query)
    else:
        articles = get_articles(args.limit)

    files = [save_article(a, args.out) for a in articles]

    with open(os.path.join(args.out, "_manifest.json"), "w") as f:
        json.dump(
            {"scraped_at": datetime.now(timezone.utc).isoformat(), "count": len(files), "files": files},
            f,
            indent=2,
        )

    print(f"done - {len(files)} files written")


if __name__ == "__main__":
    main()