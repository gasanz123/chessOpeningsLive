#!/usr/bin/env python3
"""Simple script to start the Chess Openings Live web server."""

import sys
from pathlib import Path

# Add the scripts directory to the path
scripts_dir = Path(__file__).parent / "scripts"
sys.path.insert(0, str(scripts_dir))

from lichess_openings import main

if __name__ == "__main__":
    # Run with --serve flag to start the web server
    args = ["--serve", "--port", "8000"]
    sys.exit(main(args))
