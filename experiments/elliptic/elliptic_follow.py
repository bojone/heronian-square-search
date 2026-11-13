#!/usr/bin/env python3
from pathlib import Path
import os
import signal
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
BOUND = int(sys.argv[1]) if len(sys.argv) > 1 else 100
STATE = ROOT / f"elliptic-b{BOUND}-state.txt"
stop = threading.Event()
child = None


def running():
    result = subprocess.run(["ps", "-C", "python3", "-o", "pid=,args="],
                            text=True, capture_output=True)
    names = {str(ROOT / "elliptic_search.py"), "elliptic_search.py"}
    return [(int(fields[0]), fields) for line in result.stdout.splitlines()
            if len(fields := line.split()) == 4 and fields[2] in names and fields[3] == str(BOUND)]


def read_state():
    if not STATE.exists():
        raise RuntimeError(f"missing checkpoint: {STATE}")
    values = {key: int(value) for key, value in
              (line.split() for line in STATE.read_text().splitlines())}
    if (values.get("bound") != BOUND or not 0 <= values.get("fiber", -1) <= 2
            or not 0 <= values.get("next_n", -1) <= 2 * BOUND + 1):
        raise RuntimeError(f"invalid checkpoint: {values}")
    return values


def request_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)


def main():
    global child
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    while not stop.is_set():
        state = read_state()
        new = ROOT / "elliptic-new-results.txt"
        if new.exists() and new.read_text().strip():
            subprocess.run([sys.executable, str(ROOT / "verify.py"), str(new)], check=True)
            print(f"NEW RESULTS VERIFIED {new}", flush=True)
            return
        if state["fiber"] >= 2:
            print(f"ELLIPTIC FOLLOW FINISHED {state}", flush=True)
            return
        processes = running()
        if len(processes) > 1:
            raise RuntimeError(f"duplicate elliptic searches: {processes}")
        if processes:
            stop.wait(30)
            continue
        print(f"RESUME bound={BOUND} state={state}", flush=True)
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        with (ROOT / f"elliptic-b{BOUND}.log").open("a") as output:
            child = subprocess.Popen([sys.executable, str(ROOT / "elliptic_search.py"), str(BOUND)],
                                     cwd=ROOT, env=environment, stdout=output,
                                     stderr=subprocess.STDOUT)
        status = child.wait()
        if stop.is_set():
            return
        state = read_state()
        if state["fiber"] < 2 and status != 0:
            print(f"RESUMABLE EXIT status={status} state={state}", flush=True)
        stop.wait(5)


if __name__ == "__main__":
    main()
