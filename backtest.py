"""Offline backtest CLI: freeze a protocol, then replay one named fold."""

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
import math
from pathlib import Path
import platform

import numpy as np
import pandas as pd

from backtest_data import Dataset, amount
from backtest_engine import DISTRESS, STRATEGIES, ranked_groups, scan_candidates, schedule, simulate
from fundamental_analysis import POLICY_PATH, load_policy


ROOT = Path(__file__).resolve().parent
CODE_FILES = ("backtest.py", "backtest_data.py", "backtest_engine.py", "fundamental_analysis.py",
              "screening.py", "scanner_history.py", "scanner_currency.py")
FOLDS = ("development", "validation", "holdout")
CONTROLS = tuple(s for s in STRATEGIES if s != "scanner_core")
DEFAULTS = {
    "version": 1, "initial_cash": 1_000_000, "max_positions": 10, "signal_interval_sessions": 21,
    "min_market_cap": 750_000_000, "min_adv": 2_000_000, "min_price": 5, "min_drawdown_pct": 20,
    "min_order": 1_000, "participation": .01, "match_ratio": 2,
    "cost_bps": {"commission": 2, "half_spread": 10, "slippage": 10, "impact": 100},
    "cost_scales": [1, 2], "unknown_recovery_scenarios": [0, 1], "horizons_days": [183, 365, 730],
    "acceptance": {"min_annualized_excess": .02, "min_completed_trades": 30, "min_distinct_issuers": 20,
                   "min_outcome_coverage": 1., "min_input_coverage": .95, "min_match_coverage": .8,
                   "max_missing_entry_fraction": .05, "min_market_invested_fraction": .95,
                   "min_independent_blocks": 8, "max_issuer_notional_share": .25,
                   "max_severe_loss_rate": .10, "max_provisional_mark_fraction": .01,
                   "familywise_alpha": .05, "bootstrap_samples": 40000, "bootstrap_seed": 1729},
}


def load_json(path):
    def reject(value):
        raise ValueError(f"Nonfinite JSON value: {value}")
    return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=reject)


def write_new(path, obj):
    with Path(path).open("x", encoding="utf-8") as file:
        json.dump(obj, file, indent=2, sort_keys=True, allow_nan=False)
        file.write("\n")


def protocol(path):
    raw = load_json(path)
    if set(raw) != set(DEFAULTS) | {"folds"} or raw["version"] != 1:
        raise ValueError("Expected complete version 1 protocol; use init-protocol for a template")
    if (set(raw["cost_bps"]) != set(DEFAULTS["cost_bps"])
            or set(raw["acceptance"]) != set(DEFAULTS["acceptance"])):
        raise ValueError("Unknown or missing cost/acceptance setting")
    for name in ("initial_cash", "min_market_cap", "min_adv", "min_price", "min_drawdown_pct", "min_order"):
        amount(raw[name], 1e-12)
    for name in ("max_positions", "signal_interval_sessions"):
        if type(raw[name]) is not int or raw[name] <= 0:
            raise ValueError(f"{name} must be a positive integer")
    if not 0 < amount(raw["participation"]) <= 1 or amount(raw["match_ratio"]) < 1:
        raise ValueError("Invalid participation or matching caliper")
    if (raw["cost_scales"] != [1, 2] or raw["unknown_recovery_scenarios"] != [0, 1]
            or not raw["horizons_days"] or any(type(h) is not int for h in raw["horizons_days"])
            or sorted(set(raw["horizons_days"])) != raw["horizons_days"]
            or not set(raw["horizons_days"]) <= {183, 365, 730}):
        raise ValueError("Use base/double costs, zero/last-mark scenarios, and supported separate horizons")
    if 2 * sum(amount(x) for x in raw["cost_bps"].values()) >= 10000:
        raise ValueError("Costs would exhaust a fill under the stress scenario")
    if not isinstance(raw["folds"], dict) or set(raw["folds"]) != set(FOLDS):
        raise ValueError("Specify development, validation and holdout")
    previous = date.min
    for name in FOLDS:
        start, end = (date.fromisoformat(raw["folds"][name][x]) for x in ("start", "end"))
        if not previous < start < end:
            raise ValueError("Folds must be chronological and nonoverlapping")
        previous = end
    a = raw["acceptance"]
    for name, value in a.items():
        amount(value)
        if name.startswith(("min_outcome_", "min_input_", "min_match_", "min_market_invested_", "max_")) and not 0 < value <= 1:
            raise ValueError(f"{name} must be a fraction in (0,1]")
    for name in ("min_completed_trades", "min_distinct_issuers", "min_independent_blocks", "bootstrap_samples", "bootstrap_seed"):
        if type(a[name]) is not int or a[name] < (0 if name == "bootstrap_seed" else 1):
            raise ValueError(f"Invalid integer: {name}")
    if not 0 < a["familywise_alpha"] <= .05 or a["bootstrap_samples"] < 1000 or a["min_independent_blocks"] < 4:
        raise ValueError("Inference needs conservative alpha, at least 1000 draws and four independent blocks")
    if a["bootstrap_samples"] * interval_tail(raw) < 20:
        raise ValueError("Too few bootstrap draws for the frozen familywise tail")
    return raw


