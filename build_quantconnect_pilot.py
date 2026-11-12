"""Package the existing replay into readable source for one QuantConnect Research cell."""

import argparse
import ast
from pathlib import Path
from pprint import pformat

from fundamental_analysis import load_policy


ROOT = Path(__file__).resolve().parent
SHARED_CODE = (
    ("scanner_currency.py", ("finite",)),
    ("scanner_history.py", ("distribution_adjusted_close",)),
    ("screening.py", ("drawdown_candidate",)),
    ("fundamental_analysis.py", ("_date", "_consecutive", "specialist_requirements", "assess_solvency", "valuation_scenarios")),
    ("backtest_data.py", ("ATTESTATIONS", "ACTION_KINDS", "TERMINAL", "instant", "amount", "Dataset")),
    ("backtest_engine.py", ("scan_candidates", "ranked_groups", "schedule", "Lot", "simulate")),
    ("backtest.py", ("DEFAULTS",)),
)
HEADER = '''"""Fallen Angel Scanner development pilot for QuantConnect Research.

Generated locally from readable scanner source. Runs in memory and prints only coverage counts.
Paste into a Python code cell in QuantConnect Research and run the cell.
"""

from bisect import bisect_left
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from statistics import median
from zoneinfo import ZoneInfo
import json
import math

import numpy as np
import pandas as pd
'''


def source_text(lines, node):
    decorators = getattr(node, "decorator_list", ())
    start = min([node.lineno, *(decorator.lineno for decorator in decorators)])
    return "\n".join(lines[start-1:node.end_lineno])


def definitions(path, names):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    found = {}
    for node in ast.parse(source, filename=str(path)).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            found[node.name] = source_text(lines, node)
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = source_text(lines, node)
    return "\n\n\n".join(found[name] for name in names)


def build():
    runner = ROOT / "quantconnect_pilot.py"
    source = runner.read_text(encoding="utf-8")
    lines = source.splitlines()
    nodes = ast.parse(source, filename=str(runner)).body
    adapter = "\n\n\n".join(source_text(lines, node) for node in nodes
                             if isinstance(node, (ast.Assign, ast.FunctionDef)))
    policy = "PILOT_POLICY = " + pformat(load_policy(), sort_dicts=True, width=100)
    sections = [HEADER, policy, "def load_policy():\n    return deepcopy(PILOT_POLICY)"]
    sections.extend(f"# From {name}\n\n" + definitions(ROOT / name, symbols) for name, symbols in SHARED_CODE)
    sections.extend(["# QuantConnect Research adapter\n\n" + adapter,
                     'print(json.dumps(run_quantconnect_pilot(), indent=2, sort_keys=True))'])
    bundle = "\n\n\n".join(sections) + "\n"
    compile(bundle, "quantconnect_pilot_cell.py", "exec")
    return bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        file.write(build())


if __name__ == "__main__":
    main()
