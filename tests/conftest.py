import os
import sys
import tempfile
from pathlib import Path

# Isolate all SQLite files / indexes from the developer's real data
os.environ["FINAI_DATA_DIR"] = tempfile.mkdtemp(prefix="finai-test-")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
