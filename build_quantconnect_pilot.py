"""Package the replay as two Python files for QuantConnect Research."""

import argparse
import ast
from pathlib import Path
from pprint import pformat

from fundamental_analysis import load_policy


ROOT = Path(__file__).resolve().parent
MAX_FILE_BYTES = 32_000
SHARED_CODE = (
    ("scanner_currency.py", ("finite",)),
    ("scanner_history.py", ("distribution_adjusted_close",)),
    ("screening.py", ("drawdown_candidate",)),
    ("fundamental_analysis.py", ("_date", "_consecutive", "specialist_requirements", "assess_solvency", "valuation_scenarios")),
    ("backtest_data.py", ("ATTESTATIONS", "ACTION_KINDS", "TERMINAL", "instant", "amount", "Dataset")),
)
REPLAY_CODE = (
    ("backtest_engine.py", ("scan_candidates", "ranked_groups", "schedule", "Lot", "simulate")),
    ("backtest.py", ("DEFAULTS",)),
)
INPUT_IMPORTS = '''from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timezone
from statistics import median
import math

import numpy as np
import pandas as pd
'''
REPLAY_IMPORTS = '''from bisect import bisect_left
from collections import Counter, defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo
import math

from fa_pilot_inputs import Dataset, TERMINAL, assess_solvency, drawdown_candidate, load_policy, valuation_scenarios
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


def shared_sections(group):
    return [f"# From {name}\n\n" + definitions(ROOT / name, symbols) for name, symbols in group]


def build():
    runner = ROOT / "quantconnect_pilot.py"
    source = runner.read_text(encoding="utf-8")
    lines = source.splitlines()
    nodes = ast.parse(source, filename=str(runner)).body
    adapter = "\n\n\n".join(source_text(lines, node) for node in nodes
                             if isinstance(node, (ast.Assign, ast.FunctionDef)))
    policy = "PILOT_POLICY = " + pformat(load_policy(), sort_dicts=True, width=100)
    sections = {
        "fa_pilot_inputs.py": [INPUT_IMPORTS, policy, "def load_policy():\n    return deepcopy(PILOT_POLICY)",
                               *shared_sections(SHARED_CODE)],
        "fa_pilot_replay.py": [REPLAY_IMPORTS, *shared_sections(REPLAY_CODE),
                               "# QuantConnect Research adapter\n\n" + adapter],
    }
    files = {}
    for name, parts in sections.items():
        source = '# Generated from Fallen Angel Scanner source.\n\n' + "\n\n\n".join(parts) + "\n"
        compile(source, name, "exec")
        if len(source.replace("\n", "\r\n").encode("utf-8")) >= MAX_FILE_BYTES:
            raise ValueError(f"{name} exceeds the QuantConnect Free project file limit")
        files[name] = source
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="New directory for the two generated source files")
    args = parser.parse_args()
    files = build()
    args.output_dir.mkdir()
    for name, source in files.items():
        (args.output_dir / name).write_bytes(source.encode("utf-8"))


if __name__ == "__main__":
    main()