def interval_tail(config):
    tests = len(CONTROLS)*len(config["horizons_days"])*len(config["cost_scales"])*len(config["unknown_recovery_scenarios"])
    return config["acceptance"]["familywise_alpha"] / (2*tests)


def digest(path):
    h = sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def lock_for(dataset_path, protocol_path, policy_path):
    code = {name: sha256((ROOT/name).read_text(encoding="utf-8").encode("utf-8")).hexdigest() for name in CODE_FILES}
    return dict(version=1, dataset_sha256=digest(dataset_path), protocol_sha256=digest(protocol_path),
                policy_sha256=digest(policy_path), code_sha256=code,
                runtime=dict(python=platform.python_version(), numpy=np.__version__, pandas=pd.__version__))


def annualized(nav):
    n = len(nav) - 1
    if n <= 0 or nav[0] <= 0 or nav[-1] < 0:
        return None
    return (nav[-1] / nav[0]) ** (252. / n) - 1.


def summarize(result):
    path = [x["nav"] for x in result["daily"]]
    known = [x for x in result["trades"] if x["outcome_known"]]
    hit_known = [x for x in known if x["target_touched_at_close"] is not None]
    count = len(result["trades"])
    by_issuer = Counter()
    for x in result["trades"]:
        by_issuer[x["issuer"]] += x["initial_notional"]
    peak = np.maximum.accumulate(path)
    attempted = result["counts"].get("attempted_entries", 0)
    return dict(total_net_return=path[-1]/path[0]-1, annualized_net_return=annualized(path),
                max_drawdown=float((np.asarray(path) / peak - 1.).min()),
                turnover_notional_over_average_nav=result["turnover_notional"]/float(np.mean(path)),
                transaction_cost=result["costs"], completed_trades=len(known),
                unknown_outcomes=count-len(known), outcome_coverage=len(known)/count if count else 0.,
                distinct_issuers=len(by_issuer), largest_issuer_notional_share=max(by_issuer.values())/by_issuer.total() if by_issuer else None,
                severe_loss_rate=sum(x["net_return"] <= -.5 for x in known)/len(known) if known else None,
                distress_exits=sum(bool(DISTRESS.intersection(x["terminal_events"])) for x in result["trades"]),
                target_touch_hits=sum(x["target_touched_at_close"] is True for x in hit_known),
                target_touch_known_paths=len(hit_known),
                target_exit_hits=sum(x["target_met_at_exit"] is True for x in known),
                provisional_mark_fraction=sum(x["provisional_mark"] for x in result["daily"])/len(path),
                missing_entry_fraction=result["counts"].get("missed_entry_open", 0)/max(1, attempted),
                first_entry_fraction=(result["trades"][0]["initial_notional"]+result["trades"][0]["entry_cost"])/path[0]
                if count else 0.,
                order_counts=result["counts"])


