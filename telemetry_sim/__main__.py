"""Entry point: python -m telemetry_sim <subcommand>."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
