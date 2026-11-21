"""Entry point: python -m prefix_cache_audit [demo|evaluate]."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
