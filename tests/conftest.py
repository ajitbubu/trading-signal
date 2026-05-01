"""Test bootstrap: put repo root on sys.path so `import config.settings` works
without needing `pip install -e .`.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
