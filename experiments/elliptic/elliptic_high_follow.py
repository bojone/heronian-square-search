#!/usr/bin/env python3
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
BOUND = int(os.environ.get("ELLIPTIC_BOUND", "10000"))
SPECS = (
    (f"elliptic-lazy-b{BOUND}", 1, {"ELLIPTIC_FIBER_STOP": "1"}),
    (f"elliptic-lazy-b{BOUND}-f1", 2,
     {"ELLIPTIC_FIBER_START": "1", "ELLIPTIC_FIBER_STOP": "2"}),
)
stop = threading.Event()
children = {}


def state(spec):
    path = ROOT / f"{spec[0]}-state.txt"
    if not path.exists():
        return {}
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def complete(spec, values):
    return values.get("bound") == BOUND and values.get("fiber", -1) >= spec[1]


def process_matches(pid):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "args="],
                            text=True, capture_output=True)
    fields = result.stdout.split()
    return len(fields) == 3 and Path(fields[1]).name == "elliptic_vector_search.py" and fields[2] == str(BOUND)


def running(handle):
    if isinstance(handle, subprocess.Popen):
        return handle.poll() is None
    return process_matches(handle)


def launch(index):
    spec = SPECS[index]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["ELLIPTIC_PREFIX"] = spec[0]
    environment.update(spec[2])
    with (ROOT / f"{spec[0]}.log").open("a") as output:
        process = subprocess.Popen([sys.executable, str(ROOT / "elliptic_vector_search.py"), str(BOUND)],
                                   cwd=ROOT, env=environment, stdout=output,
                                   stderr=subprocess.STDOUT)
    print(f"RESUME fiber_index={index} pid={process.pid} state={state(spec)}", flush=True)
    return process


def request_stop(signum, frame):
    stop.set()
    for handle in children.values():
        if isinstance(handle, subprocess.Popen):
            if handle.poll() is None:
                handle.send_signal(signal.SIGTERM)
        elif process_matches(handle):
            os.kill(handle, signal.SIGTERM)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: elliptic_high_follow.py EXISTING_PID_0 EXISTING_PID_1")
    lines = subprocess.check_output(["ps", "-C", "python3", "-o", "pid=,args="], text=True).splitlines()
    duplicates = [line for line in lines
                  if int(line.split()[0]) != os.getpid() and "elliptic_high_follow.py" in line]
    if duplicates:
        raise RuntimeError(f"duplicate high-level follow: {duplicates}")
    for index, text in enumerate(sys.argv[1:]):
        if complete(SPECS[index], state(SPECS[index])):
            continue
        pid = int(text)
        if pid == 0:
            continue
        if not process_matches(pid):
            raise RuntimeError(f"process {pid} is not the expected bound-{BOUND} worker")
        children[index] = pid
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    failures = [0, 0]
    resumed_states = {}
    print(f"ADOPT children={children} states={[state(spec) for spec in SPECS]}", flush=True)
    while not stop.is_set():
        new = ROOT / "elliptic-new-results.txt"
        if new.exists() and new.read_text().strip():
            subprocess.run([sys.executable, str(ROOT / "verify.py"), str(new)], check=True)
            print(f"NEW RESULTS VERIFIED {new}", flush=True)
            request_stop(signal.SIGTERM, None)
            break
        if all(complete(spec, state(spec)) for spec in SPECS):
            print("ALL FIBERS COMPLETE", flush=True)
            break
        for index, spec in enumerate(SPECS):
            values = state(spec)
            if complete(spec, values):
                failures[index] = 0
                continue
            handle = children.get(index)
            if handle is not None and running(handle):
                continue
            signature = (values.get("fiber"), values.get("next_n"))
            if resumed_states.get(index) == signature:
                failures[index] += 1
            else:
                failures[index] = 0
            if failures[index] >= 3:
                raise RuntimeError(f"fiber index {index} failed to advance after three resumes: {values}")
            children[index] = launch(index)
            resumed_states[index] = signature
        stop.wait(20)
    for handle in children.values():
        if isinstance(handle, subprocess.Popen):
            handle.wait()
    print("HIGH FOLLOW FINISHED", flush=True)


if __name__ == "__main__":
    main()
