#!/usr/bin/env python3
import datetime
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 10000000
stop = threading.Event()
child = None


def stage_range(index):
    first = 8900000 - 200000 * (index - 6)
    return first, first + 99999


def read_state(path):
    path = Path(path)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {}
    return {key: int(value) for key, value in (line.split() for line in path.read_text().splitlines())}


def complete(first, last, path):
    state = read_state(path)
    return state.get("limit") == LIMIT and state.get("end") == last and state.get("resume") == last + 1


def covered(first, last, path):
    if complete(first, last, path):
        return True
    report_path = ROOT / "coverage-latest.json"
    if not report_path.exists():
        return False
    report = json.loads(report_path.read_text())
    if report.get("limit") != LIMIT:
        return False
    return any(begin <= first and last <= end for begin, end in report["complete_intervals"])


def running():
    result = subprocess.run(["ps", "-C", "search_v13", "-o", "pid=,args="], text=True, capture_output=True)
    return [(int(fields[0]), fields) for line in result.stdout.splitlines()
            if len(fields := line.split()) == 8
            and Path(fields[6]).name.startswith("lookahead")]


def wait_for_slot(first, last, state, results):
    while not stop.is_set():
        if complete(first, last, state):
            return True
        processes = running()
        if not processes:
            return False
        for pid, fields in processes:
            matches = (fields[2:6] == [str(LIMIT), str(first), str(last), "16"] and
                       Path(fields[6]).name == Path(state).name and
                       Path(fields[7]).name == Path(results).name)
            if not matches and not complete(int(fields[3]), int(fields[4]), fields[6]):
                raise RuntimeError(f"unexpected search_v13 process: {fields}")
        stop.wait(30)
    return False


def launch(index, first, last):
    global child
    state = ROOT / f"lookahead{index}-state.txt"
    results = ROOT / f"lookahead{index}-results.txt"
    if not results.exists():
        shutil.copyfile(ROOT / "full100k-results.txt", results)
    with (ROOT / f"lookahead{index}-v13-start.txt").open("a") as output:
        output.write(datetime.datetime.now(datetime.timezone.utc).isoformat() + "\n")
    with (ROOT / f"lookahead{index}.log").open("a") as output:
        child = subprocess.Popen([
            str(ROOT / "search_v13"), str(LIMIT), str(first), str(last), "16", str(state), str(results),
        ], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
    print(f"START cpu index={index} pid={child.pid} range={first}-{last}", flush=True)


def report_results(index):
    path = ROOT / f"lookahead{index}-results.txt"
    if path.read_text().strip():
        print(f"RESULTS {path}:\n{path.read_text()}", end="", flush=True)
        subprocess.run(["python3", str(ROOT / "scripts/verify.py"), str(path)], check=True)


def run_stage(index):
    first, last = stage_range(index)
    state = ROOT / f"lookahead{index}-state.txt"
    results = ROOT / f"lookahead{index}-results.txt"
    if index == 7:
        while not stop.is_set() and not state.exists():
            stop.wait(30)
    else:
        previous_first, previous_last = stage_range(index - 1)
        while not stop.is_set() and not covered(previous_first, previous_last,
                                               ROOT / f"lookahead{index - 1}-state.txt"):
            stop.wait(30)
    failures = 0
    while not stop.is_set() and not covered(first, last, state):
        if wait_for_slot(first, last, state, results):
            break
        if stop.is_set():
            return
        launch(index, first, last)
        child.wait()
        if covered(first, last, state):
            break
        failures += 1
        if failures >= 3:
            raise RuntimeError(f"CPU stage {index} failed to advance")
        stop.wait(30)
    if complete(first, last, state):
        report_results(index)
        print(f"DONE cpu index={index} range={first}-{last}", flush=True)
    elif covered(first, last, state):
        print(f"ALREADY COVERED cpu index={index} range={first}-{last}", flush=True)


def request_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    for index in range(7, 17):
        if stop.is_set():
            break
        run_stage(index)
    print("CPU FOLLOW FINISHED", flush=True)


if __name__ == "__main__":
    main()
