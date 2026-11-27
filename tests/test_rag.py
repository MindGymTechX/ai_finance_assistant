import numpy as np

from src.core.config import KB_DIR
from src.rag.chunker import chunk_documents, chunk_text
from src.rag.loader import load_documents, parse_front_matter
from src.rag.store import VectorStore

VOCAB = ["ppf", "tax", "mutual", "fund", "stock", "credit", "score", "gold", "inflation", "emi"]


def fake_embed(texts):
    return [[t.lower().count(w) + 0.01 for w in VOCAB] for t in texts]


def test_front_matter():
    meta, body = parse_front_matter("---\ntitle: X\ncategory: tax\n---\nHello")
    assert meta == {"title": "X", "category": "tax"} and body == "Hello"


def test_chunker_respects_size_and_overlap():
    text = "# A\n" + ("Sentence one is here. " * 100)
    chunks = chunk_text(text, size=300, overlap=50)
    assert len(chunks) > 3 and all(len(c) <= 300 for c in chunks)


def test_knowledge_base_loads_with_categories():
    docs = load_documents(KB_DIR)
    assert len(docs) >= 50
    cats = {d["category"] for d in docs}
    assert {"tax", "basics", "mutual_funds", "stocks", "banking"} <= cats
    assert all(d["title"] and d["text"] for d in docs)
    tax_docs = [d for d in docs if d["category"] == "tax"]
    assert all("Rules as of" in d["text"] for d in tax_docs)


def test_store_search_filter_threshold_and_persistence(tmp_path):
    chunks = chunk_documents(load_documents(KB_DIR), 800, 120)
    store = VectorStore.build(chunks, fake_embed)
    q = fake_embed(["ppf tax"])[0]
    hits = store.search(q, k=3, category="tax")
    assert hits and all(h["category"] == "tax" for h in hits)
    assert hits[0]["score"] >= hits[-1]["score"]
    assert store.search(q, k=3, min_score=1.01) == []
    store.save(tmp_path)
    again = VectorStore.load(tmp_path)
    assert len(again.chunks) == len(chunks)
    assert np.allclose(again.vectors, store.vectors)
    assert VectorStore.load(tmp_path / "missing") is None
