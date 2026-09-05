"""Make ``brain`` importable when pytest runs from this directory (mirrors server/ layout)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
