#!/usr/bin/env python3
"""Run the bundled offline integration tests; does not evaluate agent behavior."""
from pathlib import Path
import sys
import unittest


def main():
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parents[1] / "tests"), pattern="test_*.py")
    if not suite.countTestCases():
        print("No tests discovered", file=sys.stderr)
        return 2
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
