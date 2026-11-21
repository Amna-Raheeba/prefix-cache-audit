"""Root conftest: make the package importable under plain ``pytest``."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
