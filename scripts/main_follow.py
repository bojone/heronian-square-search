#!/usr/bin/env python3
import datetime
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent.parent
LIMIT = 10000000
ARGUMENTS = ["10000000", "1", "10000000", "272", "main-state.txt", "main-results.txt"]
DEADLINE = float(os.environ["MAIN_FOLLOW_DEADLINE"])
stop = threading.Event()
child = None
current_pid = None


def log(message):
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print(f"{stamp} {message}", flush=True)


def state():
    path = ROOT / "main-state.txt"
    if not path.exists():
        return {}
    return {key: int(value) for key, value in
            (line.split() for line in path.read_text().splitlines())}


def complete(values=None):
    values = state() if values is None else values
    return (values.get("limit") == LIMIT and values.get("end") == LIMIT
            and values.get("resume", 0) > LIMIT)


def process_matches(pid):
    try:
        fields = [os.fsdecode(value) for value in
                  Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0") if value]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return len(fields) == 7 and Path(fields[0]).name == "search" and fields[1:] == ARGUMENTS


def running_main():
    result = subprocess.run(["ps", "-C", "search", "-o", "pid=,args="],
                            text=True, capture_output=True)
    found = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) == 8 and Path(fields[1]).name == "search" and fields[2:] == ARGUMENTS:
            found.append(int(fields[0]))
    if len(found) > 1:
        raise RuntimeError(f"duplicate main searches: {found}")
    return found[0] if found else None


def launch():
    global child
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    with (ROOT / "main.log").open("a") as output:
        child = subprocess.Popen([str(ROOT / "search"), *ARGUMENTS], cwd=ROOT,
                                 env=environment, stdout=output, stderr=subprocess.STDOUT)
    log(f"START main pid={child.pid} state={state()}")
    return child.pid


def request_stop(signum, frame):
    stop.set()
    if child is not None and child.poll() is None:
        child.send_signal(signal.SIGTERM)
    elif current_pid is not None and process_matches(current_pid):
        try:
            os.kill(current_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main():
    global current_pid
    if len(sys.argv) != 2:
        raise SystemExit("usage: main_follow.py EXISTING_PID_OR_0")
    if DEADLINE <= time.time():
        raise SystemExit("main follow deadline has already passed")
    lines = subprocess.check_output(["ps", "-C", "python3", "-o", "pid=,args="],
                                    text=True).splitlines()
    duplicates = [line for line in lines
                  if int(line.split()[0]) != os.getpid() and "main_follow.py" in line]
    if duplicates:
        raise RuntimeError(f"duplicate main follow: {duplicates}")
    current_pid = int(sys.argv[1])
    if current_pid:
        if not process_matches(current_pid):
            raise RuntimeError(f"process {current_pid} is not the expected main search")
    else:
        current_pid = running_main()
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    log(f"ADOPT pid={current_pid} deadline={datetime.datetime.fromtimestamp(DEADLINE, datetime.timezone.utc).isoformat()} state={state()}")
    failures = 0
    previous_resume = None
    while not stop.is_set() and time.time() < DEADLINE:
        if complete():
            log("MAIN COMPLETE")
            break
        if current_pid is not None and process_matches(current_pid):
            stop.wait(20)
            continue
        current_pid = running_main()
        if current_pid is not None:
            log(f"ADOPT replacement pid={current_pid}")
            continue
        values = state()
        if complete(values):
            continue
        resume = values.get("resume")
        if resume == previous_resume:
            failures += 1
        else:
            failures = 0
        if failures >= 3:
            raise RuntimeError(f"main search failed to advance after three resumes: {values}")
        if time.time() >= DEADLINE:
            break
        current_pid = launch()
        previous_resume = resume
        stop.wait(20)
    if time.time() >= DEADLINE and not complete():
        request_stop(signal.SIGTERM, None)
    if current_pid is not None:
        deadline = time.monotonic() + 180
        while process_matches(current_pid) and time.monotonic() < deadline:
            time.sleep(1)
        if process_matches(current_pid):
            raise RuntimeError(f"main search did not stop: {current_pid}")
    log(f"MAIN FOLLOW FINISHED complete={complete()} state={state()}")


if __name__ == "__main__":
    main()
