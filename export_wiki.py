#!/usr/bin/env python3
"""
export_wiki.py - export every Wiki.js page to a local .md file.

The output folder is meant for oikb, which then performs the incremental
sync to an Open WebUI knowledge base (add / update / delete).

Deliberately simple and robust: every run rewrites ALL pages and removes
orphaned .md files (pages deleted from the wiki). No need to be incremental
here: oikb only re-uploads what changed (SHA-256 diff).

Usage:
    export WIKI_URL="https://wiki.example.org"
    export WIKI_TOKEN="your_wikijs_api_token"
    export OUT_DIR="./wiki_md"
    python export_wiki.py
"""

import os
import re
import sys

import requests

WIKI_URL   = os.environ.get("WIKI_URL", "https://wiki.example.org").rstrip("/")
WIKI_TOKEN = os.environ.get("WIKI_TOKEN", "")
OUT_DIR    = os.environ.get("OUT_DIR", "./wiki_md")
# Marker injected under every level-2 heading so that each chunk keeps its
# source URL after the RAG splitter has cut the page. The RAG template in
# examples/rag_template.txt tells the model to cite it.
SOURCE_MARKER = os.environ.get("SOURCE_MARKER", "Source de ce paragraphe")


def gql(query, variables=None):
    r = requests.post(
        f"{WIKI_URL}/graphql",
        json={"query": query, "variables": variables or {}},
        headers={"Authorization": f"Bearer {WIKI_TOKEN}"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"GraphQL: {data['errors']}")
    return data["data"]


def list_pages():
    return gql("{ pages { list(orderBy: PATH) { id path title locale } } }")["pages"]["list"]


def get_content(page_id):
    q = "query($id:Int!){ pages { single(id:$id){ content } } }"
    return gql(q, {"id": page_id})["pages"]["single"]["content"] or ""


def safe_relpath(wiki_path):
    """Turn a wiki page path into a safe relative file path."""
    rel = wiki_path.strip("/").replace("..", "_")
    return (rel or "index") + ".md"


def export():
    pages = list_pages()
    written = set()

    for p in pages:
        rel = safe_relpath(p["path"])
        dest = os.path.join(OUT_DIR, rel)
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)

        # header: title + source URL, so the RAG answer can cite the page
        url = f"{WIKI_URL}/{p['path'].lstrip('/')}"
        header = f"{p['title']}\n\nSource : {url}\n\n---\n\n"
        content = get_content(p["id"])

        # repeat the source URL under each "## " heading: chunks made from the
        # middle of a long page would otherwise lose the reference
        content = re.sub(
            r"^(##\s+.*)$",
            lambda m: m.group(1) + "\n\n*" + SOURCE_MARKER + " : " + url + "*\n",
            content,
            flags=re.MULTILINE,
        )
        with open(dest, "w", encoding="utf-8") as f:
            f.write(header + content)

        written.add(os.path.abspath(dest))
        print(f"  written  {rel}")

    # remove orphaned .md files -> oikb will propagate the deletion to the KB
    removed = 0
    for root, _dirs, files in os.walk(OUT_DIR):
        for name in files:
            if not name.endswith(".md"):
                continue
            full = os.path.abspath(os.path.join(root, name))
            if full not in written:
                os.remove(full)
                removed += 1
                print(f"  removed  {os.path.relpath(full, OUT_DIR)}")

    print(f"\n{len(pages)} pages exportées, {removed} orphelins supprimés -> {OUT_DIR}")


if __name__ == "__main__":
    if not WIKI_TOKEN:
        sys.exit("WIKI_TOKEN is missing: export WIKI_TOKEN=... (Wiki.js > Administration > API Access)")
    export()
