"""Strict validator for competition submissions (Python standard library only)."""
import argparse
import csv
import datetime as dt
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PRIVATE_START = dt.datetime.fromisoformat("2026-11-11T01:00:00+05:30")
PRIVATE_END = dt.datetime.fromisoformat("2026-11-13T00:00:00+05:30")
STATIONS = ("11611", "11606", "3409510", "3409511")


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def load_clean_last24():
    raw = read_csv(ROOT / "Train.csv")
    by_station = {s: {} for s in STATIONS}
    for row in raw:
        sid = row["location_id"]
        by_station[sid][dt.datetime.fromisoformat(row["timestamp_ist"])] = float(row["pm25"])
    clean = {s: {} for s in STATIONS}
    for sid in STATIONS:
        for stamp, value in by_station[sid].items():
            peers = [by_station[o][stamp] for o in STATIONS if o != sid and stamp in by_station[o]]
            isolated = value > 500 and bool(peers) and _median(peers) < 150
            if value <= 1000 and not isolated:
                clean[sid][stamp] = value
    t0 = max(t for values in by_station.values() for t in values)
    means = {}
    for sid in STATIONS:
        values = [v for t, v in clean[sid].items() if t0 - dt.timedelta(hours=24) < t <= t0]
        means[sid] = sum(values) / len(values) if values else float("nan")
    return means


def _median(values):
    s = sorted(values)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def validate_file(path, verbose=True):
    path = Path(path)
    errors = []
    try:
        with path.open(newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != ["ID", "Target"]:
                errors.append(f"columns must be ['ID', 'Target']; got {reader.fieldnames}")
            rows = list(reader)
    except Exception as exc:
        if verbose:
            print(f"{path.name}: FAIL — cannot read file: {exc}")
        return False

    if len(rows) != 2592:
        errors.append(f"expected 2592 data rows; got {len(rows)}")
    sample = read_csv(ROOT / "SampleSubmission.csv")
    expected_ids = [row["ID"] for row in sample]
    if [row.get("ID") for row in rows] != expected_ids:
        errors.append("IDs or row order differ from SampleSubmission.csv")
    parsed = []
    for index, row in enumerate(rows, 1):
        try:
            value = float(row["Target"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"row {index}: Target is not numeric")
            parsed.append(float("nan"))
            continue
        parsed.append(value)
        if not math.isfinite(value):
            errors.append(f"row {index}: Target is NaN or infinite")
        elif value < 0:
            errors.append(f"row {index}: Target is negative")
        elif value > 1000:
            errors.append(f"row {index}: Target exceeds 1000")

    test = read_csv(ROOT / "Test.csv")
    t0 = max(dt.datetime.fromisoformat(r["timestamp_ist"]) for r in read_csv(ROOT / "Train.csv"))
    private = [r for r in test if PRIVATE_START <= dt.datetime.fromisoformat(r["target_end_ist"]) <= PRIVATE_END]
    if len(private) != 192:
        errors.append(f"date-selected private window should contain 192 Test rows; got {len(private)}")
    horizons = [(dt.datetime.fromisoformat(r["target_end_ist"]) - t0).total_seconds() / 3600 for r in private]
    if set(horizons) != set(range(16, 64)):
        errors.append(f"private horizons should be exactly 16..63; got {sorted(set(horizons))[:3]}..{sorted(set(horizons))[-3:] if horizons else []}")
    if len(rows) == len(test):
        by_station = {s: [] for s in STATIONS}
        for row, tr in zip(rows, test):
            stamp = dt.datetime.fromisoformat(tr["target_end_ist"])
            if tr["location_id"] in by_station and PRIVATE_START <= stamp <= PRIVATE_END:
                try:
                    by_station[tr["location_id"]].append(float(row["Target"]))
                except (KeyError, TypeError, ValueError):
                    pass
        try:
            last24 = load_clean_last24()
        except Exception as exc:
            errors.append(f"could not calculate cleaned last-24h means: {exc}")
            last24 = {}
        if verbose:
            print(f"{path.name} private means (192 date-selected rows):")
            for sid in STATIONS:
                values = by_station[sid]
                pred_mean = sum(values) / len(values) if values else float("nan")
                print(f"  {sid}: prediction={pred_mean:.3f}; last24={last24.get(sid, float('nan')):.3f}")

    if verbose:
        if errors:
            print(f"{path.name}: FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path.name}: PASS")
    return not errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", help="submission CSV file(s) to validate")
    args = parser.parse_args()
    ok = True
    for file in args.files:
        ok = validate_file(file, verbose=True) and ok
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
