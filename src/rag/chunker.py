"""Heading-aware chunking: split on markdown headings first, then by size with overlap."""
from __future__ import annotations

import re


def _split_sections(text: str) -> list[str]:
    parts = re.split(r"\n(?=#{1,3} )", text)
    return [p.strip() for p in parts if p.strip()]


def chunk_text(text: str, size: int = 800, overlap: int = 120) -> list[str]:
    chunks: list[str] = []
    for section in _split_sections(text):
        if len(section) <= size:
            chunks.append(section)
            continue
        start = 0
        while start < len(section):
            end = min(len(section), start + size)
            if end < len(section):  # prefer to break at a sentence or line end
                cut = max(section.rfind(". ", start, end), section.rfind("\n", start, end))
                if cut > start + size // 2:
                    end = cut + 1
            chunks.append(section[start:end].strip())
            if end >= len(section):
                break
            start = max(end - overlap, start + 1)
    return [c for c in chunks if c]


def chunk_documents(docs: list[dict], size: int = 800, overlap: int = 120) -> list[dict]:
    out = []
    for d in docs:
        for i, c in enumerate(chunk_text(d["text"], size, overlap)):
            out.append({"chunk_id": f"{d['id']}#{i}", "doc_id": d["id"], "title": d["title"],
                        "category": d["category"], "source": d["source"],
                        "source_url": d["source_url"], "text": f"{d['title']}\n{c}"})
    return out
