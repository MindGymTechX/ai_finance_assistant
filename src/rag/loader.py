"""Loads knowledge-base markdown files with a small front-matter header:

---
title: What is a mutual fund?
category: mutual_funds
source: FinAI-authored summary (reference: SEBI investor education)
reference_url: https://...
last_checked: 2026-11-21   (optional, for facts verified against a dated source)
---
"""
from __future__ import annotations

from pathlib import Path


def parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict[str, str] = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            for line in text[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            text = text[end + 4:]
    return meta, text.strip()


def load_documents(kb_dir: Path) -> list[dict]:
    docs = []
    for path in sorted(Path(kb_dir).rglob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        docs.append({
            "id": str(path.relative_to(kb_dir)),
            "title": meta.get("title", path.stem.replace("_", " ").title()),
            "category": meta.get("category", path.parent.name),
            "source": meta.get("source", "FinAI knowledge base"),
            "source_url": meta.get("reference_url", meta.get("source_url", "")),
            "last_checked": meta.get("last_checked", ""),
            "text": body,
        })
    return docs
