#!/usr/bin/env python3
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 10000000
MAIN_DEADLINE = float(os.environ["MAIN_FOLLOW_DEADLINE"])
DEADLINE = MAIN_DEADLINE + 300
AUXILIARY_START = DEADLINE - 2100
DIRECT_START = DEADLINE - 600
SUPERVISORS = {"gpu_rebalance.py", "gpu_follow.py", "cpu_follow.py", "elliptic_high_follow.py"}
WORKERS = {"gpu_queue.py", "gpu_search_v32", "gpu_search_v40", "gpu_search_v42", "search_v13",
           "elliptic_vector_search.py"}
PROCESS_NAMES = ["python3", "search", "search_v13", "gpu_search_v32", "gpu_search_v40", "gpu_search_v42"]
stop = threading.Event()


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"{stamp} {message}", flush=True)


def request_stop(signum, frame):
    stop.set()


def goal_complete():
    verified = ROOT / "new-verified-results.txt"
    if verified.exists() and verified.read_text().strip():
        return True
    report = ROOT / "coverage-latest.json"
    if not report.exists():
        return False
    try:
        values = json.loads(report.read_text())
        return (values.get("limit") == LIMIT and
                values.get("complete_intervals") == [[1, LIMIT]])
    except (OSError, ValueError):
        return False


def processes():
    result = subprocess.run(["ps", *sum((["-C", name] for name in PROCESS_NAMES), []),
                             "-o", "pid=,args="], text=True, capture_output=True)
    found = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 2:
            continue
        pid = int(fields[0])
        name = Path(fields[1]).name
        if name == "python3":
            if len(fields) < 3:
                continue
            name = Path(fields[2]).name
        if name not in SUPERVISORS | WORKERS | {"search", "main_follow.py"}:
            continue
        try:
            if Path(f"/proc/{pid}/cwd").resolve() != ROOT:
                continue
        except (FileNotFoundError, ProcessLookupError):
            continue
        found.append((pid, name))
    return found


def signal_names(names, phase):
    selected = [(pid, name) for pid, name in processes() if name in names]
    for pid, name in selected:
        try:
            os.kill(pid, signal.SIGTERM)
            log(f"{phase} SIGTERM pid={pid} name={name}")
        except ProcessLookupError:
            pass
    if not selected:
        log(f"{phase} no matching processes")


def wait_until(target):
    while not stop.is_set() and time.time() < target:
        if goal_complete():
            log("verified result or complete coverage detected; deadline guard exiting without signals")
            return False
        stop.wait(min(20, max(0, target - time.time())))
    return not stop.is_set()


def main():
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    log(f"schedule auxiliary={datetime.datetime.fromtimestamp(AUXILIARY_START, datetime.timezone.utc).isoformat()} "
        f"direct={datetime.datetime.fromtimestamp(DIRECT_START, datetime.timezone.utc).isoformat()} "
        f"main={datetime.datetime.fromtimestamp(MAIN_DEADLINE, datetime.timezone.utc).isoformat()} "
        f"hard={datetime.datetime.fromtimestamp(DEADLINE, datetime.timezone.utc).isoformat()}")
    log(f"initial processes={processes()}")
    if not wait_until(AUXILIARY_START):
        return
    signal_names(SUPERVISORS, "auxiliary-stop")
    if not wait_until(DIRECT_START):
        return
    signal_names(WORKERS, "worker-stop")
    if not wait_until(DEADLINE):
        return
    signal_names(WORKERS | {"search", "main_follow.py"}, "deadline-stop")
    subprocess.run(["python3", str(ROOT / "scripts/coverage_audit.py")], cwd=ROOT, check=False)
    log("deadline guard finished")


if __name__ == "__main__":
    main()
