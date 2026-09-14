"""Make ``tita_perception`` importable when running pytest from a checkout
without ``pip install -e`` (colcon test installs the package first, so this
is a no-op there)."""

import sys
from pathlib import Path

_PKG_ROOT = str(Path(__file__).resolve().parent)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)
