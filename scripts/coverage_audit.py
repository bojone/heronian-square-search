#!/usr/bin/env python3
import datetime
import json
from pathlib import Path
import re

from gpu_stages import stage_first, stage_index

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 10000000


def state(path):
    if not path.exists():
        return {}
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def complete(first, last, path):
    values = state(path)
    return (values.get("limit") == LIMIT and values.get("end") == last
            and values.get("resume") == last + 1)


def cpu_range(index):
    if index == 0:
        return 9900000, 10000000
    if index == 1:
        return 9800000, 9899999
    if index < 7:
        first = 9500000 - 200000 * (index - 2)
    else:
        first = 8900000 - 200000 * (index - 6)
    return first, first + 99999


def merge(intervals):
    result = []
    for first, last in sorted(intervals):
        if result and first <= result[-1][1] + 1:
            result[-1][1] = max(result[-1][1], last)
        else:
            result.append([first, last])
    return result


def gpu_complete(first, last, path):
    if not complete(first, last, path):
        return False
    values = state(path)
    if values.get("version") != 1 or not 1 <= values.get("begin", 0) <= last + 1:
        return False
    log = path.with_name(path.name.replace("-state.txt", ".log"))
    if not log.exists():
        return False
    expected = first
    for line in log.read_text().splitlines():
        fields = line.split()
        if len(fields) < 3 or fields[:2] != ["PROGRESS", "resume"]:
            continue
        resume = int(fields[2])
        if resume <= expected:
            continue
        if resume != min(expected + 512, last + 1):
            return False
        expected = resume
    return expected == last + 1


def heavy_covered(path):
    values = state(path)
    minimum = values.get("min_weight", 0)
    if not minimum or values.get("limit") != LIMIT:
        return []
    first = values.get("begin", 0)
    last = values.get("end", -1)
    resume = values.get("resume", 0)
    if not 1 <= first <= last <= LIMIT or not first <= resume <= last + 1:
        return []
    done = Path(str(path) + ".done")
    if not done.exists():
        return []
    header = {}
    roots = []
    for line in done.read_text().splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0] in {"limit", "min_weight"}:
            header[fields[0]] = int(fields[1])
        elif len(fields) == 1:
            root = int(fields[0])
            if not first <= root < resume or root > last:
                raise ValueError(f"invalid heavy checkpoint entry in {done}: {root}")
            roots.append(root)
        else:
            raise ValueError(f"invalid heavy checkpoint line in {done}: {line}")
    if header.get("limit") != LIMIT or header.get("min_weight") != minimum:
        return []
    return [(root, root) for root in roots]


def main():
    covered = []
    sources = []
    main_state = state(ROOT / "main-state.txt")
    if main_state.get("limit") == LIMIT and main_state.get("resume", 0) > 1:
        covered.append((1, main_state["resume"] - 1))
        sources.append("main-state.txt")
    for index in range(17):
        first, last = cpu_range(index)
        if index == 0:
            name = "lookahead-state.txt"
        elif index < 7:
            name = f"lookahead{index + 1}-state.txt"
        else:
            name = f"lookahead{index}-state.txt"
        if complete(first, last, ROOT / name):
            covered.append((first, last))
            sources.append(name)
    pattern = re.compile(r"gpu-([0-7])([a-z]{0,2})-state\.txt")
    for path in ROOT.glob("gpu-*-state.txt"):
        match = pattern.fullmatch(path.name)
        if match is None:
            continue
        suffix = match.group(2)
        base = 9700000 if not suffix else stage_first(stage_index(suffix))
        values = state(path)
        last = values.get("end", 0)
        first = last - 12499
        if (base <= first < base + 100000 and first % 12500 == 0
                and gpu_complete(first, last, path)):
            covered.append((first, last))
            sources.append(path.name)
    for path in ROOT.glob("experiments/heavy/heavy-v3[56]-*-state.txt"):
        intervals = heavy_covered(path)
        if intervals:
            covered.extend(intervals)
            sources.append(path.name + ".done")
    intervals = merge(covered)
    roots = sum(last - first + 1 for first, last in intervals)
    pairs = sum((last - first + 1) * (2 * LIMIT - first - last + 2) // 2
                for first, last in intervals)
    report = {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "limit": LIMIT,
        "complete_intervals": intervals,
        "root_coverage": roots / LIMIT,
        "logical_pair_coverage": pairs / (LIMIT * (LIMIT + 1) // 2),
        "sources": sorted(sources),
    }
    temporary = ROOT / "coverage-latest.tmp"
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(ROOT / "coverage-latest.json")
    print(f"root coverage: {roots}/{LIMIT} = {report['root_coverage']:.6%}")
    print(f"logical pair coverage: {report['logical_pair_coverage']:.6%}")
    for first, last in intervals:
        print(f"{first}-{last}")


if __name__ == "__main__":
    main()