def paired_comparison(primary, control, horizon, cfg):
    x, y = [np.array([row["nav"] for row in v["daily"]]) for v in (primary, control)]
    block = math.ceil(horizon*252/365)
    result = dict(annualized_net_excess=annualized(x)-annualized(y), block_sessions=block,
                  nominal_blocks=(len(x)-1)//block, interval=None, halves_net_excess=None)
    middle = len(x)//2
    if min(x[middle], y[middle]) > 0 and len(x) >= 4:
        result["halves_net_excess"] = [annualized(x[:middle+1])-annualized(y[:middle+1]),
                                       annualized(x[middle:])-annualized(y[middle:])]
    a = cfg["acceptance"]
    if result["nominal_blocks"] < a["min_independent_blocks"] or min(x.min(), y.min()) <= 0:
        return result
    rx, ry = np.diff(np.log(x)), np.diff(np.log(y))
    n = len(rx)
    rng = np.random.default_rng(a["bootstrap_seed"])
    # Paired circular moving-block bootstrap: preserve within-block dependence
    # and use the same resampled dates for the strategy and its control.
    full, remainder = divmod(n, block)
    def sums(values, width):
        cumulative = np.r_[0., np.cumsum(np.r_[values, values[:width]])]
        return cumulative[width:width+n] - cumulative[:n]
    whole = [sums(v, block) for v in (rx, ry)]
    part = [sums(v, remainder) for v in (rx, ry)]
    sims = []
    for offset in range(0, a["bootstrap_samples"], 2048):
        size = min(2048, a["bootstrap_samples"]-offset)
        starts = rng.integers(n, size=(size, full + bool(remainder)))
        totals = [w[starts[:, :full]].sum(axis=1) + (p[starts[:, -1]] if remainder else 0)
                  for w, p in zip(whole, part)]
        sims.extend(np.expm1(252*totals[0]/n)-np.expm1(252*totals[1]/n))
    tail = interval_tail(cfg)
    result["interval"] = [float(q) for q in np.quantile(sims, [tail, 1-tail])]
    return result


def gate(metrics, comparisons, coverage, config):
    a = config["acceptance"]
    core = metrics["scanner_core"]
    insufficient = []
    if core["completed_trades"] < a["min_completed_trades"] or core["distinct_issuers"] < a["min_distinct_issuers"]:
        insufficient.append("Too few resolved scanner trades or distinct issuers")
    if (coverage["input_fraction"] < a["min_input_coverage"]
            or coverage["match_fraction"] < a["min_match_coverage"]
            or coverage["matched_fill_fraction"] < a["min_match_coverage"]):
        insufficient.append("Insufficient point-in-time input or matching coverage")
    if any(m["outcome_coverage"] < a["min_outcome_coverage"]
           or m["provisional_mark_fraction"] > a["max_provisional_mark_fraction"] for m in metrics.values()):
        insufficient.append("Insufficient outcome coverage or too many provisional marks")
    if (any(m["missing_entry_fraction"] > a["max_missing_entry_fraction"] for m in metrics.values())
            or metrics["market"]["first_entry_fraction"] < a["min_market_invested_fraction"]):
        insufficient.append("Missing entry prices or underfunded market benchmark")
    if any(c["interval"] is None for c in comparisons.values()):
        insufficient.append("Insufficient dependence-adjusted sample for inference")
    if insufficient:
        return "INSUFFICIENT_EVIDENCE", insufficient
    failed = []
    if core["largest_issuer_notional_share"] > a["max_issuer_notional_share"]:
        failed.append("Issuer concentration exceeds the frozen limit")
    if core["severe_loss_rate"] > a["max_severe_loss_rate"]:
        failed.append("Severe-loss rate exceeds the frozen limit")
    for name, c in comparisons.items():
        if (c["annualized_net_excess"] < a["min_annualized_excess"] or c["interval"][0] <= 0
                or not c["halves_net_excess"] or min(c["halves_net_excess"]) <= 0):
            failed.append(f"Incremental performance gate failed against {name}")
    return ("GATE_NOT_MET", failed) if failed else ("GATE_MET_FOR_CORE_ONLY", [])


def write_summary(out, report):
    lines = ["# Historical replay report", "", f"**{report['status']}** · {report['fold']} fold · {report['dataset_kind']} data",
             "", report["notice"], "", "Baseline costs and zero-recovery sensitivity:", "",
             "| Horizon | Scenario status | Resolved scanner trades | Scanner net return | Market net return |",
             "|---|---|---:|---:|---:|"]
    notes = []
    for horizon, detail in report["horizons"].items():
        if not detail.get("scenarios"):
            lines.append(f"| {horizon} days | {detail['status']} | — | — | — |")
            notes.extend(f"- {horizon} days: {reason}" for reason in detail["reasons"])
            continue
        base = detail["scenarios"][0]
        metrics = base["metrics"]
        scanner, market = metrics["scanner_core"], metrics["market"]
        lines.append(f"| {horizon} days | {detail['status']} | {scanner['completed_trades']} | "
                     f"{scanner['total_net_return']:+.2%} | {market['total_net_return']:+.2%} |")
        reasons = sorted({reason for scenario in detail["scenarios"] for reason in scenario["reasons"]})
        notes.extend(f"- {horizon} days: {reason}" for reason in reasons)
    lines += ["", *notes, "", "See report.json for paired comparisons, coverage, all cost/recovery scenarios and the frozen inputs."]
    (out/"report.md").write_text("\n".join(lines)+"\n", encoding="utf-8")


def run(dataset_path, protocol_path, policy_path, lock_path, fold, out):
    expected = lock_for(dataset_path, protocol_path, policy_path)
    if load_json(lock_path) != expected:
        raise ValueError("Frozen data, protocol, policy or implementation changed; lock does not match")
    cfg, data, policy = protocol(protocol_path), Dataset(load_json(dataset_path)), load_policy(policy_path)
    bounds = cfg["folds"][fold]
    start, end = (date.fromisoformat(bounds[x]) for x in ("start", "end"))
    if not data.days[0] <= start < end <= data.days[-1]:
        raise ValueError("Requested fold is outside the supplied session calendar")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    report = dict(fold=fold, bounds=bounds, dataset_kind=data.kind, data_source=data.source, attested=data.attested,
                  lock=expected, horizons={},
                  notice="Deterministic core proxy only; no live headline/risk-score parity, AI, manual cases or five-year survival estimates. "
                         "Zero/last-mark recovery are scenarios, not bounds on true proceeds.")
    cache = {}
    for horizon in cfg["horizons_days"]:
        first, stop, eligible = schedule(data, start, end, horizon, cfg["signal_interval_sessions"])
        if not eligible:
            report["horizons"][str(horizon)] = dict(status="INSUFFICIENT_EVIDENCE", reasons=["No signals with full horizon inside the fold"])
            continue
        orders = {s: {} for s in STRATEGIES}
        totals = Counter()
        signals = []
        for i, exit_i in eligible.items():
            if i not in cache:
                candidates, counts = scan_candidates(data, i, cfg, policy)
                cache[i] = ranked_groups(candidates, cfg), counts
            groups, counts = cache[i]
            totals.update(counts)
            totals["core_candidates"] += len(groups["scanner_core"])
            totals["matched_candidates"] += len(groups["matched"])
            for s, rows in groups.items():
                orders[s][i+1] = (i, exit_i, rows)
            signals.append(dict(session=str(data.days[i]), cutoff=data.closes[i].isoformat(),
                                planned_exit=str(data.days[exit_i]), coverage=dict(counts), groups=groups))
        i = first
        adv = data.adv(data.benchmark, i)
        if adv:
            security = data.securities[data.benchmark]
            orders["market"][i+1] = (i, stop-1, [dict(sid=data.benchmark, issuer=security["issuer_id"], adv=adv)])
        coverage = dict(counts=dict(totals), signals=len(eligible),
                        input_fraction=(1.-totals["input_unverified_members"]/totals["active_members"]
                                        if totals["active_members"] else 0.),
                        match_fraction=totals["matched_candidates"]/max(1, totals["core_candidates"]))
        write_new(out/f"signals-{horizon}.json", signals)
        detail = dict(coverage=coverage, scenarios=[])
        for scale in cfg["cost_scales"]:
            for recovery in cfg["unknown_recovery_scenarios"]:
                core = simulate(data, cfg, first, stop, orders["scanner_core"], "scanner_core", horizon, scale, recovery)
                core_entries = {(t["entry_session"], t["sid"]) for t in core["trades"]}
                # Match realized entries at their entry session; no return or
                # future outcome fields are used to choose the matched control.
                matched_orders = {i: (signal_i, exit_i, [r for r in rows
                    if (str(data.days[i]), r["matched_to"]) in core_entries])
                    for i, (signal_i, exit_i, rows) in orders["matched"].items()}
                results = {"scanner_core": core}
                for s in CONTROLS:
                    results[s] = simulate(data, cfg, first, stop, matched_orders if s == "matched" else orders[s],
                                          s, horizon, scale, recovery)
                metrics = {s: summarize(r) for s, r in results.items()}
                comparisons = {s: paired_comparison(results["scanner_core"], results[s], horizon, cfg) for s in CONTROLS}
                fill_coverage = len(results["matched"]["trades"])/max(1, len(core_entries))
                status, reasons = gate(metrics, comparisons, {**coverage, "matched_fill_fraction": fill_coverage}, cfg)
                ledger = f"ledger-{horizon}-cost-{scale}-recovery-{recovery}.json"
                write_new(out/ledger, results)
                detail["scenarios"].append(dict(cost_scale=scale, unknown_recovery=recovery, metrics=metrics,
                                                comparisons=comparisons, status=status, reasons=reasons, ledger=ledger,
                                                matched_fill_fraction=fill_coverage))
        statuses = {s["status"] for s in detail["scenarios"]}
        detail["status"] = ("INSUFFICIENT_EVIDENCE" if "INSUFFICIENT_EVIDENCE" in statuses
                            else "GATE_NOT_MET" if "GATE_NOT_MET" in statuses else "GATE_MET_FOR_CORE_ONLY")
        report["horizons"][str(horizon)] = detail
    status_set = {h["status"] for h in report["horizons"].values()}
    report["status"] = ("SYNTHETIC_ONLY" if data.kind == "synthetic" else
                        "DEVELOPMENT_ONLY" if fold != "holdout" else
                        "INSUFFICIENT_EVIDENCE" if not all(data.attested.values()) or "INSUFFICIENT_EVIDENCE" in status_set else
                        "GATE_NOT_MET" if "GATE_NOT_MET" in status_set else "GATE_MET_FOR_CORE_ONLY")
    write_new(out/"report.json", report)
    write_summary(out, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init-protocol", help="Write a template; set the dated folds before freezing")
    init.add_argument("output")
    for name in ("freeze", "run"):
        p = sub.add_parser(name)
        p.add_argument("--data", required=True)
        p.add_argument("--protocol", required=True)
        p.add_argument("--policy", default=str(POLICY_PATH))
        p.add_argument("--lock", required=True)
        if name == "run":
            p.add_argument("--fold", choices=FOLDS, required=True)
            p.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    try:
        if args.command == "init-protocol":
            write_new(args.output, {**DEFAULTS, "folds": {f: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"} for f in FOLDS}})
        elif args.command == "freeze":
            protocol(args.protocol)
            load_policy(args.policy)
            write_new(args.lock, lock_for(args.data, args.protocol, args.policy))
        else:
            report = run(args.data, args.protocol, args.policy, args.lock, args.fold, args.output_dir)
            print(f"{report['status']}: {Path(args.output_dir)/'report.json'}")
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f"Backtest input/replay error: {exc}\n")


if __name__ == "__main__":
    main()
