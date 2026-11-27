"""Build (or rebuild) the knowledge-base vector index.  Usage: python -m scripts.build_index"""
import shutil

from src.core import services
from src.core.config import data_dir

if __name__ == "__main__":
    shutil.rmtree(data_dir() / "index", ignore_errors=True)
    services.get_vector_store.cache_clear()
    store = services.get_vector_store()
    print(f"Indexed {len(store.chunks)} chunks into {data_dir() / 'index'}")
